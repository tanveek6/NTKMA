---
title: NTKMA Media Intelligence Dashboard
emoji: 📰
colorFrom: orange
colorTo: green
sdk: docker
app_port: 7860
pinned: false
---
# NTKMA FastAPI + Firebase Backend

This version serves the existing dashboard UI from FastAPI and connects the frontend actions to backend APIs.

## Run locally

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
uvicorn app.main:app --reload
```

Open `http://127.0.0.1:8765` when using `run_server.bat`, or `http://127.0.0.1:8000` if you run uvicorn without a port.

## Firebase

The app automatically uses Firebase Firestore when credentials are configured:

```powershell
$env:FIREBASE_CREDENTIALS="C:\path\to\firebase-service-account.json"
$env:FIREBASE_PROJECT_ID="your-firebase-project-id"
$env:FIREBASE_STORAGE_BUCKET="your-project-id.appspot.com"
uvicorn app.main:app --reload
```

Without Firebase credentials, it uses `data/local_db.json` so the project still works immediately. With credentials, news, logs, documents, and ingestion runs are written to Firestore; uploaded files are also copied to Firebase Storage when `FIREBASE_STORAGE_BUCKET` is set.

## Real-time scraping

The backend starts an automatic scraper loop on startup. Defaults:

```powershell
$env:AUTO_SCRAPE_ENABLED="true"
$env:AUTO_SCRAPE_MINUTES="15"
$env:SCRAPE_LIMIT="50"
```

Manual refresh is still available from the dashboard and through `POST /api/scrape`.

## API

- `GET /api/news` - dashboard news data
- `POST /api/news` - add a news item
- `POST /api/scrape` - fetch Google News RSS results
- `POST /api/upload` - save uploaded documents and create a news record
- `GET /api/brief` - generate the officer-style daily brief
- `GET /api/logs` - scraper/upload/report logs
- `GET /api/ingestion-runs` - recent scraper run status and counts
- `GET /api/export.csv` - CSV export
- `GET /api/health` - backend status

