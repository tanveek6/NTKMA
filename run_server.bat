@echo off
cd /d "%~dp0"
set "FIREBASE_CREDENTIALS=C:\Users\tanvi\Downloads\ntkma-media-system-firebase-adminsdk-fbsvc-1f3895c4ff.json"
set "FIREBASE_PROJECT_ID=ntkma-media-system"
set "FIREBASE_STORAGE_BUCKET=ntkma-media-system.firebasestorage.app"
set "AUTO_SCRAPE_ENABLED=true"
set "AUTO_SCRAPE_MINUTES=15"
".venv\Scripts\python.exe" -m uvicorn app.main:app --host 127.0.0.1 --port 8765
