from __future__ import annotations

from pathlib import Path
from zipfile import ZipFile
import xml.etree.ElementTree as ET

import cv2
import numpy as np
import pdfplumber
import pytesseract
from PIL import Image

from .config import settings


if settings.tesseract_cmd:
    pytesseract.pytesseract.tesseract_cmd = settings.tesseract_cmd


def _preprocess_image(path: Path) -> Image.Image:
    img = cv2.imread(str(path))
    if img is None:
        return Image.open(path)
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    gray = cv2.bilateralFilter(gray, 9, 75, 75)
    thresh = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)[1]
    return Image.fromarray(thresh)


def _ocr_image(path: Path) -> str:
    image = _preprocess_image(path)
    return pytesseract.image_to_string(image, lang=settings.ocr_languages).strip()


def _extract_pdf(path: Path) -> str:
    text_parts: list[str] = []
    with pdfplumber.open(path) as pdf:
        for page in pdf.pages:
            page_text = page.extract_text() or ""
            if page_text.strip():
                text_parts.append(page_text)
            else:
                image = page.to_image(resolution=220).original
                text_parts.append(pytesseract.image_to_string(image, lang=settings.ocr_languages))
    return "\n\n".join(part.strip() for part in text_parts if part.strip())


def _extract_docx(path: Path) -> str:
    with ZipFile(path) as docx:
        xml = docx.read("word/document.xml")
    root = ET.fromstring(xml)
    ns = {"w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main"}
    paragraphs: list[str] = []
    for paragraph in root.findall(".//w:p", ns):
        text = "".join(node.text or "" for node in paragraph.findall(".//w:t", ns)).strip()
        if text:
            paragraphs.append(text)
    return "\n".join(paragraphs)


def extract_text(path: Path) -> tuple[str, str]:
    suffix = path.suffix.lower()
    try:
        if suffix == ".txt":
            return path.read_text(encoding="utf-8", errors="ignore"), "text"
        if suffix == ".docx":
            return _extract_docx(path), "docx"
        if suffix == ".pdf":
            return _extract_pdf(path), "pdfplumber+tesseract"
        if suffix in {".png", ".jpg", ".jpeg", ".webp", ".bmp", ".tif", ".tiff"}:
            return _ocr_image(path), "opencv+tesseract"
    except Exception as exc:
        return "", f"ocr_failed:{exc}"
    return "", "unsupported"
