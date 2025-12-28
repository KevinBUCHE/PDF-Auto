import re
from decimal import Decimal, InvalidOperation
from typing import Any

from services.address_sanitizer import sanitize_client_address

SRX_RE = re.compile(r"SRX(\d{4})([A-Z]{3})(\d{6})", re.IGNORECASE)
AMOUNT_KEYS = {"fourniture_ht", "prestations_ht", "total_ht", "pose_amount"}
EXPECTED_STR_KEYS = {
    "devis_annee_mois",
    "devis_type",
    "devis_num",
    "ref_affaire",
    "client_nom",
    "client_contact",
    "client_adresse1",
    "client_adresse2",
    "client_adresse",
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
    "pose_amount",
}


def _as_string(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip()


def _format_amount_fr(value: Any) -> str:
    if value in ("", None):
        return ""
    text = _as_string(value)
    text = text.replace("€", "").replace("\u00a0", " ").strip()
    try:
        if isinstance(value, (int, float, Decimal)):
            dec = Decimal(str(value))
        else:
            cleaned = text.replace(" ", "")
            cleaned = cleaned.replace(",", ".")
            dec = Decimal(cleaned)
        dec = dec.quantize(Decimal("0.01"))
    except (InvalidOperation, ValueError):
        return text
    int_part, frac_part = str(dec).split(".")
    int_part_with_space = ""
    while len(int_part) > 3:
        int_part_with_space = f" {int_part[-3:]}{int_part_with_space}"
        int_part = int_part[:-3]
    int_part_with_space = f"{int_part}{int_part_with_space}"
    return f"{int_part_with_space},{frac_part.zfill(2)}"


def _normalize_srx(data: dict) -> dict:
    normalized = dict(data)
    candidate = _as_string(data.get("devis_num", ""))
    match = SRX_RE.search(candidate)
    if not match:
        for value in data.values():
            if isinstance(value, str) and "SRX" in value.upper():
                match = SRX_RE.search(value)
                if match:
                    break
    if match:
        normalized["devis_annee_mois"] = match.group(1)
        normalized["devis_type"] = match.group(2)
        normalized["devis_num"] = match.group(3)
    else:
        devis_annee_mois = _as_string(normalized.get("devis_annee_mois", ""))
        if len(devis_annee_mois) == 6 and devis_annee_mois.isdigit():
            normalized["devis_annee_mois"] = devis_annee_mois[-4:]
    return normalized


def normalize_extracted_data(data: dict) -> dict:
    normalized: dict[str, Any] = {key: value for key, value in (data or {}).items()}
    normalized = _normalize_srx(normalized)

    for key in AMOUNT_KEYS:
        if key in normalized:
            normalized[key] = _format_amount_fr(normalized.get(key))

    normalized["pose_sold"] = bool(normalized.get("pose_sold"))

    for key in EXPECTED_STR_KEYS:
        if key not in normalized:
            normalized[key] = ""
        elif not isinstance(normalized[key], bool):
            normalized[key] = _as_string(normalized[key])

    normalized = sanitize_client_address(normalized)

    address_lines = []
    for key in ("client_adresse1", "client_adresse2"):
        part = _as_string(normalized.get(key))
        if part:
            address_lines.append(part)
    cp_ville = " ".join(
        part for part in (_as_string(normalized.get("client_cp")), _as_string(normalized.get("client_ville"))) if part
    ).strip()
    if cp_ville and cp_ville not in address_lines:
        address_lines.append(cp_ville)
    if address_lines:
        normalized["client_adresse"] = "\n".join(address_lines)

    return normalized
