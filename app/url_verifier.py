from __future__ import annotations

from dataclasses import dataclass
from urllib.parse import parse_qs, unquote, urlparse

import httpx
from bs4 import BeautifulSoup


@dataclass
class VerificationResult:
    raw_url: str
    canonical_url: str
    status_code: int | None
    verified: bool
    title: str = ""
    description: str = ""
    image: str = ""


def _candidate_from_google_url(url: str) -> str:
    parsed = urlparse(url)
    qs = parse_qs(parsed.query)
    for key in ("url", "q"):
        if qs.get(key):
            candidate = unquote(qs[key][0])
            if candidate.startswith("http"):
                return candidate
    return url


async def verify_url(url: str, timeout: float = 10.0) -> VerificationResult:
    if not url or url == "#":
        return VerificationResult(url, "#", None, False)

    raw_url = url
    candidate = _candidate_from_google_url(url)
    headers = {
        "User-Agent": "Mozilla/5.0 NTKMA-Media-Monitor/1.0 (+https://ntkma.local)",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    }
    try:
        async with httpx.AsyncClient(follow_redirects=True, timeout=timeout, headers=headers) as client:
            res = await client.get(candidate)
            canonical = str(res.url)
            title = ""
            description = ""
            image = ""
            content_type = res.headers.get("content-type", "")
            if "html" in content_type.lower():
                soup = BeautifulSoup(res.text[:500_000], "lxml")
                link = soup.find("link", rel=lambda v: v and "canonical" in v)
                if link and link.get("href"):
                    canonical = str(link["href"])
                og_title = soup.find("meta", property="og:title")
                og_desc = soup.find("meta", property="og:description") or soup.find("meta", attrs={"name": "description"})
                og_image = soup.find("meta", property="og:image")
                if soup.title and soup.title.string:
                    title = soup.title.string.strip()
                if og_title and og_title.get("content"):
                    title = og_title["content"].strip()
                if og_desc and og_desc.get("content"):
                    description = og_desc["content"].strip()
                if og_image and og_image.get("content"):
                    image = og_image["content"].strip()
            return VerificationResult(raw_url, canonical, res.status_code, 200 <= res.status_code < 400, title, description, image)
    except Exception:
        return VerificationResult(raw_url, candidate, None, False)
