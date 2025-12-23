import re
from pathlib import Path

import pdfplumber

from services.text_utils import (
    EMAIL_RE,
    PHONE_RE,
    CP_VILLE_RE,
    extract_email,
    extract_phones,
    is_cp_ville,
    is_email,
    is_phone,
    is_riaux_line,
    normalize_line,
)

AMOUNT_RE = re.compile(r"([0-9][0-9\s\u202f]*[\.,][0-9]{2})")
SRX_RE = re.compile(r"SRX(?P<yymm>\d{4})(?P<type>[A-Z]{3})(?P<num>\d{6})", re.IGNORECASE)
LETTER_RE = re.compile(r"[A-Za-zÀ-ÖØ-öø-ÿ]")
MOBILE_RE = re.compile(r"\b0[67](?:[\s.-]?\d{2}){4}\b")


class DevisParser:
    def __init__(self, debug: bool = False):
        self.debug = debug

    def parse(self, path: Path) -> dict:
        text, lines = self._extract_text(path)
        warnings = []

        devis_match = self._find_devis_reference(lines)
        devis_annee_mois = devis_match[0] if devis_match else ""
        devis_num = devis_match[1] if devis_match else ""
        devis_type = devis_match[2] if devis_match else ""

        ref_affaire = self._find_ref_affaire(lines)
        client_details = self._find_client_details(lines)
        commercial_details = self._find_commercial_details(lines)

        fourniture_ht = self._find_amount_by_label(
            lines, r"PRIX DE LA FOURNITURE HT\s*:\s*([\d\s]+,\d{2})"
        )
        prestations_ht = self._find_amount_by_label(
            lines, r"PRIX PRESTATIONS ET SERVICES HT\s*:\s*([\d\s]+,\d{2})"
        )
        total_ht = self._find_amount_by_label(
            lines, r"TOTAL HORS TAXE\s*:\s*([\d\s]+,\d{2})"
        )

        pose_sold, pose_amount = self._detect_pose(lines)

        if not devis_num:
            warnings.append("Devis SRX introuvable.")
        if not ref_affaire:
            warnings.append("Réf affaire introuvable.")
        if not client_details["nom"]:
            warnings.append("Client introuvable (ancre 'Code client :').")
        if not commercial_details["nom"]:
            warnings.append("Contact commercial introuvable.")

        return {
            "lines": lines,
            "devis_annee_mois": devis_annee_mois,
            "devis_num": devis_num,
            "devis_type": devis_type,
            "ref_affaire": ref_affaire,
            "client_nom": client_details["nom"],
            "client_contact": client_details["contact"],
            "client_adresse1": client_details["adresse1"],
            "client_adresse2": client_details["adresse2"],
            "client_cp": client_details["cp"],
            "client_ville": client_details["ville"],
            "client_tel": client_details["tel"],
            "client_email": client_details["email"],
            "commercial_nom": commercial_details["nom"],
            "commercial_tel": commercial_details["tel"],
            "commercial_tel2": commercial_details["tel2"],
            "commercial_email": commercial_details["email"],
            "fourniture_ht": fourniture_ht,
            "prestations_ht": prestations_ht,
            "total_ht": total_ht,
            "pose_sold": pose_sold,
            "pose_amount": pose_amount,
            "parse_warning": " ".join(warnings).strip(),
        }

    def _extract_text(self, path: Path) -> tuple[str, list[str]]:
        if not path.exists():
            raise FileNotFoundError(path)
        text_parts = []
        lines = []
        with pdfplumber.open(path) as pdf:
            for page in pdf.pages:
                page_text = page.extract_text() or ""
                if not page_text:
                    continue
                text_parts.append(page_text)
                for line in page_text.splitlines():
                    cleaned = normalize_line(line)
                    if cleaned:
                        lines.append(cleaned)
        return "\n".join(text_parts), lines

    def _find_amount_by_label(self, lines, pattern):
        regex = re.compile(pattern, re.IGNORECASE)
        for line in lines:
            match = regex.search(line)
            if match:
                return self._normalize_amount(match.group(1))
        return ""

    def _normalize_amount(self, value: str) -> str:
        value = normalize_line(value)
        if "," in value and "." in value:
            value = value.replace(".", "")
        if "." in value:
            value = value.replace(".", ",")
        return value

    def _find_devis_reference(self, lines):
        for line in lines:
            cleaned = re.sub(r"[^A-Za-z0-9]", "", line).upper()
            match = SRX_RE.search(cleaned)
            if match:
                return (
                    match.group("yymm"),
                    match.group("num"),
                    match.group("type").upper(),
                )
        return None

    def _find_ref_affaire(self, lines):
        for idx, line in enumerate(lines):
            if line.lower().startswith("réf affaire"):
                value = self._extract_ref_affaire(line)
                if not value:
                    value = self._next_non_empty(lines, idx + 1)
                return value.strip()
        return ""

    def _find_client_details(self, lines):
        anchor_idx = self._find_anchor_index(lines, "code client")
        if anchor_idx is None:
            return self._empty_contact()

        client_nom = self._find_client_name_before_anchor(lines, anchor_idx)
        details = self._parse_client_block(lines, anchor_idx)
        details["nom"] = client_nom
        return details

    def _find_commercial_details(self, lines):
        anchor_idx = self._find_anchor_index(lines, "contact commercial")
        if anchor_idx is None:
            return self._empty_contact()
        return self._parse_commercial_block(lines, anchor_idx)

    def _find_anchor_index(self, lines: list[str], anchor_text: str) -> int | None:
        anchor_lower = anchor_text.lower()
        for idx, line in enumerate(lines):
            if anchor_lower in line.lower():
                return idx
        return None

    def _find_client_name_before_anchor(self, lines: list[str], anchor_idx: int) -> str:
        for idx in range(anchor_idx - 1, -1, -1):
            line = lines[idx].strip()
            if not line:
                continue
            if is_riaux_line(line) or self._is_parasitic_client_line(line):
                continue
            if is_cp_ville(line) or not self._has_letters(line):
                continue
            return line
        return ""

    def _parse_client_block(self, lines: list[str], anchor_idx: int) -> dict:
        email = ""
        phones = []
        cp = ""
        ville = ""
        adresse_lines = []
        address_done = False
        for line in lines[anchor_idx + 1 :]:
            lowered = line.lower()
            if any(
                marker in lowered
                for marker in [
                    "contact commercial",
                    "réf affaire",
                    "prix de la fourniture",
                    "prix prestations",
                    "total hors taxe",
                    "prestations",
                ]
            ):
                break

            if is_riaux_line(line):
                continue

            if any(
                lowered.startswith(prefix)
                for prefix in [
                    "tél",
                    "tel",
                    "fax",
                    "mob",
                    "mail",
                    "e mail",
                    "contact commercial",
                ]
            ):
                address_done = True

            found_email = extract_email(line)
            if found_email and not email:
                email = found_email
            for phone in extract_phones(line):
                if phone not in phones:
                    phones.append(phone)

            if not address_done:
                cp_match = CP_VILLE_RE.search(line)
                if cp_match:
                    cp = cp_match.group(1)
                    ville = cp_match.group(2).strip()
                    continue
                if not is_phone(line) and not is_email(line) and self._has_letters(line):
                    adresse_lines.append(line)

        adresse1 = adresse_lines[0] if len(adresse_lines) >= 1 else ""
        adresse2 = adresse_lines[1] if len(adresse_lines) >= 2 else ""
        return {
            "nom": "",
            "contact": "",
            "adresse1": adresse1,
            "adresse2": adresse2,
            "cp": cp,
            "ville": ville,
            "tel": phones[0] if phones else "",
            "tel2": "",
            "email": email,
        }

    def _parse_commercial_block(self, lines: list[str], anchor_idx: int) -> dict:
        email = ""
        phones = []
        name = ""
        for line in lines[anchor_idx + 1 :]:
            lowered = line.lower()
            if any(
                marker in lowered
                for marker in [
                    "réf affaire",
                    "code client",
                    "prix de la fourniture",
                    "prix prestations",
                    "total hors taxe",
                    "prestations",
                ]
            ):
                break
            if is_riaux_line(line):
                continue
            if not email:
                found_email = extract_email(line)
                if found_email:
                    email = found_email
            for phone in extract_phones(line):
                if phone not in phones:
                    phones.append(phone)
            if not name and line.strip():
                if is_cp_ville(line) or is_phone(line) or is_email(line):
                    continue
                name = line.strip()
        tel = self._select_commercial_phone(phones)
        tel2 = ""
        if tel and len(phones) > 1:
            for phone in phones:
                if phone != tel:
                    tel2 = phone
                    break
        return {
            "nom": name,
            "contact": "",
            "adresse1": "",
            "adresse2": "",
            "cp": "",
            "ville": "",
            "tel": tel,
            "tel2": tel2,
            "email": email,
        }

    def _extract_after_colon(self, line: str) -> str:
        if ":" not in line:
            return ""
        value = line.split(":", 1)[1].strip()
        return value

    def _extract_ref_affaire(self, line: str) -> str:
        match = re.search(r"réf affaire\s*:?\s*(.*)", line, re.IGNORECASE)
        if not match:
            return ""
        return match.group(1).strip()

    def _next_non_empty(self, lines: list[str], start: int) -> str:
        for idx in range(start, len(lines)):
            if lines[idx].strip():
                return lines[idx].strip()
        return ""

    def _has_letters(self, value: str) -> bool:
        return bool(LETTER_RE.search(value))

    def _detect_pose(self, lines: list[str]) -> tuple[bool, str]:
        saw_prestations = False
        for line in lines:
            if "PRESTATIONS" in line.upper():
                saw_prestations = True
                continue
            if saw_prestations and "pose" in line.lower():
                amount = self._extract_amount_from_line(line)
                if amount and self._amount_to_float(amount) > 0:
                    return True, amount
        return False, ""

    def _extract_amount_from_line(self, line: str) -> str:
        match = AMOUNT_RE.search(line)
        if match:
            return self._normalize_amount(match.group(1))
        return ""

    def _amount_to_float(self, value: str) -> float:
        normalized = value.replace("\u202f", " ").replace(" ", "")
        normalized = normalized.replace(",", ".")
        try:
            return float(normalized)
        except ValueError:
            return 0.0

    def _select_commercial_phone(self, phones: list[str]) -> str:
        for phone in phones:
            if MOBILE_RE.search(phone):
                return phone
        return phones[0] if phones else ""

    def _is_parasitic_client_line(self, line: str) -> bool:
        lowered = line.lower()
        if lowered.startswith("devis"):
            return True
        if any(
            keyword in lowered
            for keyword in [
                "devis n",
                "réalisé par",
                "date du devis",
                "réf affaire",
                "validité",
            ]
        ):
            return True
        return False

    def _empty_contact(self) -> dict:
        return {
            "nom": "",
            "contact": "",
            "adresse1": "",
            "adresse2": "",
            "cp": "",
            "ville": "",
            "tel": "",
            "tel2": "",
            "email": "",
        }
