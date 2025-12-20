import re
from pathlib import Path

import pdfplumber


AMOUNT_RE = re.compile(r"([0-9][0-9\s\u202f]*[\.,][0-9]{2})")
SRX_RE = re.compile(r"SRX(\d{4})AFF(\d{1,6})")


class DevisParser:
    def parse(self, path: Path) -> dict:
        text = self._extract_text(path)
        lines = [line.strip() for line in text.splitlines() if line.strip()]

        fourniture_ht = self._find_amount_before(lines, "PRIX DE LA FOURNITURE HT")
        prestations_ht = self._find_amount_before(lines, "PRIX PRESTATIONS ET SERVICES HT")
        total_ht = self._find_amount_before(lines, "TOTAL HORS TAXE")

        devis_match = self._find_devis_reference(lines)
        devis_annee_mois = devis_match[0] if devis_match else ""
        devis_num = devis_match[1] if devis_match else ""

        return {
            "lines": lines,
            "fourniture_ht": fourniture_ht,
            "prestations_ht": prestations_ht,
            "total_ht": total_ht,
            "devis_annee_mois": devis_annee_mois,
            "devis_num": devis_num,
            "devis_type": "AFF" if devis_match else "",
        }

    def _extract_text(self, path: Path) -> str:
        if not path.exists():
            raise FileNotFoundError(path)
        text_parts = []
        with pdfplumber.open(path) as pdf:
            for page in pdf.pages:
                page_text = page.extract_text() or ""
                text_parts.append(page_text)
        return "\n".join(text_parts)

    def _find_amount_before(self, lines, label):
        for idx, line in enumerate(lines):
            if label in line:
                before = line.split(label)[0]
                amount = self._extract_amount(before)
                if amount:
                    return amount
                if idx > 0:
                    amount = self._extract_amount(lines[idx - 1])
                    if amount:
                        return amount
        return ""

    def _extract_amount(self, text):
        match = AMOUNT_RE.search(text)
        if not match:
            return ""
        value = match.group(1)
        value = value.replace("\u202f", " ")
        value = value.replace(" ", "")
        if "," in value and "." in value:
            value = value.replace(".", "")
        if "." in value:
            value = value.replace(".", ",")
        return value

    def _find_devis_reference(self, lines):
        for line in lines:
            match = SRX_RE.search(line.replace(" ", ""))
            if match:
                yymm = match.group(1)
                num = match.group(2).zfill(6)
                return yymm, num
        return None
