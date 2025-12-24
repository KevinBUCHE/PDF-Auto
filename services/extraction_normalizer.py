import re
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from typing import Any, Iterable


SRX_RE = re.compile(r"SRX(\d{4})([A-Z]{3})(\d{6})", re.IGNORECASE)
AMOUNT_FIELDS = {"fourniture_ht", "prestations_ht", "total_ht", "pose_amount"}
BOOL_FIELDS = {"pose_sold"}
STRING_FIELDS = {
    "client_adresse",
    "client_adresse1",
    "client_adresse2",
    "client_code",
    "client_contact",
    "client_email",
    "client_fax",
    "client_mob",
    "client_nom",
    "client_tel",
    "client_ville",
    "client_cp",
    "commercial_email",
    "commercial_nom",
    "commercial_tel",
    "commercial_tel2",
    "date_devis",
    "devis_annee_mois",
    "devis_num",
    "devis_type",
    "esc_essence",
    "esc_finition_contremarche",
    "esc_finition_mains_courante",
    "esc_finition_marches",
    "esc_finition_rampe",
    "esc_finition_structure",
    "esc_gamme",
    "esc_main_courante",
    "esc_main_courante_scellement",
    "esc_nez_de_marches",
    "esc_poteaux_depart",
    "esc_tete_de_poteau",
    "parse_warning",
    "pose_amount",
    "prestations_ht",
    "ref_affaire",
    "total_ht",
    "fourniture_ht",
}
ADDRESS_POLLUTIONS = {"VAUGARNY", "35560"}


def _strip_to_str(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, bool):
        return ""
    return str(value).strip()


def _format_amount(value: Any) -> str:
    cleaned = _strip_to_str(value)
    if not cleaned:
        return ""
    normalized = (
        cleaned.replace("\u202f", " ")
        .replace("\xa0", " ")
        .replace(" ", "")
        .replace(",", ".")
    )
    try:
        amount = Decimal(normalized)
    except (InvalidOperation, ValueError):
        return ""
    quantized = amount.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    integer_part, frac_part = f"{quantized:.2f}".split(".")
    sign = "-" if quantized < 0 else ""
    integer_part = integer_part.lstrip("-")
    groups = []
    while integer_part:
        groups.append(integer_part[-3:])
        integer_part = integer_part[:-3]
    integer_with_spaces = " ".join(reversed(groups)) if groups else "0"
    return f"{sign}{integer_with_spaces},{frac_part}"


def _apply_amounts(data: dict) -> None:
    for field in AMOUNT_FIELDS:
        if field in data:
            data[field] = _format_amount(data.get(field, ""))


def _normalize_yymm(value: str) -> str:
    if not value:
        return ""
    value = value.strip()
    if re.fullmatch(r"\d{6}", value) and value.startswith("20"):
        return value[-4:]
    if re.fullmatch(r"\d{4}", value):
        return value
    return value[-4:] if len(value) > 4 and value[-4:].isdigit() else value


def _extract_srx(parts: Iterable[Any]) -> tuple[str, str, str] | None:
    for part in parts:
        if not isinstance(part, str):
            continue
        match = SRX_RE.search(part.replace(" ", ""))
        if match:
            return match.group(1), match.group(2), match.group(3)
    return None


def _normalize_srx(data: dict) -> None:
    candidates = [data.get("devis_num", "")]
    candidates.extend(value for value in data.values() if isinstance(value, str))
    match = _extract_srx(candidates)
    if match:
        yymm, devis_type, devis_num = match
        data["devis_annee_mois"] = _normalize_yymm(yymm)
        data["devis_type"] = devis_type
        data["devis_num"] = devis_num
    else:
        data["devis_annee_mois"] = _normalize_yymm(
            _strip_to_str(data.get("devis_annee_mois", ""))
        )
        devis_type = _strip_to_str(data.get("devis_type", ""))
        data["devis_type"] = devis_type.upper() if devis_type else ""
        devis_num = _strip_to_str(data.get("devis_num", ""))
        if re.fullmatch(r"\d{6}", devis_num):
            data["devis_num"] = devis_num


def _sanitize_adresse_component(value: str) -> str:
    upper = value.upper().strip()
    if not upper:
        return ""
    for token in ADDRESS_POLLUTIONS:
        if token in upper:
            return ""
    return value


def _rebuild_client_adresse(data: dict) -> None:
    lines: list[str] = []
    for key in ("client_adresse1", "client_adresse2"):
        part = _strip_to_str(data.get(key, ""))
        part = _sanitize_adresse_component(part)
        if part:
            lines.append(part)
    cp = _sanitize_adresse_component(_strip_to_str(data.get("client_cp", "")))
    ville = _sanitize_adresse_component(_strip_to_str(data.get("client_ville", "")))
    data["client_cp"] = cp
    data["client_ville"] = ville
    cp_ville = " ".join(part for part in (cp, ville) if part)
    if cp_ville:
        lines.append(cp_ville)
    data["client_adresse"] = "\n".join(lines)


def _ensure_types(data: dict) -> None:
    for key in STRING_FIELDS:
        if key in data:
            data[key] = _strip_to_str(data.get(key, ""))
    for key in BOOL_FIELDS:
        if key in data:
            data[key] = bool(data.get(key))


def normalize_extracted_data(data: dict) -> dict:
    """Normalize extracted devis data for Gemini or fallback parsers."""
    normalized = dict(data) if isinstance(data, dict) else {}
    _ensure_types(normalized)
    _normalize_srx(normalized)
    _apply_amounts(normalized)
    _rebuild_client_adresse(normalized)
    _ensure_types(normalized)
    return normalized
