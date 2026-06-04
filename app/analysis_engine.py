from __future__ import annotations

import hashlib
import re
from collections import Counter
from difflib import SequenceMatcher

try:
    from rapidfuzz import fuzz
except Exception:  # pragma: no cover - dependency fallback
    fuzz = None


STOP_WORDS = {
    "the", "a", "an", "and", "or", "for", "to", "of", "in", "on", "at", "by", "with", "from",
    "is", "are", "was", "were", "will", "be", "has", "have", "had", "about", "after", "before",
}

DEPARTMENT_RULES = [
    ("Mobility", "Traffic Police / Transport", ["traffic", "road", "ring road", "parking", "bus", "transport", "airport", "railway"]),
    ("Public Health", "Health Department", ["health", "hospital", "medical", "ambulance", "disease", "water contamination", "stp"]),
    ("Sanitation", "Municipal Corporation", ["clean", "waste", "garbage", "sanitation", "toilet", "sewage", "drainage"]),
    ("Security", "Police Department", ["security", "police", "crowd", "stampede", "control room", "surveillance", "ai crowd"]),
    ("Infrastructure", "Public Works Department", ["bridge", "ghat", "riverfront", "construction", "corridor", "works", "tender"]),
    ("Water Management", "Water Resources / NMC", ["godavari", "water", "river", "dam", "pipeline", "stp"]),
    ("Revenue", "District Administration", ["collector", "revenue", "district administration", "meeting", "review"]),
]

NEGATIVE_WORDS = [
    "delay", "lapse", "contamination", "fear", "risk", "unsafe", "stampede", "fake", "fraud",
    "protest", "death", "accident", "shortage", "critical", "warning", "violence", "illegal",
]
POSITIVE_WORDS = ["approved", "completed", "progress", "successful", "cleanliness", "reviewed", "launched", "ready", "modern"]


def normalize_text(text: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9]+", " ", str(text).lower())).strip()


def duplicate_key(title: str, url: str = "") -> str:
    canonical = normalize_text(title)
    tokens = [t for t in canonical.split() if t not in STOP_WORDS]
    basis = " ".join(tokens[:18]) or normalize_text(url)
    return hashlib.sha256(basis.encode("utf-8")).hexdigest()[:24]


def is_near_duplicate(a: str, b: str, threshold: int = 90) -> bool:
    if not a or not b:
        return False
    left = normalize_text(a)
    right = normalize_text(b)
    if fuzz is not None:
        return fuzz.token_set_ratio(left, right) >= threshold
    return SequenceMatcher(None, left, right).ratio() * 100 >= threshold


def guess_sector(text: str) -> str:
    t = normalize_text(text)
    best = ("General Administration", 0)
    for sector, _department, words in DEPARTMENT_RULES:
        score = sum(1 for word in words if normalize_text(word) in t)
        if score > best[1]:
            best = (sector, score)
    return best[0]


def guess_department(text: str) -> str:
    sector = guess_sector(text)
    for rule_sector, department, _words in DEPARTMENT_RULES:
        if rule_sector == sector:
            return department
    return "Media Cell / Verification"


def guess_sentiment(text: str) -> tuple[str, str]:
    t = normalize_text(text)
    neg = sum(1 for word in NEGATIVE_WORDS if word in t)
    pos = sum(1 for word in POSITIVE_WORDS if word in t)
    if neg >= 2:
        return "Critical", "Critical"
    if neg == 1:
        return "Critical", "High"
    if pos > neg:
        return "Positive", "Medium"
    return "Neutral", "Medium"


def top_terms(texts: list[str], limit: int = 12) -> list[tuple[str, int]]:
    words: list[str] = []
    for text in texts:
        words.extend(w for w in normalize_text(text).split() if len(w) > 3 and w not in STOP_WORDS)
    return Counter(words).most_common(limit)
