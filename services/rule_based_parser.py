import re
from typing import Iterable

import pdfplumber

RIAUX_BLACKLIST = [
    "VAUGARNY",
    "35560",
    "BAZOUGES",
    "BAZOUGES LA PEROUSE",
    "GROUPE RIAUX",
    "RIAUX",
    "1623Z",
    "RCS RENNES",
    "02 99 97 45 40",
]

AMOUNT_LABELS = {
    "fourniture_ht": re.compile(r"PRIX DE LA FOURNITURE HT", re.IGNORECASE),
    "prestations_ht": re.compile(r"PRIX PRESTATIONS ET SERVICES HT", re.IGNORECASE),
    "total_ht": re.compile(r"TOTAL HORS TAXE", re.IGNORECASE),
}

CP_VILLE_RE = re.compile(r"\b(\d{5})\s+(.+)")
SRX_RE = re.compile(r"SRX\s*(\d{4})\s*([A-Z]{3})\s*(\d{6})", re.IGNORECASE)
EMAIL_RE = re.compile(r"[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}", re.IGNORECASE)
PHONE_RE = re.compile(r"\b(?:\+33|0)\s?\d(?:[\s.-]?\d{2}){4}\b")
ESSENCE_RE = re.compile(r"\b(hêtre|chêne|frêne|sapin|pin)\b", re.IGNORECASE)


def _clean_line(line: str) -> str:
    value = (line or "").replace("\u202f", " ")
    value = re.sub(r"\s+", " ", value).strip()
    return value


class RuleBasedParser:
    def __init__(self, debug: bool = False):
        self.debug = debug

    def parse(self, path) -> dict:
        text, lines = self._extract_text(path)
        data = {"lines": lines}
        warnings = []

        self._parse_reference(lines, data, warnings)
        data["ref_affaire"] = self._extract_ref_affaire(lines)
        self._extract_amounts(lines, data, warnings)
        self._extract_client_block(lines, data, warnings)
        self._extract_commercial_block(lines, data, warnings)
        self._extract_technical(lines, data)
        data["pose_sold"] = self._detect_pose(lines)
        data["pose_amount"] = ""
        data["parse_warning"] = " ".join(warnings).strip()
        return data

    def _extract_text(self, path) -> tuple[str, list[str]]:
        text_parts = []
        lines = []
        with pdfplumber.open(path) as pdf:
            for page in pdf.pages:
                page_text = pdf.pages[page.page_number - 1].extract_text() or ""
                if not page_text:
                    continue
                text_parts.append(page_text)
                for line in page_text.splitlines():
                    cleaned = _clean_line(line)
                    if cleaned:
                        lines.append(cleaned)
        return "\n".join(text_parts), lines

    def _parse_reference(self, lines: list[str], data: dict, warnings: list[str]) -> None:
        for line in lines:
            match = SRX_RE.search(line)
            if match:
                data["devis_annee_mois"] = match.group(1)
                data["devis_type"] = match.group(2)
                data["devis_num"] = match.group(3)
                return
        warnings.append("Devis SRX introuvable")
        data.setdefault("devis_annee_mois", "")
        data.setdefault("devis_type", "")
        data.setdefault("devis_num", "")

    def _extract_ref_affaire(self, lines: list[str]) -> str:
        for idx, line in enumerate(lines):
            if re.search(r"r.?f affaire", line, flags=re.IGNORECASE):
                after = self._after_colon(line)
                if after:
                    return after
                return self._next_non_empty(lines, idx + 1)
        return ""

    def _extract_amounts(self, lines: list[str], data: dict, warnings: list[str]):
        for key, pattern in AMOUNT_LABELS.items():
            value = self._amount_after_label(lines, pattern)
            data[key] = value
            if not value:
                warnings.append(f"{key} manquant")

    def _amount_after_label(self, lines: list[str], label_re: re.Pattern) -> str:
        for idx, line in enumerate(lines):
            if not label_re.search(line):
                continue
            inline = self._after_colon(line)
            if inline and self._looks_amount(inline):
                return self._normalize_amount(inline)
            if idx + 1 < len(lines) and self._looks_amount(lines[idx + 1]):
                return self._normalize_amount(lines[idx + 1])
        return ""

    def _looks_amount(self, value: str) -> bool:
        return bool(re.search(r"\d[\d\s]*[.,]\d{2}", value))

    def _normalize_amount(self, value: str) -> str:
        cleaned = value.replace("\u202f", " ")
        cleaned = re.sub(r"[^\d,\. ]", "", cleaned)
        cleaned = cleaned.replace(".", ",")
        cleaned = re.sub(r"\s+", " ", cleaned).strip()
        return cleaned

    def _extract_client_block(self, lines: list[str], data: dict, warnings: list[str]):
        client_nom = ""
        adresse_lines: list[str] = []
        contact = ""
        tel = ""
        email = ""
        anchor_idx = None
        for idx, line in enumerate(lines):
            if re.search(r"code client", line, flags=re.IGNORECASE):
                anchor_idx = idx
                break
        if anchor_idx is not None:
            for rev in range(anchor_idx - 1, -1, -1):
                candidate = lines[rev]
                if self._is_blacklisted(candidate):
                    continue
                if re.search(r"(devis|r.?alis[ée]? par|date du devis|r.?f affaire)", candidate, flags=re.IGNORECASE):
                    continue
                if candidate:
                    client_nom = candidate
                    break
            if not client_nom:
                for line in lines[anchor_idx + 1 :]:
                    if re.match(r"(t[ée]l|fax|contact commercial|e[- ]?mail|mail|validit)", line, flags=re.IGNORECASE):
                        break
                    if self._is_blacklisted(line):
                        continue
                    if not client_nom and line:
                        client_nom = line
                        continue
            for line in lines[anchor_idx + 1 :]:
                if re.match(r"(t[ée]l|fax|contact commercial|e[- ]?mail|mail|validit)", line, flags=re.IGNORECASE):
                    break
                if "contact" in line.lower():
                    contact = self._after_colon(line) or contact
                    continue
                if line == client_nom:
                    continue
                adresse_lines.append(line)
            window = lines[anchor_idx : anchor_idx + 7]
            tel = self._first_match(window, PHONE_RE) or ""
            email = self._first_match(window, EMAIL_RE) or ""
        if not client_nom:
            warnings.append("Client introuvable")
        cp = ""
        ville = ""
        for line in adresse_lines:
            match = CP_VILLE_RE.search(line)
            if match:
                cp = match.group(1)
                ville = match.group(2).strip()
                break
        adresse_lines_clean = [l for l in adresse_lines if not CP_VILLE_RE.search(l) and not self._is_blacklisted(l)]
        adresse1 = adresse_lines_clean[0] if adresse_lines_clean else ""
        adresse2 = adresse_lines_clean[1] if len(adresse_lines_clean) > 1 else ""
        data.update(
            {
                "client_nom": client_nom,
                "client_contact": contact,
                "client_adresse1": adresse1,
                "client_adresse2": adresse2,
                "client_cp": cp,
                "client_ville": ville,
                "client_tel": tel,
                "client_email": email,
            }
        )

    def _extract_commercial_block(self, lines: list[str], data: dict, warnings: list[str]):
        anchor_idx = None
        for idx, line in enumerate(lines):
            if re.search(r"contact commercial", line, flags=re.IGNORECASE):
                anchor_idx = idx
                break
        commercial_nom = ""
        commercial_tel = ""
        commercial_tel2 = ""
        commercial_email = ""
        if anchor_idx is not None:
            for next_line in lines[anchor_idx + 1 :]:
                if not commercial_nom and not CP_VILLE_RE.search(next_line):
                    commercial_nom = next_line
                    continue
                if not commercial_email:
                    commercial_email = self._first_match([next_line], EMAIL_RE) or commercial_email
                phones = PHONE_RE.findall(next_line)
                for phone in phones:
                    if phone.startswith(("06", "07")) and not commercial_tel:
                        commercial_tel = phone
                    elif not commercial_tel2:
                        commercial_tel2 = phone
                if commercial_nom and commercial_tel and commercial_email:
                    break
        if not commercial_nom:
            warnings.append("Commercial introuvable")
        data.update(
            {
                "commercial_nom": commercial_nom,
                "commercial_tel": commercial_tel,
                "commercial_tel2": commercial_tel2,
                "commercial_email": commercial_email,
            }
        )

    def _extract_technical(self, lines: list[str], data: dict):
        for line in lines:
            if "- Modèle" in line:
                data["esc_gamme"] = self._after_colon(line)
            if "FINITION" in line.upper():
                continue
            if "- Marches" in line:
                data["esc_finition_marches"] = self._after_colon(line)
            if "- Structure" in line:
                data["esc_finition_structure"] = self._after_colon(line)
            if "- Main courante" in line:
                main_val = self._after_colon(line)
                data["esc_main_courante"] = main_val
                if "scellement" in main_val.lower():
                    data["esc_main_courante_scellement"] = main_val
            if "- Contremarche" in line:
                data["esc_finition_contremarche"] = self._after_colon(line)
            if "- Rampe" in line:
                data["esc_finition_rampe"] = self._after_colon(line)
            if "- Nez de marche" in line.lower():
                data["esc_nez_de_marches"] = self._after_colon(line)
            essence_match = ESSENCE_RE.search(line)
            if essence_match and not data.get("esc_essence"):
                data["esc_essence"] = essence_match.group(1).title()
            if "tête" in line.lower() and "poteau" in line.lower():
                data["esc_tete_de_poteau"] = self._after_colon(line)
            if "poteau" in line.lower() and "depart" in line.lower():
                data["esc_poteaux_depart"] = self._after_colon(line)

    def _detect_pose(self, lines: Iterable[str]) -> bool:
        saw_prestations = False
        for line in lines:
            if "PRESTATIONS" in line.upper():
                saw_prestations = True
                continue
            if saw_prestations and "pose" in line.lower():
                return True
        return False

    def _after_colon(self, line: str) -> str:
        if ":" in line:
            return line.split(":", 1)[1].strip()
        return ""

    def _next_non_empty(self, lines: list[str], start: int) -> str:
        for idx in range(start, len(lines)):
            if lines[idx].strip():
                return lines[idx].strip()
        return ""

    def _first_match(self, lines: Iterable[str], regex: re.Pattern) -> str | None:
        for line in lines:
            found = regex.search(line)
            if found:
                return found.group(0)
        return None

    def _is_blacklisted(self, value: str) -> bool:
        upper = value.upper()
        return any(token.upper() in upper for token in RIAUX_BLACKLIST)
