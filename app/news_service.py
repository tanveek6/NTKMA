from __future__ import annotations

from collections import Counter, defaultdict
from datetime import date, datetime, timedelta
import html
import re
from typing import Any

from .ingestion import fetch_google_news


async def scrape_google_news(query: str, limit: int):
    return await fetch_google_news(query, limit)


def _norm(value: Any) -> str:
    return str(value or "").strip()


def _is_flagged(item: dict[str, Any]) -> bool:
    sentiment = _norm(item.get("sentiment"))
    importance = _norm(item.get("importance"))
    return importance in {"Critical", "High"} or sentiment in {"Critical", "Negative", "High", "Critical / Reputation Risk"}


def _sentiment_bucket(item: dict[str, Any]) -> str:
    sentiment = _norm(item.get("sentiment")).lower()
    if _is_flagged(item) or "negative" in sentiment or "critical" in sentiment:
        return "Negative"
    if "positive" in sentiment:
        return "Positive"
    return "Neutral"


def _unique_items(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen_keys: set[str] = set()
    seen_titles: set[str] = set()
    unique: list[dict[str, Any]] = []
    for item in items:
        title_key = re.sub(r"\s+", " ", _norm(item.get("title")).lower())
        key = _norm(item.get("duplicate_key") or item.get("canonical_url") or item.get("url") or title_key).lower()
        if not key or key in seen_keys or (title_key and title_key in seen_titles):
            continue
        seen_keys.add(key)
        if title_key:
            seen_titles.add(title_key)
        unique.append(item)
    return unique


def _source_url(item: dict[str, Any]) -> str:
    return _norm(item.get("canonical_url") or item.get("url") or item.get("raw_url") or "#")


def _parse_item_date(item: dict[str, Any]) -> date:
    raw = _norm(item.get("date") or item.get("published_at") or item.get("created_at"))
    if raw:
        for fmt in ("%Y-%m-%d", "%d-%m-%Y", "%d/%m/%Y", "%Y/%m/%d"):
            try:
                return datetime.strptime(raw[:10], fmt).date()
            except ValueError:
                pass
        try:
            return datetime.fromisoformat(raw.replace("Z", "+00:00")).date()
        except ValueError:
            pass
    return date.today()


def _format_day(d: date) -> str:
    return d.strftime("%d %b %Y").lstrip("0")


def _format_period(start: date, end: date) -> str:
    if start == end:
        return _format_day(end)
    return f"{_format_day(start)} - {_format_day(end)}"


def _marker(item: dict[str, Any]) -> str:
    bucket = _sentiment_bucket(item)
    if bucket == "Positive":
        return "[+]"
    if bucket == "Negative":
        return "[-]"
    return "[~]"


def _decision_signal(item: dict[str, Any]) -> str:
    sector = _norm(item.get("sector") or "Unclassified")
    department = _norm(item.get("department") or "Media Cell / Verification")
    bucket = _sentiment_bucket(item)
    if bucket == "Negative":
        return f"Decision signal: CRITICAL: {sector} concern requires source verification and response from {department}."
    if bucket == "Positive":
        return f"Decision signal: Positive preparedness signal for {sector}; continue public communication and evidence sharing."
    return f"Decision signal: Process update for {sector}; monitor for outcome and keep {department} informed."


def _summary_line(item: dict[str, Any]) -> str:
    summary = summarize_text(_norm(item.get("summary") or item.get("description") or ""), fallback="")
    return summary or "Coverage item requires original-source verification before official use."


def _impact_level(item: dict[str, Any]) -> str:
    if _is_flagged(item):
        return "High"
    if _sentiment_bucket(item) == "Positive":
        return "Medium"
    return _norm(item.get("importance") or "Low")


def _narrative(positive: int, negative: int, neutral: int, sectors: Counter[str]) -> str:
    top = sectors.most_common(2)
    top_text = ", ".join(name for name, _ in top) if top else "preparedness updates"
    total = positive + negative + neutral
    if not total:
        return "No verified media items are available for this reporting period."
    if negative > positive:
        return f"Overall tone is cautious with visible concern areas around {top_text}. Leadership attention should prioritise verification, department ownership and timely clarification."
    if positive > negative:
        return f"Overall tone is cautiously optimistic, with favourable attention around {top_text}. Concerns remain suitable for routine monitoring and quick clarification."
    return f"Overall tone is balanced and mostly informational, with coverage concentrated around {top_text}. Continue monitoring for repeated concerns or escalation patterns."


def _marathi_narrative(positive: int, negative: int, neutral: int) -> str:
    if positive + negative + neutral == 0:
        return "या कालावधीसाठी पडताळलेली मीडिया माहिती उपलब्ध नाही."
    if negative > positive:
        return "एकूण सूर सावध आहे. नकारात्मक किंवा जोखमीच्या बातम्यांची मूळ स्रोतांद्वारे पडताळणी करून संबंधित विभागांकडून त्वरित प्रतिसाद आवश्यक आहे."
    if positive > negative:
        return "एकूण सूर सकारात्मक व आश्वासक आहे. तयारी, समन्वय आणि प्रगतीविषयी अनुकूल बातम्या दिसत आहेत; तरीही चिंता क्षेत्रांवर सतत लक्ष ठेवणे आवश्यक आहे."
    return "एकूण सूर संतुलित आहे. बातम्या प्रामुख्याने माहितीपर असून पुनरावृत्ती होणाऱ्या मुद्द्यांवर निरीक्षण आवश्यक आहे."


def summarize_text(text: str, fallback: str = "Uploaded document stored for OCR / manual verification.") -> str:
    clean = html.unescape(str(text or ""))
    clean = re.sub(r"<[^>]+>", " ", clean)
    clean = re.sub(r"\s+", " ", clean).strip()
    if not clean:
        return fallback
    sentences = re.split(r"(?<=[.!?])\s+", clean)
    selected = [sentence.strip() for sentence in sentences if len(sentence.strip()) > 30][:3]
    summary = " ".join(selected) if selected else clean[:700]
    return summary[:1200]


def build_brief(items: list[dict[str, Any]]) -> str:
    all_unique = _unique_items(items)

    if all_unique:
        dated = [(item, _parse_item_date(item)) for item in all_unique]
        end = max(d for _, d in dated)
        start = end - timedelta(days=6)
        report_items = [item for item, d in dated if start <= d <= end]
        if not report_items:
            report_items = all_unique
            start = min(d for _, d in dated)
            end = max(d for _, d in dated)
    else:
        report_items = []
        start = end = date.today()

    positive = sum(1 for item in report_items if _sentiment_bucket(item) == "Positive")
    negative = sum(1 for item in report_items if _sentiment_bucket(item) == "Negative")
    neutral = sum(1 for item in report_items if _sentiment_bucket(item) == "Neutral")
    total = len(report_items)
    raw_period_mentions = [item for item in items if start <= _parse_item_date(item) <= end]
    raw_mentions = max(len(raw_period_mentions), total)
    discrepancy = max(0, raw_mentions - total)
    pct = lambda value: round((value / total) * 100) if total else 0

    sectors = Counter(_norm(item.get("sector") or "Unclassified") for item in report_items)
    departments = Counter(_norm(item.get("department") or "Media Cell / Verification") for item in report_items)
    outlets = Counter(_norm(item.get("source") or "Unknown source") for item in report_items)
    flagged = [item for item in report_items if _is_flagged(item)]
    grouped: dict[date, list[dict[str, Any]]] = defaultdict(list)
    for item in report_items:
        grouped[_parse_item_date(item)].append(item)

    perception = round(((positive - negative) / total) * 100) if total else 0
    posture = "Critical / Reputation Risk" if negative > positive and negative >= 3 else "Positive" if positive > negative else "Neutral"

    lines: list[str] = [
        "NASHIK SIMHASTHA KUMBH MELA 2027",
        "Media Sentiment Analysis Report",
        "नाशिक सिंहस्थ कुंभमेळा २०२७ - मीडिया सेंटिमेंट अहवाल",
        f"Coverage Period: {_format_period(start, end)}",
        "",
        "Overall Sentiment Summary  |  एकूण सेंटिमेंट सारांश",
        "",
        f"Positive | सकारात्मक\n{pct(positive)}%",
        f"Negative | नकारात्मक\n{pct(negative)}%",
        f"Neutral | तटस्थ\n{pct(neutral)}%",
        "",
        f"Total verified articles: {total}",
        f"Raw mentions: {raw_mentions}",
        f"Discrepancy: {discrepancy}",
        f"Overall sentiment classification: {posture}",
        f"Simhastha Preparedness Perception Score: {perception}%",
        "",
        "Analysis of daily multi-source coverage for Simhastha Kumbh Mela preparations, with each item classified by theme, sentiment, impact level and responsible department.",
        _narrative(positive, negative, neutral, sectors),
        _marathi_narrative(positive, negative, neutral),
        "",
        "Reading Guide  |  वाचण्याची पद्धत",
        "[+]  Positive sentiment - opportunity or progress signal",
        "[-]  Negative sentiment - risk, concern, or gap",
        "[~]  Neutral sentiment - informational or process step",
        "",
        "Day-wise Analysis  |  दिनांकनिहाय विश्लेषण",
    ]

    if grouped:
        for day in sorted(grouped):
            day_items = grouped[day]
            day_pos = sum(1 for item in day_items if _sentiment_bucket(item) == "Positive")
            day_neg = sum(1 for item in day_items if _sentiment_bucket(item) == "Negative")
            day_neu = sum(1 for item in day_items if _sentiment_bucket(item) == "Neutral")
            lines.extend(["", f"{_format_day(day)}   Positive: {day_pos}  |  Negative: {day_neg}  |  Neutral: {day_neu}"])
            for item in day_items[:5]:
                lines.extend([
                    f"{_marker(item)} {_norm(item.get('title') or 'Untitled media item')}",
                    f"Source: {_norm(item.get('source') or 'Unknown source')} | Language: {_norm(item.get('language') or 'Not recorded')} | Platform: {_norm(item.get('platform') or item.get('platform_type') or 'Digital / Print')} | Impact: {_impact_level(item)}",
                    f"Theme: {_norm(item.get('sector') or 'Unclassified')} | Department: {_norm(item.get('department') or 'Media Cell / Verification')}",
                    f"Reason: {_summary_line(item)}",
                    _decision_signal(item),
                    f"Original link: {_source_url(item)}",
                ])
    else:
        lines.append("No verified media items are available yet.")

    lines.extend(["", "Strategic Themes for Decision-Making  |  धोरणात्मक विषय"])
    if sectors:
        for sector, count in sectors.most_common(10):
            sector_items = [item for item in report_items if _norm(item.get("sector") or "Unclassified") == sector]
            sector_neg = sum(1 for item in sector_items if _sentiment_bucket(item) == "Negative")
            sector_pos = sum(1 for item in sector_items if _sentiment_bucket(item) == "Positive")
            signal = "requires communication or administrative intervention" if sector_neg else "receiving positive or routine attention" if sector_pos else "requires routine monitoring"
            lines.append(f"- {sector}: {count} mention(s), {sector_pos} positive, {sector_neg} concern(s) - {signal}.")
    else:
        lines.append("- No theme concentration detected.")

    lines.extend(["", "Media Outlet Trend Analysis  |  मीडिया संस्था ट्रेंड विश्लेषण"])
    if outlets:
        for outlet, count in outlets.most_common(8):
            outlet_items = [item for item in report_items if _norm(item.get("source") or "Unknown source") == outlet]
            outlet_neg = sum(1 for item in outlet_items if _sentiment_bucket(item) == "Negative")
            outlet_pos = sum(1 for item in outlet_items if _sentiment_bucket(item) == "Positive")
            themes = Counter(_norm(item.get("sector") or "Unclassified") for item in outlet_items).most_common(2)
            theme_text = ", ".join(theme for theme, _ in themes) or "Unclassified"
            lines.append(f"- {outlet}: {count} mention(s); sentiment trend {outlet_pos} positive / {outlet_neg} concern(s); major themes: {theme_text}.")
    else:
        lines.append("- No outlet pattern detected.")

    lines.extend(["", "Red Flag Tracker  |  संवेदनशील मुद्दे"])
    if flagged:
        for item in flagged[:8]:
            lines.append(
                f"- Issue: {_norm(item.get('title') or 'Untitled')} | First appearance: {_format_day(_parse_item_date(item))} | Mentions: 1 | Amplification: Watch | Agency: {_norm(item.get('department') or 'Media Cell / Verification')} | Risk: {_impact_level(item)} | Action: Verify original source and assign owner. | {_source_url(item)}"
            )
    else:
        lines.append("- No immediate red-flag item detected in the current verified feed.")

    lines.extend(["", "Key Action Recommendations  |  महत्त्वाच्या शिफारशी"])
    if flagged:
        top_departments = ", ".join(name for name, _ in departments.most_common(3)) or "concerned departments"
        lines.extend([
            f"1. Verify all red-flag items through original media links before using them in official communication.",
            f"2. Assign response ownership to {top_departments} for recurring concern areas.",
            "3. Prepare short clarification notes for negative or critical coverage clusters within the same working day.",
            "4. Use positive preparedness coverage as public confidence material with photos, milestones and department factsheets.",
        ])
    else:
        lines.extend([
            "1. Maintain daily monitoring of infrastructure, mobility, health, sanitation, crowd management and river/environment themes.",
            "2. Convert positive preparedness coverage into proactive public confidence messaging.",
            "3. Keep a watch list for repeated grievances even when individual items are neutral.",
        ])

    lines.extend([
        "",
        "Weekly Perception Movement Note  |  साप्ताहिक धारणा हालचाल",
        "Use this daily baseline to compare theme-wise improvement or deterioration across the next seven days, identify communication opportunities and prepare the Commissioner brief.",
        "",
        f"Report prepared from verified dashboard coverage | {_format_period(start, end)}",
        f"अहवाल पडताळलेल्या डॅशबोर्ड कव्हरेजवर आधारित | {_format_period(start, end)}",
    ])

    return "\n".join(lines)




