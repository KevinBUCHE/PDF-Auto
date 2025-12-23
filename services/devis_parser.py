import re
from pathlib import Path

import pdfplumber

AMOUNT_RE = re.compile(r"([0-9][0-9\s\u202f]*[\.,][0-9]{2})")
SRX_RE = re.compile(r"SRX(?P<yymm>\d{4})(?P<type>[A-Z]{3})(?P<num>\d{6})")
EMAIL_RE = re.compile(r"[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}", re.IGNORECASE)
PHONE_RE = re.compile(r"\b(?:\+33|0)\s?\d(?:[\s.-]?\d{2}){4}\b")
CP_VILLE_RE = re.compile(r"\b(\d{5})\s+(.+)")
LETTER_RE = re.compile(r"[A-Za-zÀ-ÖØ-öø-ÿ]")


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

        pose_sold = self._detect_pose(lines)

        if not devis_num:
            warnings.append("Devis SRX introuvable.")
        if not ref_affaire:
            warnings.append("Réf affaire introuvable.")
        if not client_details["nom"]:
            warnings.append("Client introuvable (ancre 'Code client :').")

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
            "pose_amount": "",
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
                    cleaned = self._clean_line(line)
                    if cleaned:
                        lines.append(cleaned)
        return "\n".join(text_parts), lines

    def _clean_line(self, value: str) -> str:
        value = value.replace("\u202f", " ")
        value = re.sub(r"\s+", " ", value).strip()
        return value

    def _find_amount_by_label(self, lines, pattern):
        regex = re.compile(pattern, re.IGNORECASE)
        for line in lines:
            match = regex.search(line)
            if match:
                return self._normalize_amount(match.group(1))
        return ""

    def _normalize_amount(self, value: str) -> str:
        value = value.replace("\u202f", " ")
        value = re.sub(r"\s+", " ", value).strip()
        if "," in value and "." in value:
            value = value.replace(".", "")
        if "." in value:
            value = value.replace(".", ",")
        return value

    def _find_devis_reference(self, lines):
        for line in lines:
            if "DEVIS" not in line.upper():
                continue
            match = SRX_RE.search(line.replace(" ", ""))
            if match:
                return match.group("yymm"), match.group("num"), match.group("type")
        return None

    def _find_ref_affaire(self, lines):
        for idx, line in enumerate(lines):
            if "réf affaire" in line.lower():
                value = self._extract_after_colon(line)
                if not value:
                    value = self._next_non_empty(lines, idx + 1)
                return value
        return ""

    def _find_client_details(self, lines):
        block = self._extract_block(lines, r"code client\s*:")
        return self._parse_contact_block(block)

    def _find_commercial_details(self, lines):
        block = self._extract_block(lines, r"contact commercial\s*:")
        return self._parse_contact_block(block, allow_two_phones=True)

    def _extract_block(self, lines, anchor_pattern: str) -> list[str]:
        anchor_re = re.compile(anchor_pattern, re.IGNORECASE)
        stop_markers = [
            "contact commercial",
            "réf affaire",
            "code client",
            "devis",
            "prix de la fourniture",
            "prix prestations",
            "total hors taxe",
            "prestations",
        ]
        block = []
        for idx, line in enumerate(lines):
            if not anchor_re.search(line):
                continue
            inline = self._extract_after_colon(line)
            if inline and self._has_letters(inline):
                block.append(inline)
            for next_line in lines[idx + 1 :]:
                lowered = next_line.lower()
                if any(marker in lowered for marker in stop_markers):
                    break
                if next_line:
                    block.append(next_line)
            break
        return block

    def _parse_contact_block(self, block: list[str], allow_two_phones: bool = False) -> dict:
        email = ""
        phones = []
        cp = ""
        ville = ""
        candidate_lines = []
        for line in block:
            line_email = EMAIL_RE.search(line)
            if line_email and not email:
                email = line_email.group(0)
            line_phones = PHONE_RE.findall(line)
            if line_phones:
                for phone in line_phones:
                    if phone not in phones:
                        phones.append(phone)
            cp_ville = CP_VILLE_RE.search(line)
            if cp_ville:
                cp = cp_ville.group(1)
                ville = cp_ville.group(2).strip()
                continue
            cleaned = EMAIL_RE.sub("", line)
            cleaned = PHONE_RE.sub("", cleaned)
            cleaned = cleaned.strip(" -")
            if cleaned and self._has_letters(cleaned):
                candidate_lines.append(cleaned)

        nom = candidate_lines[0] if candidate_lines else ""
        adresse_lines = candidate_lines[1:] if len(candidate_lines) > 1 else []
        adresse1 = ""
        adresse2 = ""
        if len(adresse_lines) == 1:
            adresse2 = adresse_lines[0]
        elif len(adresse_lines) >= 2:
            adresse1 = adresse_lines[0]
            adresse2 = adresse_lines[1]

        tel = phones[0] if phones else ""
        tel2 = phones[1] if allow_two_phones and len(phones) > 1 else ""

        return {
            "nom": nom,
            "contact": "",
            "adresse1": adresse1,
            "adresse2": adresse2,
            "cp": cp,
            "ville": ville,
            "tel": tel,
            "tel2": tel2,
            "email": email,
        }

    def _extract_after_colon(self, line: str) -> str:
        if ":" not in line:
            return ""
        value = line.split(":", 1)[1].strip()
        return value

    def _next_non_empty(self, lines: list[str], start: int) -> str:
        for idx in range(start, len(lines)):
            if lines[idx].strip():
                return lines[idx].strip()
        return ""

    def _has_letters(self, value: str) -> bool:
        return bool(LETTER_RE.search(value))

    def _detect_pose(self, lines: list[str]) -> bool:
        saw_prestations = False
        for line in lines:
            if "PRESTATIONS" in line.upper():
                saw_prestations = True
                continue
            if saw_prestations and "pose" in line.lower():
                return True
        return False
