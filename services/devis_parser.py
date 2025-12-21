import re
from pathlib import Path

import pdfplumber


AMOUNT_RE = re.compile(r"([0-9][0-9\s\u202f]*[\.,][0-9]{2})")
SRX_RE = re.compile(r"SRX(\d{4})AFF(\d{1,6})")
DATE_RE = re.compile(r"\b\d{1,2}/\d{1,2}/\d{2,4}\b")
LETTER_RE = re.compile(r"[A-Za-zÀ-ÖØ-öø-ÿ]")


class DevisParser:
    def __init__(self, debug: bool = False):
        self.debug = debug

    def parse(self, path: Path) -> dict:
        text = self._extract_text(path)
        lines = [line.strip() for line in text.splitlines() if line.strip()]
        parse_warning = ""
        if not lines:
            parse_warning = "Texte du devis illisible ou vide."

        fourniture_ht = self._find_amount_before(lines, "PRIX DE LA FOURNITURE HT")
        prestations_ht = self._find_amount_before(lines, "PRIX PRESTATIONS ET SERVICES HT")
        total_ht = self._find_amount_before(lines, "TOTAL HORS TAXE")

        devis_match = self._find_devis_reference(lines)
        devis_annee_mois = devis_match[0] if devis_match else ""
        devis_num = devis_match[1] if devis_match else ""
        devis_type = devis_match[2] if devis_match else ""

        ref_affaire = self._find_ref_affaire(lines)
        client_nom, client_adresse = self._find_client(lines)
        esc_gamme = self._find_modele(lines)
        esc_finition_marches = self._find_marche(lines)
        esc_essence = self._extract_essence(esc_finition_marches)
        esc_tete_de_poteau = self._find_tete_poteau(lines)
        esc_poteaux_depart = self._find_poteaux_depart(lines)

        data = {
            "lines": lines,
            "fourniture_ht": fourniture_ht,
            "prestations_ht": prestations_ht,
            "total_ht": total_ht,
            "devis_annee_mois": devis_annee_mois,
            "devis_num": devis_num,
            "devis_type": devis_type,
            "ref_affaire": ref_affaire,
            "client_nom": client_nom,
            "client_adresse": client_adresse,
            "esc_gamme": esc_gamme,
            "esc_finition_marches": esc_finition_marches,
            "esc_essence": esc_essence,
            "esc_tete_de_poteau": esc_tete_de_poteau,
            "esc_poteaux_depart": esc_poteaux_depart,
            "parse_warning": parse_warning,
        }
        if self.debug:
            data["debug"] = [
                f"devis_annee_mois={devis_annee_mois}",
                f"devis_type={devis_type}",
                f"devis_num={devis_num}",
                f"ref_affaire={ref_affaire}",
                f"client_nom={client_nom}",
                f"client_adresse={client_adresse}",
                f"fourniture_ht={fourniture_ht}",
                f"prestations_ht={prestations_ht}",
                f"total_ht={total_ht}",
                f"esc_gamme={esc_gamme}",
                f"esc_finition_marches={esc_finition_marches}",
                f"esc_essence={esc_essence}",
                f"esc_tete_de_poteau={esc_tete_de_poteau}",
                f"esc_poteaux_depart={esc_poteaux_depart}",
            ]
        return data

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
                return yymm, num, "AFF"
        return None

    def _find_ref_affaire(self, lines):
        for idx, line in enumerate(lines):
            if DATE_RE.search(line):
                for prev in range(idx - 1, -1, -1):
                    if lines[prev].strip():
                        return lines[prev].strip()
                return ""
        return ""

    def _find_client(self, lines):
        block = self._find_block(lines, "code client", "contact commercial")
        if not block:
            return "", ""
        name_index = None
        for idx, line in enumerate(block):
            if LETTER_RE.search(line) and not line.strip().isdigit():
                name_index = idx
                break
        if name_index is None:
            name_index = 0
        client_nom = block[name_index].strip() if block else ""
        address_lines = [line.strip() for line in block[name_index + 1 :] if line.strip()]
        client_adresse = "\n".join(address_lines)
        return client_nom, client_adresse

    def _find_block(self, lines, start_label, end_label):
        start_idx = None
        end_idx = None
        for idx, line in enumerate(lines):
            lowered = line.lower()
            if start_idx is None and start_label in lowered:
                start_idx = idx + 1
                continue
            if start_idx is not None and end_label in lowered:
                end_idx = idx
                break
        if start_idx is None:
            return []
        if end_idx is None:
            end_idx = len(lines)
        return [line.strip() for line in lines[start_idx:end_idx] if line.strip()]

    def _find_modele(self, lines):
        for line in lines:
            match = re.search(r"-\s*Mod[eè]le\s*:\s*(.+)", line, re.IGNORECASE)
            if match:
                return match.group(1).strip()
        return ""

    def _find_marche(self, lines):
        for line in lines:
            match = re.search(r"-\s*Marche\s*:\s*(.+)", line, re.IGNORECASE)
            if match:
                return match.group(1).strip()
        return ""

    def _extract_essence(self, finition_marches: str) -> str:
        if not finition_marches:
            return ""
        parts = finition_marches.split("-", 1)
        return parts[0].strip()

    def _find_tete_poteau(self, lines):
        for line in lines:
            if "poteau" in line.lower():
                match = re.search(r"\(([^)]+)\)", line)
                if match:
                    return match.group(1).strip()
        return ""

    def _find_poteaux_depart(self, lines):
        for line in lines:
            if "poteau" in line.lower():
                lowered = line.lower()
                if "droit" in lowered or "standard" in lowered:
                    continue
                cleaned = re.sub(r"^[\-\s]*", "", line).strip()
                cleaned = re.sub(r"\([^)]*\)", "", cleaned).strip()
                return cleaned
        return ""
