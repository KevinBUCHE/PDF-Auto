import json
import re
from typing import Iterable

EMAIL_RE = re.compile(r"^[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}$", re.IGNORECASE)
CP_VILLE_RE = re.compile(r"\b(\d{5})\s+([A-Za-zÀ-ÖØ-öø-ÿ\-'\s]+)")
POSE_RE = re.compile(r"pose", re.IGNORECASE)

CLIENT_SCHEMA_KEYS = {
    "devis_annee_mois",
    "devis_type",
    "devis_num",
    "ref_affaire",
    "client_nom",
    "client_contact",
    "client_adresse1",
    "client_adresse2",
    "client_cp",
    "client_ville",
    "client_tel",
    "client_email",
    "commercial_nom",
    "commercial_tel",
    "commercial_tel2",
    "commercial_email",
    "fourniture_ht",
    "prestations_ht",
    "total_ht",
    "esc_gamme",
    "esc_essence",
    "esc_main_courante",
    "esc_main_courante_scellement",
    "esc_nez_de_marches",
    "esc_finition_marches",
    "esc_finition_structure",
    "esc_finition_mains_courante",
    "esc_finition_contremarche",
    "esc_finition_rampe",
    "esc_tete_de_poteau",
    "esc_poteaux_depart",
    "pose_sold",
    "pose_amount",
    "parse_warning",
}

RIAUX_TERMS = [
    "riaux",
    "bazouges la perouse",
    "vaugarny",
    "rcs rennes",
    "naf 1623z",
    "sas au capital",
    "35560",
]

INVALID_CLIENT_NAMES = [
    "devis",
    "réalisé par",
    "date du devis",
    "contact commercial",
]


def _normalize_string(value) -> str:
    if value is None:
        return ""
    if isinstance(value, (int, float, bool)):
        return str(value)
    return str(value).strip()


def _looks_like_cp_field(value: str) -> bool:
    return value.strip() == "35560"


def _looks_like_riaux(line: str) -> bool:
    lowered = line.lower()
    return any(term in lowered for term in RIAUX_TERMS)


def _find_cp_ville(lines: Iterable[str]) -> tuple[str, str]:
    for line in lines:
        if _looks_like_riaux(line):
            continue
        match = CP_VILLE_RE.search(line)
        if match:
            cp = match.group(1)
            ville = match.group(2).strip()
            if _looks_like_cp_field(cp) or "bazouges" in ville.lower():
                continue
            return cp, ville
    return "", ""


def _detect_pose(lines: Iterable[str]) -> bool:
    saw_prestations = False
    for line in lines:
        upper = line.upper()
        if "PRESTATIONS" in upper:
            saw_prestations = True
            continue
        if saw_prestations and POSE_RE.search(line):
            return True
    return False


def _validate_email(value: str) -> str:
    value = value.strip()
    return value if EMAIL_RE.match(value) else ""


def ensure_schema(data: dict) -> dict:
    normalized = {key: "" for key in CLIENT_SCHEMA_KEYS}
    normalized["pose_sold"] = False
    for key in CLIENT_SCHEMA_KEYS:
        if key in data:
            if key == "pose_sold":
                normalized[key] = bool(data.get(key))
            else:
                normalized[key] = _normalize_string(data.get(key))
    return normalized


def validate_and_normalize(data: dict, lines: Iterable[str]) -> dict:
    lines_list = list(lines or [])
    normalized = ensure_schema(data)
    warnings = []

    for field in ("client_nom", "client_adresse1", "client_adresse2", "client_cp", "client_ville"):
        value = normalized.get(field, "")
        if not value:
            continue
        if _looks_like_riaux(value) or _looks_like_cp_field(value):
            normalized[field] = ""
            warnings.append(f"{field} nettoyé (pollution RIAUX).")

    client_nom_lower = normalized.get("client_nom", "").lower()
    if any(term in client_nom_lower for term in INVALID_CLIENT_NAMES):
        normalized["client_nom"] = ""
        warnings.append("client_nom invalide (DEVI/Contact détecté).")

    if _looks_like_cp_field(normalized.get("client_cp", "")) or "bazouges" in normalized.get("client_ville", "").lower():
        normalized["client_cp"] = ""
        normalized["client_ville"] = ""
        warnings.append("client_cp/ville nettoyés (RIAUX).")

    cp, ville = _find_cp_ville(lines_list) if not normalized.get("client_cp") else ("", "")
    if cp and not normalized.get("client_cp"):
        normalized["client_cp"] = cp
        normalized["client_ville"] = ville
        warnings.append("client_cp/ville complétés depuis le texte.")

    commercial_nom = normalized.get("commercial_nom", "")
    if re.match(r"^\d{5}\s", commercial_nom):
        normalized["commercial_nom"] = ""
        warnings.append("commercial_nom invalide (CP détecté).")

    normalized["client_email"] = _validate_email(normalized.get("client_email", ""))
    normalized["commercial_email"] = _validate_email(normalized.get("commercial_email", ""))

    if not isinstance(normalized.get("pose_sold"), bool):
        normalized["pose_sold"] = bool(normalized.get("pose_sold"))

    if normalized["pose_sold"] is False:
        pose_detected = _detect_pose(lines_list)
        if pose_detected:
            normalized["pose_sold"] = True
            warnings.append("pose_sold auto-détectée (heuristique).")

    if normalized.get("pose_sold") and not normalized.get("pose_amount"):
        normalized["pose_amount"] = normalized.get("prestations_ht", "")

    if not normalized.get("parse_warning"):
        normalized["parse_warning"] = ""

    existing_warning = normalized.get("parse_warning", "")
    if warnings:
        warning_msg = " ".join(warnings).strip()
        if existing_warning:
            normalized["parse_warning"] = f"{existing_warning} {warning_msg}".strip()
        else:
            normalized["parse_warning"] = warning_msg

    return normalized


def safe_json_dumps(data: dict) -> str:
    return json.dumps(data, ensure_ascii=False, indent=2, sort_keys=True)
