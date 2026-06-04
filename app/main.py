from __future__ import annotations

import csv
import asyncio
import shutil
from datetime import date as today_date
from datetime import datetime, timezone
from io import StringIO
from pathlib import Path
from uuid import uuid4

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, PlainTextResponse, Response
from fastapi.staticfiles import StaticFiles

from .config import settings
from .analysis_engine import guess_department, guess_sector, guess_sentiment
from .ingestion import collect_all, fetch_gdelt, fetch_google_news
from .models import NewsItem, ScrapeRequest
from .news_service import build_brief, summarize_text
from .ocr_service import extract_text
from .storage import ROOT, Storage


STATIC_DIR = ROOT / "app" / "static"
UPLOAD_DIR = ROOT / "uploads"
UPLOAD_DIR.mkdir(exist_ok=True)

app = FastAPI(title="NTKMA Media Intelligence Backend", version="1.0.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)
store = Storage()
ingestion_lock = asyncio.Lock()
auto_scrape_task: asyncio.Task | None = None


async def ingest_sources(
    *,
    query: str | None = None,
    limit: int | None = None,
    include_gdelt: bool = True,
    include_google_news: bool = True,
    verify_urls: bool = True,
    save: bool = True,
    source: str = "manual",
) -> dict:
    run_id = f"{source}_{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')}"
    limit = limit or settings.scrape_limit
    failures: list[str] = []
    grouped: dict[str, list[NewsItem]] = {}

    async with ingestion_lock:
        try:
            if query:
                if include_google_news:
                    grouped[f"google:{query}"] = await fetch_google_news(query, limit, verify_urls)
                if include_gdelt:
                    try:
                        grouped[f"gdelt:{query}"] = await fetch_gdelt(query, limit, verify_urls)
                    except Exception as exc:
                        failures.append(f"GDELT: {exc}")
            else:
                grouped = await collect_all(
                    limit=limit,
                    verify_urls=verify_urls,
                    include_gdelt=include_gdelt,
                    include_google_news=include_google_news,
                )
        except Exception as exc:
            store.add_log(f"Ingestion failed: {exc}")
            store.add_ingestion_run({
                "id": run_id,
                "source": source,
                "status": "failed",
                "fetched": 0,
                "inserted": 0,
                "duplicates": 0,
                "failed": 1,
                "errors": [str(exc)],
            })
            raise

        items = [item for source_items in grouped.values() for item in source_items]
        inserted, duplicates = store.upsert_unique_news(items) if save else ([], 0)
        payload = {
            "id": run_id,
            "source": source,
            "status": "completed" if not failures else "completed_with_errors",
            "backend": store.backend_name(),
            "fetched": len(items),
            "inserted": len(inserted),
            "duplicates": duplicates,
            "failed": len(failures),
            "errors": failures,
            "sources": {name: len(source_items) for name, source_items in grouped.items()},
            "query": query or "default NTKMA source set",
            "saved": save,
        }
        store.add_ingestion_run(payload)
        store.add_log(
            f"Ingestion run '{source}' completed. Fetched {len(items)}, added {len(inserted)}, duplicates {duplicates}."
        )
        return payload | {"items": inserted if save else [item.model_dump() for item in items]}


async def scheduled_ingestion() -> None:
    try:
        await ingest_sources(source="scheduler")
    except Exception as exc:
        store.add_log(f"Scheduled scraper failed: {exc}")


async def auto_scrape_loop() -> None:
    while True:
        await asyncio.sleep(max(1, settings.auto_scrape_minutes) * 60)
        await scheduled_ingestion()


@app.on_event("startup")
async def start_scheduler() -> None:
    global auto_scrape_task
    if settings.auto_scrape_enabled and auto_scrape_task is None:
        auto_scrape_task = asyncio.create_task(auto_scrape_loop())
        store.add_log(f"Auto scraper active every {settings.auto_scrape_minutes} minute(s).")


@app.on_event("shutdown")
async def stop_scheduler() -> None:
    global auto_scrape_task
    if auto_scrape_task is not None:
        auto_scrape_task.cancel()
        auto_scrape_task = None


@app.get("/")
def index() -> FileResponse:
    return FileResponse(STATIC_DIR / "index.html")


@app.get("/api/health")
def health() -> dict:
    firebase = store.diagnostics()
    return {
        "status": "ok",
        "backend": store.backend_name(),
        "auto_scrape_enabled": settings.auto_scrape_enabled,
        "auto_scrape_minutes": settings.auto_scrape_minutes,
        "firebase": firebase,
        "firebase_storage": firebase["storage"],
    }


@app.get("/api/news")
def list_news() -> dict:
    return {"items": store.list_news(), "backend": store.backend_name()}


@app.post("/api/news")
def add_news(item: NewsItem) -> dict:
    saved = store.add_news(item)
    store.add_log(f"News saved: {item.title}")
    return saved


@app.post("/api/scrape")
async def scrape(request: ScrapeRequest) -> dict:
    try:
        result = await ingest_sources(
            query=request.query,
            limit=request.limit,
            include_gdelt=request.include_gdelt,
            include_google_news=request.include_google_news,
            verify_urls=request.verify_urls,
            save=request.save,
            source="api",
        )
    except Exception as exc:
        store.add_log(f"Scrape failed: {exc}")
        raise HTTPException(status_code=502, detail="Unable to fetch live news feed right now.") from exc

    return {
        "added": result["inserted"],
        "fetched": result["fetched"],
        "duplicates": result["duplicates"],
        "failed": result["failed"],
        "items": result["items"],
        "backend": store.backend_name(),
    }


@app.post("/api/upload")
async def upload_document(
    title: str = Form("Uploaded clipping"),
    source: str = Form("Uploaded Document"),
    date: str = Form(""),
    summary: str = Form("Uploaded document stored for OCR / manual verification."),
    file: UploadFile | None = File(None),
) -> dict:
    saved_name = ""
    firebase_uri = ""
    extracted_text = ""
    ocr_method = "manual"
    if file and file.filename:
        safe_name = f"{uuid4().hex}_{Path(file.filename).name}"
        target = UPLOAD_DIR / safe_name
        with target.open("wb") as out:
            shutil.copyfileobj(file.file, out)
        saved_name = safe_name
        extracted_text, ocr_method = extract_text(target)
        firebase_uri = store.upload_file_to_firebase(target, f"uploads/{safe_name}")

    default_summary = "Uploaded document stored for OCR / manual verification."
    manual_summary = summary.strip() if summary and summary.strip() != default_summary else ""
    final_summary = manual_summary or summarize_text(extracted_text, default_summary)
    text = f"{title} {final_summary} {extracted_text[:1500]}"
    sentiment, importance = guess_sentiment(text)
    item = NewsItem(
        date=date or today_date.today().isoformat(),
        source=source,
        title=title or (file.filename if file else "Uploaded clipping"),
        url=f"/uploads/{saved_name}" if saved_name else "#",
        sector=guess_sector(text) if text.strip() else "Uploaded Document",
        department=guess_department(text) if text.strip() else "Media Cell / Verification",
        sentiment=sentiment,
        importance=importance,
        summary=final_summary,
        extracted_text=extracted_text[:20000],
        source_type="uploaded_document",
    )
    saved = store.add_news(item)
    document = store.add_document({
        "title": item.title,
        "source": source,
        "date": item.date,
        "filename": saved_name,
        "local_url": item.url,
        "firebase_uri": firebase_uri,
        "news_id": saved["id"],
        "summary": final_summary,
        "extracted_text": extracted_text[:20000],
        "ocr_method": ocr_method,
        "sector": item.sector,
        "department": item.department,
        "sentiment": item.sentiment,
        "importance": item.importance,
    })
    store.add_log(f"Document uploaded and OCR analysed: {saved['title']} ({ocr_method})")
    return {"item": saved, "document": document, "filename": saved_name, "firebase_uri": firebase_uri, "ocr_method": ocr_method, "summary": final_summary, "extracted_text": extracted_text[:3000]}


@app.get("/api/brief", response_class=PlainTextResponse)
def brief() -> str:
    store.add_log("Daily officer brief generated.")
    return build_brief(store.list_news())


@app.get("/api/logs")
def logs() -> dict:
    return {"items": store.list_logs()}


@app.get("/api/documents")
def documents() -> dict:
    return {"items": store.list_documents(), "backend": store.backend_name()}


@app.get("/api/ingestion-runs")
def ingestion_runs() -> dict:
    return {"items": store.list_ingestion_runs(), "backend": store.backend_name()}


@app.get("/api/sources")
def sources() -> dict:
    return {
        "items": [
            {"name": "Google News RSS", "url": "https://news.google.com/search?q=Nashik%20Kumbh%202027", "type": "Aggregator", "notes": "Live RSS search for Nashik Kumbh coverage"},
            {"name": "GDELT DOC API", "url": "https://www.gdeltproject.org/", "type": "Global media index", "notes": "Cross-checks national and international media mentions"},
            {"name": "Times of India Nashik", "url": "https://timesofindia.indiatimes.com/city/nashik", "type": "Publisher", "notes": "City desk and civic infrastructure coverage"},
            {"name": "Sakal", "url": "https://www.esakal.com/uttar-maharashtra/nashik", "type": "Publisher", "notes": "Marathi regional coverage"},
            {"name": "Lokmat", "url": "https://www.lokmat.com/nashik/", "type": "Publisher", "notes": "Marathi regional coverage"},
            {"name": "Maharashtra Times", "url": "https://maharashtratimes.com/maharashtra/nashik/", "type": "Publisher", "notes": "Marathi city coverage"},
            {"name": "Divya Marathi", "url": "https://divyamarathi.bhaskar.com/local/maharashtra/nashik/", "type": "Publisher", "notes": "Regional city reporting"},
            {"name": "News18 Lokmat", "url": "https://lokmat.news18.com/maharashtra/nashik/", "type": "Publisher", "notes": "Regional broadcast and web coverage"},
            {"name": "PIB / Official Govt Portals", "url": "https://pib.gov.in/", "type": "Official", "notes": "Government releases and official source verification"},
        ]
    }


@app.get("/api/export.csv")
def export_csv() -> Response:
    headers = ["date", "source", "title", "sector", "department", "sentiment", "importance", "url", "summary"]
    buffer = StringIO()
    writer = csv.DictWriter(buffer, fieldnames=headers, extrasaction="ignore")
    writer.writeheader()
    writer.writerows(store.list_news())
    return Response(
        content=buffer.getvalue(),
        media_type="text/csv",
        headers={"Content-Disposition": 'attachment; filename="ntkma-media-report.csv"'},
    )


app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
app.mount("/uploads", StaticFiles(directory=UPLOAD_DIR), name="uploads")



