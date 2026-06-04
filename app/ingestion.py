from __future__ import annotations

import asyncio
from datetime import date, datetime, timezone
from html import unescape
from urllib.parse import quote_plus
from urllib.parse import urlparse

import feedparser
import httpx
from bs4 import BeautifulSoup

from .analysis_engine import duplicate_key, guess_department, guess_sector, guess_sentiment
from .article_parser import parse_article
from .models import NewsItem
from .url_verifier import verify_url


DEFAULT_IMAGE = "https://upload.wikimedia.org/wikipedia/commons/thumb/5/5b/Ramkund_Nashik.jpg/640px-Ramkund_Nashik.jpg"

SEARCH_QUERIES = [
    "Nashik Kumbh 2027",
    "Nashik Trimbakeshwar Kumbh",
    "Simhastha Kumbh Nashik",
    "Nashik Kumbh AI crowd management",
    "Nashik Kumbh Godavari cleanup",
    "Nashik Kumbh ring road airport expansion ghats sanitation",
    "Nashik Kumbh fake tender",
]

PUBLISHER_SITE_QUERIES = {
    "Times of India": "site:timesofindia.indiatimes.com Nashik Kumbh",
    "Sakal": "site:esakal.com Nashik Kumbh",
    "Lokmat": "site:lokmat.com Nashik Kumbh",
    "Maharashtra Times": "site:maharashtratimes.com Nashik Kumbh",
    "Divya Marathi": "site:divyamarathi.bhaskar.com Nashik Kumbh",
    "Hindustan Times": "site:hindustantimes.com Nashik Kumbh",
    "Economic Times": "site:economictimes.indiatimes.com Nashik Kumbh",
    "PTI": "site:ptinews.com Nashik Kumbh",
    "Government PR": "site:pib.gov.in Nashik Kumbh OR Simhastha",
}


def _published_date(entry) -> str:
    published = getattr(entry, "published_parsed", None)
    if published:
        return date(*published[:3]).isoformat()
    return date.today().isoformat()


def _entry_source(entry, fallback: str) -> str:
    return getattr(getattr(entry, "source", None), "title", None) or fallback


def _clean_html(value: str) -> str:
    if not value:
        return ""
    return BeautifulSoup(unescape(value), "lxml").get_text(" ", strip=True)


def _is_google_news_url(url: str) -> bool:
    return urlparse(url).netloc.endswith("news.google.com")


async def _item_from_entry(entry, fallback_source: str, verify_urls: bool) -> NewsItem:
    raw_title = unescape(getattr(entry, "title", "")).strip()
    raw_url = getattr(entry, "link", "#")
    verification = await verify_url(raw_url) if verify_urls else None
    canonical = verification.canonical_url if verification else raw_url
    article = (
        await parse_article(canonical)
        if verification and canonical and canonical != "#" and not _is_google_news_url(canonical)
        else {}
    )
    title = article.get("title") or (verification.title if verification else "") or raw_title
    extracted_text = article.get("text", "")
    summary = article.get("summary") or (verification.description if verification else "") or _clean_html(getattr(entry, "summary", "")) or title
    image = article.get("image") or (verification.image if verification else "") or DEFAULT_IMAGE
    signal_text = f"{title} {summary} {extracted_text[:1200]}"
    sentiment, importance = guess_sentiment(signal_text)
    return NewsItem(
        date=_published_date(entry),
        source=_entry_source(entry, fallback_source),
        title=title,
        url=canonical,
        raw_url=raw_url,
        canonical_url=canonical,
        url_status=verification.status_code if verification else None,
        url_verified=verification.verified if verification else False,
        sector=guess_sector(signal_text),
        department=guess_department(signal_text),
        sentiment=sentiment,
        importance=importance,
        summary=summary[:1200],
        extracted_text=extracted_text[:20000],
        duplicate_key=duplicate_key(title, canonical),
        source_type="scraper",
        image=image,
        verified=bool(verification.verified) if verification else False,
        created_at=datetime.now(timezone.utc).isoformat(),
    )


async def fetch_google_news(query: str, limit: int, verify_urls: bool = True, source_name: str = "Google News") -> list[NewsItem]:
    feed_url = f"https://news.google.com/rss/search?q={quote_plus(query)}&hl=en-IN&gl=IN&ceid=IN:en"
    parsed = feedparser.parse(feed_url)
    entries = parsed.entries[:limit]
    tasks = [_item_from_entry(entry, source_name, verify_urls) for entry in entries if getattr(entry, "title", "")]
    return await asyncio.gather(*tasks) if tasks else []


async def fetch_gdelt(query: str, limit: int, verify_urls: bool = True) -> list[NewsItem]:
    params = {
        "query": query,
        "mode": "ArtList",
        "format": "json",
        "maxrecords": min(limit, 250),
        "sort": "HybridRel",
    }
    url = "https://api.gdeltproject.org/api/v2/doc/doc"
    async with httpx.AsyncClient(timeout=20.0) as client:
        res = await client.get(url, params=params)
        res.raise_for_status()
        data = res.json()

    items: list[NewsItem] = []
    for article in data.get("articles", [])[:limit]:
        title = article.get("title") or article.get("seendate") or "Untitled article"
        raw_url = article.get("url", "#")
        verification = await verify_url(raw_url) if verify_urls else None
        canonical = verification.canonical_url if verification else raw_url
        parsed_article = await parse_article(canonical) if canonical and canonical != "#" else {}
        text = parsed_article.get("text", "")
        summary = parsed_article.get("summary") or article.get("sourcecountry", "") or title
        signal_text = f"{title} {summary} {text[:1200]}"
        sentiment, importance = guess_sentiment(signal_text)
        seendate = str(article.get("seendate", ""))[:8]
        item_date = f"{seendate[:4]}-{seendate[4:6]}-{seendate[6:8]}" if len(seendate) == 8 else date.today().isoformat()
        items.append(
            NewsItem(
                date=item_date,
                source=article.get("sourceCommonName") or article.get("domain") or "GDELT",
                title=parsed_article.get("title") or title,
                url=canonical,
                raw_url=raw_url,
                canonical_url=canonical,
                url_status=verification.status_code if verification else None,
                url_verified=verification.verified if verification else False,
                sector=guess_sector(signal_text),
                department=guess_department(signal_text),
                sentiment=sentiment,
                importance=importance,
                summary=summary[:1200],
                extracted_text=text[:20000],
                duplicate_key=duplicate_key(title, canonical),
                source_type="gdelt",
                image=parsed_article.get("image") or (verification.image if verification else "") or DEFAULT_IMAGE,
                verified=bool(verification.verified) if verification else False,
                created_at=datetime.now(timezone.utc).isoformat(),
            )
        )
    return items


async def collect_all(limit: int = 50, verify_urls: bool = True, include_gdelt: bool = True, include_google_news: bool = True) -> dict[str, list[NewsItem]]:
    results: dict[str, list[NewsItem]] = {}
    per_query = max(5, min(20, limit // 4))

    if include_google_news:
        for query in SEARCH_QUERIES:
            results[f"google:{query}"] = await fetch_google_news(query, per_query, verify_urls)
        for source, query in PUBLISHER_SITE_QUERIES.items():
            results[f"publisher:{source}"] = await fetch_google_news(query, 8, verify_urls, source)

    if include_gdelt:
        gdelt_query = "(Nashik OR Trimbakeshwar OR Simhastha) Kumbh"
        results["gdelt"] = await fetch_gdelt(gdelt_query, limit, verify_urls)

    return results
