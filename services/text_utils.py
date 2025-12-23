import re

EMAIL_RE = re.compile(r"[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}", re.IGNORECASE)
PHONE_RE = re.compile(r"\b(?:\+33|0)\s?\d(?:[\s.-]?\d{2}){4}\b")
CP_VILLE_RE = re.compile(r"\b(\d{5})\s+(.+)")

RIAUX_KEYWORDS = [
    "riaux",
    "vaugarny",
    "bazouges",
    "la perouse",
    "sas au capital",
    "r.c.s.",
    "naf",
    "tel 02 99 97 45 40",
    "groupe-riaux",
]


def normalize_line(value: str) -> str:
    value = value.replace("\u202f", " ")
    value = re.sub(r"\s+", " ", value).strip()
    return value


def is_email(line: str) -> bool:
    return bool(EMAIL_RE.search(line))


def extract_email(line: str) -> str:
    match = EMAIL_RE.search(line)
    return match.group(0) if match else ""


def is_phone(line: str) -> bool:
    return bool(PHONE_RE.search(line))


def extract_phones(line: str) -> list[str]:
    return PHONE_RE.findall(line)


def is_cp_ville(line: str) -> bool:
    return bool(CP_VILLE_RE.search(line))


def is_riaux_line(line: str) -> bool:
    lowered = normalize_line(line).lower()
    return any(keyword in lowered for keyword in RIAUX_KEYWORDS)
