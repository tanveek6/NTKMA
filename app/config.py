from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from .storage import ROOT


@dataclass(frozen=True)
class Settings:
    firebase_credentials: str = os.getenv("FIREBASE_CREDENTIALS") or os.getenv("GOOGLE_APPLICATION_CREDENTIALS") or ""
    firebase_project_id: str = os.getenv("FIREBASE_PROJECT_ID", "")
    firebase_storage_bucket: str = os.getenv("FIREBASE_STORAGE_BUCKET", "")
    auto_scrape_enabled: bool = os.getenv("AUTO_SCRAPE_ENABLED", "true").lower() in {"1", "true", "yes"}
    auto_scrape_minutes: int = int(os.getenv("AUTO_SCRAPE_MINUTES", "15"))
    scrape_limit: int = int(os.getenv("SCRAPE_LIMIT", "50"))
    tesseract_cmd: str = os.getenv("TESSERACT_CMD", "")
    ocr_languages: str = os.getenv("OCR_LANGUAGES", "eng+mar")
    uploads_dir: Path = ROOT / "uploads"


settings = Settings()
