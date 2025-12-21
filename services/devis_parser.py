import re
from pathlib import Path

import pdfplumber


AMOUNT_RE = re.compile(r"([0-9][0-9\s\u202f]*[\.,][0-9]{2})")
EURO_AMOUNT_RE = re.compile(r"(\d[\d\s]*,\d{2})\s*€")
SRX_RE = re.compile(r"SRX(?P<yymm>\d{4})(?P<type>[A-Z]{3})(?P<num>\d{6})")
LETTER_RE = re.compile(r"[A-Za-zÀ-ÖØ-öø-ÿ]")
EMAIL_RE = re.compile(r"[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}", re.IGNORECASE)
PHONE_RE = re.compile(r"\b(?:\+33|0)\s?\d(?:[\s.-]?\d{2}){4}\b")
CP_VILLE_RE = re.compile(r"\b(\d{5})\s+(.+)")


class DevisParser:
    def __init__(self, debug: bool = False):
        self.debug = debug

    def parse(self, path: Path) -> dict:
        text = self._extract_text(path)
        lines = [line.strip() for line in text.splitlines() if line.strip()]
        parse_warning = ""
        if not lines:
            parse_warning = "Texte du devis illisible ou vide."

        fourniture_ht = self._find_amount_by_label(
            lines, r"PRIX DE LA FOURNITURE HT\s*:\s*([\d\s]+,\d{2})"
        )
        prestations_ht = self._find_amount_by_label(
            lines, r"PRIX PRESTATIONS ET SERVICES HT\s*:\s*([\d\s]+,\d{2})"
        )
        total_ht = self._find_amount_by_label(
            lines, r"TOTAL HORS TAXE\s*:\s*([\d\s]+,\d{2})"
        )

        devis_match = self._find_devis_reference(lines)
        devis_annee_mois = devis_match[0] if devis_match else ""
        devis_num = devis_match[1] if devis_match else ""
        devis_type = devis_match[2] if devis_match else ""

        ref_affaire = self._find_ref_affaire(lines)
        client_details = self._find_client_details(lines)
        commercial_details = self._find_commercial_details(lines)
        esc_gamme = self._find_modele(lines)
        esc_finition_marches = self._find_marche(lines)
        esc_essence = self._extract_essence(esc_finition_marches)
        esc_tete_de_poteau = self._find_tete_poteau(lines)
        esc_poteaux_depart = self._find_poteaux_depart(lines)
        pose_sold, pose_amount = self._find_pose_details(lines)

        data = {
            "lines": lines,
            "fourniture_ht": fourniture_ht,
            "prestations_ht": prestations_ht,
            "total_ht": total_ht,
            "devis_annee_mois": devis_annee_mois,
            "devis_num": devis_num,
            "devis_type": devis_type,
            "ref_affaire": ref_affaire,
            "client_nom": client_details["nom"],
            "client_adresse1": client_details["adresse1"],
            "client_adresse2": client_details["adresse2"],
            "client_cp": client_details["cp"],
            "client_ville": client_details["ville"],
            "client_tel": client_details["tel"],
            "client_email": client_details["email"],
            "client_contact": client_details["contact"],
            "commercial_nom": commercial_details["nom"],
            "commercial_tel": commercial_details["tel"],
            "commercial_email": commercial_details["email"],
            "esc_gamme": esc_gamme,
            "esc_finition_marches": esc_finition_marches,
            "esc_essence": esc_essence,
            "esc_tete_de_poteau": esc_tete_de_poteau,
            "esc_poteaux_depart": esc_poteaux_depart,
            "pose_sold": pose_sold,
            "pose_amount": pose_amount,
            "parse_warning": parse_warning,
        }
        if self.debug:
            data["debug"] = [
                f"devis_annee_mois={devis_annee_mois}",
                f"devis_type={devis_type}",
                f"devis_num={devis_num}",
                f"ref_affaire={ref_affaire}",
                f"client_nom={client_details['nom']}",
                f"client_adresse1={client_details['adresse1']}",
                f"client_adresse2={client_details['adresse2']}",
                f"client_cp={client_details['cp']}",
                f"client_ville={client_details['ville']}",
                f"client_tel={client_details['tel']}",
                f"client_email={client_details['email']}",
                f"client_contact={client_details['contact']}",
                f"commercial_nom={commercial_details['nom']}",
                f"commercial_tel={commercial_details['tel']}",
                f"commercial_email={commercial_details['email']}",
                f"fourniture_ht={fourniture_ht}",
                f"prestations_ht={prestations_ht}",
                f"total_ht={total_ht}",
                f"pose_sold={pose_sold}",
                f"pose_amount={pose_amount}",
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

    def _find_amount_by_label(self, lines, pattern):
        regex = re.compile(pattern, re.IGNORECASE)
        for line in lines:
            match = regex.search(line)
            if match:
                return self._normalize_amount(match.group(1))
        return ""

    def _extract_amount(self, text):
        match = AMOUNT_RE.search(text)
        if not match:
            return ""
        return self._normalize_amount(match.group(1))

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
            match = SRX_RE.search(line.replace(" ", ""))
            if match:
                yymm = match.group("yymm")
                num = match.group("num")
                return yymm, num, match.group("type")
        return None

    def _find_ref_affaire(self, lines):
        for idx, line in enumerate(lines):
            if line.strip().lower().startswith("réf affaire"):
                parts = line.split(":", 1)
                if len(parts) > 1 and parts[1].strip():
                    return parts[1].strip()
                for next_idx in range(idx + 1, len(lines)):
                    if lines[next_idx].strip():
                        return lines[next_idx].strip()
                return ""
        return ""

    def _find_client_details(self, lines):
        code_index = None
        for idx, line in enumerate(lines):
            if "code client" in line.lower():
                code_index = idx
                break
        if code_index is None:
            return {
                "nom": "",
                "adresse1": "",
                "adresse2": "",
                "cp": "",
                "ville": "",
                "tel": "",
                "email": "",
                "contact": "",
            }
        client_nom = ""
        for prev in range(code_index - 1, -1, -1):
            if lines[prev].strip():
                client_nom = lines[prev].strip()
                break
        address_lines = []
        for idx in range(code_index + 1, len(lines)):
            line = lines[idx].strip()
            if not line:
                continue
            lowered = line.lower()
            if lowered.startswith("tél") or lowered.startswith("tel") or lowered.startswith("fax"):
                break
            if "contact commercial" in lowered:
                break
            address_lines.append(line)
        contact, address_lines = self._extract_contact(address_lines)
        adresse1, adresse2, cp, ville = self._split_address_lines(address_lines)
        tel = self._find_phone(lines[code_index : code_index + 6])
        email = self._find_email(lines[code_index : code_index + 6])
        return {
            "nom": client_nom,
            "adresse1": adresse1,
            "adresse2": adresse2,
            "cp": cp,
            "ville": ville,
            "tel": tel,
            "email": email,
            "contact": contact,
        }

    def _extract_contact(self, lines):
        filtered = []
        contact = ""
        for line in lines:
            match = re.search(r"contact\s*:?\s*(.+)", line, re.IGNORECASE)
            if match and not contact:
                contact = match.group(1).strip()
                continue
            filtered.append(line)
        return contact, filtered

    def _split_address_lines(self, address_lines):
        cp = ""
        ville = ""
        remaining = []
        for line in address_lines:
            match = CP_VILLE_RE.search(line)
            if match:
                cp = match.group(1)
                ville = match.group(2).strip()
                prefix = line[: match.start()].strip()
                if prefix:
                    remaining.append(prefix)
            else:
                remaining.append(line)
        adresse1 = remaining[0] if remaining else ""
        adresse2 = " ".join(remaining[1:]) if len(remaining) > 1 else ""
        return adresse1, adresse2, cp, ville

    def _find_commercial_details(self, lines):
        for idx, line in enumerate(lines):
            lowered = line.lower()
            if "contact commercial" in lowered:
                before = line.split("contact commercial", 1)[0].strip(" :-")
                name = ""
                if before and LETTER_RE.search(before):
                    name = before.strip()
                else:
                    for prev in range(idx - 1, -1, -1):
                        if lines[prev].strip():
                            name = lines[prev].strip()
                            break
                search_start = max(idx - 2, 0)
                search_lines = lines[search_start : idx + 3]
                return {
                    "nom": name,
                    "tel": self._find_phone(search_lines),
                    "email": self._find_email(search_lines),
                }
        return {"nom": "", "tel": "", "email": ""}

    def _find_phone(self, lines):
        for line in lines:
            match = PHONE_RE.search(line)
            if match:
                return match.group(0).strip()
        return ""

    def _find_email(self, lines):
        for line in lines:
            match = EMAIL_RE.search(line)
            if match:
                return match.group(0).strip()
        return ""

    def _find_modele(self, lines):
        for line in lines:
            match = re.search(r"-\s*Mod[eè]le\s*:\s*(.+)", line, re.IGNORECASE)
            if match:
                return match.group(1).strip()
        return ""

    def _find_marche(self, lines):
        for idx, line in enumerate(lines):
            match = re.search(r"-\s*Marche\s*:\s*(.+)", line, re.IGNORECASE)
            if match:
                value = match.group(1).strip()
                if re.search(r"\b[eé]paisseur\b", value, re.IGNORECASE):
                    continue
                if self._has_recent_finition(lines, idx):
                    return value
        return ""

    def _extract_essence(self, finition_marches: str) -> str:
        if not finition_marches:
            return ""
        parts = finition_marches.split("-", 1)
        essence = parts[0].strip()
        if len(essence) < 3 or not LETTER_RE.search(essence):
            return ""
        return essence

    def _find_tete_poteau(self, lines):
        for line in lines:
            if re.search(r"-\s*Poteau\s*:", line, re.IGNORECASE) and "(TPA)" in line:
                return "TPA"
        return ""

    def _find_poteaux_depart(self, lines):
        for line in lines:
            match = re.search(r"-\s*Poteau\s*:\s*(.+)", line, re.IGNORECASE)
            if match:
                value = match.group(1).strip()
                value = re.sub(r"\([^)]*\)", "", value).strip()
                return value
        return ""

    def _find_pose_details(self, lines):
        pose_amount = ""
        pose_sold = False
        for line in lines:
            if "pose au" in line.lower():
                matches = EURO_AMOUNT_RE.findall(line)
                if matches:
                    pose_sold = True
                    pose_amount = self._normalize_amount(matches[-1])
        return pose_sold, pose_amount

    def _has_recent_finition(self, lines, idx):
        start = max(idx - 6, 0)
        for prev in range(idx - 1, start - 1, -1):
            if "FINITION" in lines[prev].upper():
                return True
        return False
