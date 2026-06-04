from __future__ import annotations

import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.analysis_engine import guess_department, guess_sector, guess_sentiment
from app.news_service import summarize_text
from app.ocr_service import extract_text
from app.storage import ROOT, Storage

DEFAULT_SUMMARY = "Uploaded document stored for OCR / manual verification."


def main() -> None:
    store = Storage()
    docs = store.list_documents()
    updated = 0
    skipped = 0
    failed = 0
    for doc in docs:
        filename = doc.get("filename") or ""
        if not filename:
            skipped += 1
            continue
        path = ROOT / "uploads" / filename
        if not path.exists():
            skipped += 1
            continue
        current_summary = (doc.get("summary") or "").strip()
        if current_summary and current_summary != DEFAULT_SUMMARY and doc.get("extracted_text"):
            skipped += 1
            continue
        text, method = extract_text(path)
        if not text.strip():
            failed += 1
            doc["ocr_method"] = method
            doc["summary"] = current_summary or DEFAULT_SUMMARY
        else:
            summary = summarize_text(text, DEFAULT_SUMMARY)
            signal = f"{doc.get('title','')} {summary} {text[:1500]}"
            sentiment, importance = guess_sentiment(signal)
            doc.update({
                "summary": summary,
                "extracted_text": text[:20000],
                "ocr_method": method,
                "sector": guess_sector(signal),
                "department": guess_department(signal),
                "sentiment": sentiment,
                "importance": importance,
            })
            updated += 1
        store.add_document(doc)
        news_id = doc.get("news_id")
        if news_id and store.firestore is not None:
            store.firestore.collection("news").document(news_id).set({
                "summary": doc.get("summary", DEFAULT_SUMMARY),
                "extracted_text": doc.get("extracted_text", "")[:20000],
                "sector": doc.get("sector", "Uploaded Document"),
                "department": doc.get("department", "Media Cell / Verification"),
                "sentiment": doc.get("sentiment", "Neutral"),
                "importance": doc.get("importance", "Medium"),
                "source_type": "uploaded_document",
            }, merge=True)
    print({"backend": store.backend_name(), "documents": len(docs), "updated": updated, "skipped": skipped, "failed": failed})


if __name__ == "__main__":
    os.environ.setdefault("AUTO_SCRAPE_ENABLED", "false")
    main()
