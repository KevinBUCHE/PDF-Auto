import re
import unicodedata
from pathlib import Path
from typing import Iterable, List

from . import rules


def normalize_line(text: str) -> str:
    cleaned = unicodedata.normalize("NFKC", text or "")
    cleaned = cleaned.replace("\u00a0", " ")
    cleaned = re.sub(r"\s+", " ", cleaned)
    return cleaned.strip()


def normalize_for_match(text: str) -> str:
    base = normalize_line(text).lower()
    base = unicodedata.normalize("NFD", base)
    base = "".join(ch for ch in base if unicodedata.category(ch) != "Mn")
    return base


def is_riaux_line(line: str) -> bool:
    lowered = normalize_for_match(line)
    return any(marker in lowered for marker in rules.RIAUX_MARKERS)


def extract_amount(text: str) -> str:
    matches = re.findall(r"([0-9][0-9\s.,]*)", text)
    return normalize_line(matches[-1]) if matches else ""


def extract_phone_numbers(text: str) -> List[str]:
    return [normalize_line(num) for num in rules.PHONE_PATTERN.findall(text)]


def extract_email(text: str) -> str:
    match = rules.EMAIL_PATTERN.search(text)
    return match.group(0) if match else ""


def safe_filename(raw: str) -> str:
    base = normalize_line(raw)
    base = re.sub(r"[^A-Za-z0-9 _.-]", "_", base)
    base = re.sub(r"\s+", " ", base).strip()
    return base or "document"


def choose_first(values: Iterable[str]) -> str:
    for value in values:
        if value:
            return value
    return ""


def ensure_directory(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)
