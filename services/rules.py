import re
from dataclasses import dataclass
from typing import Iterable, List, Optional, Sequence, Tuple


DEVISE_REGEX = re.compile(r"SRX\d{4}[A-Z]{3}\d{6}")
BANNED_CLIENT_TERMS = ["DEVIS", "RÉALISÉ PAR", "REALISE PAR", "RIAUX", "VAUGARNY", "BAZOUGES", "35560"]
ADDRESS_STOP_PREFIXES = [
    "tél",
    "tel",
    "fax",
    "mail",
    "e mail",
    "contact commercial",
    "validité",
    "désignation",
]
NEGATIVE_CONTREMARCHE = ["sans", "aucune", "non"]
STRUCTURE_MAP = [
    ("cremaill", "bdc_chk_cremaillere"),
    ("limon central", "bdc_chk_limon_centrale"),
    ("limon decoupe", "bdc_chk_limon_decoupe"),
    ("limon", "bdc_chk_limon"),
    ("découp", "bdc_chk_limon_decoupe"),
]
ESSENCE_KEYWORDS = ["chêne", "chene", "hêtre", "hetre", "frêne", "frene", "pin", "sapin"]


@dataclass
class ParsedValues:
    devis_ref: str
    ref_affaire: str
    client_nom: str
    client_adresse: str
    commercial: str
    modele: str
    contremarche_flag: Optional[str]
    structure_flag: Optional[str]
    tete_poteau: str
    essence: str
    finition_marches: str
    finition_structure: str
    finition_main_courante: str
    finition_contremarche: str
    finition_rampe: str
    fourniture_ht: str
    prestation_ht: str


def normalize_line(line: str) -> str:
    return " ".join(line.split())


def is_banned_client_line(line: str) -> bool:
    upper = line.upper()
    return any(term in upper for term in BANNED_CLIENT_TERMS)


def find_first(lines: Sequence[str], predicate) -> Optional[int]:
    for idx, line in enumerate(lines):
        if predicate(line):
            return idx
    return None


def extract_after_colon(line: str) -> str:
    if ":" in line:
        return line.split(":", 1)[1].strip()
    return ""


def find_regex_in_lines(pattern: re.Pattern[str], lines: Iterable[str]) -> Optional[str]:
    for line in lines:
        match = pattern.search(line)
        if match:
            return match.group(0)
    return None


def extract_essence(value: str) -> str:
    lower = value.lower()
    for keyword in ESSENCE_KEYWORDS:
        if keyword in lower:
            return keyword
    return ""


def normalize_price(raw: str) -> str:
    cleaned = raw.replace("€", "").replace("EUR", "").replace(" ", "").replace("\u00a0", "")
    cleaned = cleaned.replace(",", ".")
    numbers = re.findall(r"\d+(?:\.\d+)?", cleaned)
    if not numbers:
        return ""
    numeric = float(numbers[0])
    whole, frac = divmod(round(numeric * 100), 100)
    whole_str = f"{int(whole):,}".replace(",", " ")
    return f"{whole_str},{int(frac):02d}"
