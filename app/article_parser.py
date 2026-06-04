from __future__ import annotations

import httpx
from bs4 import BeautifulSoup

try:
    from newspaper import Article
except Exception:  # pragma: no cover - optional runtime dependency
    Article = None


async def parse_article(url: str) -> dict[str, str]:
    if not url or url == "#":
        return {"title": "", "text": "", "summary": "", "image": ""}

    if Article is not None:
        try:
            article = Article(url)
            article.download()
            article.parse()
            try:
                article.nlp()
            except Exception:
                pass
            return {
                "title": article.title or "",
                "text": article.text or "",
                "summary": article.summary or "",
                "image": article.top_image or "",
            }
        except Exception:
            pass

    try:
        async with httpx.AsyncClient(timeout=12.0, follow_redirects=True) as client:
            res = await client.get(url, headers={"User-Agent": "Mozilla/5.0 NTKMA-Media-Monitor/1.0"})
        soup = BeautifulSoup(res.text, "lxml")
        for tag in soup(["script", "style", "noscript"]):
            tag.decompose()
        paragraphs = [p.get_text(" ", strip=True) for p in soup.find_all("p")]
        text = "\n".join(p for p in paragraphs if len(p) > 40)
        title = soup.title.string.strip() if soup.title and soup.title.string else ""
        return {"title": title, "text": text, "summary": text[:600], "image": ""}
    except Exception:
        return {"title": "", "text": "", "summary": "", "image": ""}
