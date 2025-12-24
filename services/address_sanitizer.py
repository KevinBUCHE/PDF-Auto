import re
from typing import Iterable

POLLUTION_PATTERNS = [
    r"VAUGARNY",
    r"BAZOUGES",
    r"LA PEROUSE",
    r"\b35560\b",
    r"RCS RENNES",
    r"NAF 1623Z",
    r"SAS au capital",
    r"Tél\\s*:\\s*02\\s*99\\s*97\\s*45\\s*40",
]

CP_VILLE_RE = re.compile(r"\b(\d{5})\s+(.+)")


def _normalize(value: str) -> str:
    return (value or "").strip()


def _contains_pollution(value: str) -> bool:
    return any(re.search(pattern, value, flags=re.IGNORECASE) for pattern in POLLUTION_PATTERNS)


def strip_pollution_lines(lines: Iterable[str]) -> list[str]:
    cleaned = []
    for line in lines or []:
        normalized = _normalize(line)
        if not normalized:
            continue
        if _contains_pollution(normalized):
            continue
        if normalized not in cleaned:
            cleaned.append(normalized)
    return cleaned


def _cp_ville_is_polluted(cp: str, ville: str) -> bool:
    if not cp and not ville:
        return False
    if cp == "35560":
        return True
    if ville and re.search(r"BAZOUGES", ville, flags=re.IGNORECASE):
        return True
    return _contains_pollution(cp or "") or _contains_pollution(ville or "")


def deduce_cp_ville(lines: Iterable[str], existing_cp: str = "", existing_ville: str = "") -> tuple[str, str]:
    cp = existing_cp
    ville = existing_ville
    for line in lines or []:
        if _contains_pollution(line):
            continue
        match = CP_VILLE_RE.search(line)
        if not match:
            continue
        candidate_cp, candidate_ville = match.group(1), match.group(2).strip()
        if _cp_ville_is_polluted(candidate_cp, candidate_ville):
            continue
        if not cp:
            cp = candidate_cp
        if not ville:
            ville = candidate_ville
        if cp and ville:
            break
    return cp, ville


def sanitize_client_address(data: dict) -> dict:
    sanitized = dict(data)
    direct_lines = strip_pollution_lines((sanitized.get("client_adresse") or "").splitlines())
    candidate_lines = list(direct_lines)
    for key in ("client_adresse1", "client_adresse2"):
        value = sanitized.get(key, "")
        if isinstance(value, str):
            candidate_lines.append(value)
    candidate_lines = strip_pollution_lines(candidate_lines)

    cp = _normalize(sanitized.get("client_cp", ""))
    ville = _normalize(sanitized.get("client_ville", ""))
    if _cp_ville_is_polluted(cp, ville):
        cp = ""
        ville = ""

    lines_from_data = sanitized.get("lines") or []
    cp, ville = deduce_cp_ville(lines_from_data, cp, ville)
    cp, ville = deduce_cp_ville(candidate_lines, cp, ville)
    if _cp_ville_is_polluted(cp, ville):
        cp = ""
        ville = ""

    address_lines = strip_pollution_lines(candidate_lines)
    cp_ville_line = " ".join(part for part in (cp, ville) if part).strip()
    if cp_ville_line and cp_ville_line not in address_lines:
        address_lines.append(cp_ville_line)

    sanitized["client_cp"] = cp
    sanitized["client_ville"] = ville
    sanitized["client_adresse1"] = address_lines[0] if address_lines else ""
    sanitized["client_adresse2"] = address_lines[1] if len(address_lines) > 1 else ""
    sanitized["client_adresse"] = "\n".join(address_lines)
    return sanitized
