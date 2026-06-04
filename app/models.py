from __future__ import annotations

from datetime import date
from typing import Optional
from uuid import uuid4

from pydantic import BaseModel, Field


class NewsItem(BaseModel):
    id: str = Field(default_factory=lambda: uuid4().hex)
    date: str = Field(default_factory=lambda: date.today().isoformat())
    source: str = "Uploaded Document"
    title: str
    url: str = "#"
    raw_url: str = ""
    canonical_url: str = ""
    url_status: int | None = None
    url_verified: bool = False
    sector: str = "Unclassified"
    department: str = "Media Cell / Verification"
    sentiment: str = "Neutral"
    importance: str = "Medium"
    summary: str = ""
    extracted_text: str = ""
    duplicate_key: str = ""
    duplicate_of: str = ""
    source_type: str = "manual"
    image: str = "https://upload.wikimedia.org/wikipedia/commons/thumb/5/5b/Ramkund_Nashik.jpg/640px-Ramkund_Nashik.jpg"
    verified: bool = True
    created_at: Optional[str] = None
    updated_at: Optional[str] = None


class LogEntry(BaseModel):
    id: str = Field(default_factory=lambda: uuid4().hex)
    message: str
    created_at: str


class ScrapeRequest(BaseModel):
    query: str = "Nashik Kumbh 2027"
    limit: int = Field(default=20, ge=1, le=50)
    include_gdelt: bool = True
    include_google_news: bool = True
    verify_urls: bool = True
    save: bool = True


class BriefResponse(BaseModel):
    brief: str


class IngestionResult(BaseModel):
    source: str
    fetched: int = 0
    inserted: int = 0
    duplicates: int = 0
    failed: int = 0
