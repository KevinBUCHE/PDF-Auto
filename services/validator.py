import re
from typing import Tuple, List

from services.address_sanitizer import sanitize_client_address

RIAUX_TOKENS = [
    "VAUGARNY",
    "35560",
    "BAZOUGES",
    "BAZOUGES LA PEROUSE",
    "GROUPE RIAUX",
    "RIAUX",
    "1623Z",
    "RCS RENNES",
    "02 99 97 45 40",
    "@GROUPE-RIAUX.FR",
]


def _contains_riaux(value: str) -> bool:
    upper = value.upper()
    return any(token in upper for token in RIAUX_TOKENS)


def _clean_cp(cp: str) -> str:
    cp = (cp or "").strip()
    return cp if re.fullmatch(r"\d{5}", cp) else ""


def _clean_amount(value: str) -> str:
    value = (value or "").replace("\u202f", " ").strip()
    if not re.search(r"\d[\d\s]*[.,]\d{2}", value):
        return ""
    value = value.replace(".", ",")
    value = re.sub(r"\s+", " ", value).strip()
    return value


def validate_and_fix(data: dict) -> Tuple[dict, List[str]]:
    fixed = dict(data)
    warnings: List[str] = []

    fixed = sanitize_client_address(fixed)

    if _contains_riaux(fixed.get("client_nom", "")):
        fixed["client_nom"] = ""
        warnings.append("Client contient une pollution RIAUX")
    for key in ("client_adresse1", "client_adresse2", "client_ville", "client_cp"):
        if _contains_riaux(fixed.get(key, "")):
            fixed[key] = ""
            warnings.append(f"{key} contient une pollution RIAUX")

    fixed["client_cp"] = _clean_cp(fixed.get("client_cp", ""))
    if fixed["client_cp"] == "":
        fixed["client_ville"] = fixed.get("client_ville", "")

    for key in ("fourniture_ht", "prestations_ht", "total_ht", "pose_amount"):
        cleaned = _clean_amount(fixed.get(key, ""))
        if fixed.get(key) and not cleaned:
            warnings.append(f"Montant invalide pour {key}")
        fixed[key] = cleaned

    if fixed.get("ref_affaire", "").lower().startswith("réf affaire"):
        fixed["ref_affaire"] = fixed["ref_affaire"].split(":", 1)[-1].strip()

    email_regex = re.compile(r"^[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}$", re.IGNORECASE)
    for key in ("client_email", "commercial_email"):
        email = fixed.get(key, "")
        if email and not email_regex.fullmatch(email):
            fixed[key] = ""
            warnings.append(f"Email invalide pour {key}")

    return fixed, warnings
