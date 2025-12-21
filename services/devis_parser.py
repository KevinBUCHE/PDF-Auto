import re
from decimal import Decimal, InvalidOperation
from pathlib import Path

import pdfplumber


AMOUNT_RE = re.compile(r"([0-9][0-9\s\u202f]*[\.,][0-9]{2})")
SRX_RE = re.compile(r"SRX(?P<yymm>\d{4})(?P<type>[A-Z]{3})(?P<num>\d{6})")
LETTER_RE = re.compile(r"[A-Za-zÀ-ÖØ-öø-ÿ]")
EMAIL_RE = re.compile(r"[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}", re.IGNORECASE)
PHONE_RE = re.compile(r"\b(?:\+33|0)\s?\d(?:[\s.-]?\d{2}){4}\b")
CP_VILLE_RE = re.compile(r"\b(\d{5})\s+(.+)")
ESSENCE_RE = re.compile(
    r"\b(ch[eê]ne|h[eê]tre|fr[eê]ne|sapin|pin|hêtre|chêne)\b", re.IGNORECASE
)


class DevisParser:
    def __init__(self, debug: bool = False):
        self.debug = debug

    def parse(self, path: Path) -> dict:
        text = self._extract_text(path)
        lines = [line.strip() for line in text.splitlines() if line.strip()]
        warnings = []
        if not lines:
            warnings.append("Texte du devis illisible ou vide.")

        fourniture_ht = self._find_amount_by_label(
            lines, r"PRIX DE LA FOURNITURE HT\s*:\s*([\d\s]+,\d{2})"
        )
        prestations_ht = self._find_amount_by_label(
            lines, r"PRIX PRESTATIONS ET SERVICES HT\s*:\s*([\d\s]+,\d{2})"
        )
        total_ht = self._find_amount_by_label(
            lines, r"TOTAL HORS TAXE\s*:\s*([\d\s]+,\d{2})"
        )
        if not prestations_ht:
            services_ht = self._find_amount_by_label(
                lines, r"PRIX.*SERVICES.*HT\s*:\s*([\d\s]+,\d{2})"
            )
            eco_ht = self._find_amount_by_label(
                lines, r"PRIX.*ECO.*HT\s*:\s*([\d\s]+,\d{2})"
            )
            prestations_ht = self._sum_amounts([services_ht, eco_ht])
            if prestations_ht and not fourniture_ht:
                warnings.append(
                    "Fourniture absente: prestations calculées depuis SERVICES/ECO."
                )

        devis_match = self._find_devis_reference(lines)
        devis_annee_mois = devis_match[0] if devis_match else ""
        devis_num = devis_match[1] if devis_match else ""
        devis_type = devis_match[2] if devis_match else ""

        ref_affaire = self._find_ref_affaire(lines)
        client_details = self._find_client_details(lines)
        commercial_details = self._find_commercial_details(lines)
        if not devis_num:
            warnings.append("Devis SRX introuvable.")
        if not ref_affaire:
            warnings.append("Réf affaire introuvable.")
        if not client_details["nom"]:
            warnings.append("Client introuvable (ancre 'Code client :').")
        esc_gamme = self._find_modele(lines)
        finitions = self._extract_finitions(lines)
        esc_finition_marches = finitions.get("marche", "")
        esc_finition_structure = finitions.get("structure", "")
        esc_finition_mains_courante = finitions.get("main_courante", "")
        esc_finition_contremarche = finitions.get("contremarche", "")
        esc_finition_rampe = finitions.get("rampe", "")
        esc_main_courante, esc_main_courante_scellement = self._find_main_courante(lines)
        esc_nez_de_marches = self._find_nez_de_marches(lines)
        esc_essence = self._extract_essence(
            [
                esc_finition_marches,
                esc_finition_structure,
                esc_finition_mains_courante,
                esc_finition_contremarche,
                esc_finition_rampe,
            ]
        )
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
            "esc_finition_structure": esc_finition_structure,
            "esc_finition_mains_courante": esc_finition_mains_courante,
            "esc_finition_contremarche": esc_finition_contremarche,
            "esc_finition_rampe": esc_finition_rampe,
            "esc_essence": esc_essence,
            "esc_main_courante": esc_main_courante,
            "esc_main_courante_scellement": esc_main_courante_scellement,
            "esc_nez_de_marches": esc_nez_de_marches,
            "esc_tete_de_poteau": esc_tete_de_poteau,
            "esc_poteaux_depart": esc_poteaux_depart,
            "pose_sold": pose_sold,
            "pose_amount": pose_amount,
            "parse_warning": " ".join(warnings).strip(),
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
                f"esc_finition_structure={esc_finition_structure}",
                f"esc_finition_mains_courante={esc_finition_mains_courante}",
                f"esc_finition_contremarche={esc_finition_contremarche}",
                f"esc_finition_rampe={esc_finition_rampe}",
                f"esc_essence={esc_essence}",
                f"esc_main_courante={esc_main_courante}",
                f"esc_main_courante_scellement={esc_main_courante_scellement}",
                f"esc_nez_de_marches={esc_nez_de_marches}",
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

    def _sum_amounts(self, amounts: list[str]) -> str:
        values = [amount for amount in amounts if amount]
        if not values:
            return ""
        total = Decimal("0")
        for value in values:
            normalized = value.replace(" ", "").replace("\u202f", "").replace(",", ".")
            try:
                total += Decimal(normalized)
            except InvalidOperation:
                continue
        return self._normalize_amount(f"{total:.2f}")

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
                yymm = match.group("yymm")
                num = match.group("num")
                return yymm, num, match.group("type")
        return None

    def _find_ref_affaire(self, lines):
        for idx, line in enumerate(lines):
            if line.strip().lower().startswith("réf affaire"):
                parts = line.split(":", 1)
                value = ""
                if len(parts) > 1 and parts[1].strip():
                    value = parts[1].strip()
                else:
                    for next_idx in range(idx + 1, len(lines)):
                        if lines[next_idx].strip():
                            value = lines[next_idx].strip()
                            break
                if not value:
                    return ""
                if value.lower().startswith("réf affaire"):
                    value = value.split(":", 1)[-1].strip()
                return value
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
            candidate = lines[prev].strip()
            if not candidate:
                continue
            lowered = candidate.lower()
            if (
                lowered.startswith("date du devis")
                or lowered.startswith("réf affaire")
                or "devis" in lowered
            ):
                continue
            client_nom = candidate
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
            if self._is_legal_noise(line):
                continue
            if "vaugarny" in lowered:
                continue
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

    def _is_legal_noise(self, line: str) -> bool:
        lowered = line.lower()
        keywords = (
            "sas",
            "sarl",
            "rcs",
            "naf",
            "siret",
            "capital",
            "eur",
        )
        return any(keyword in lowered for keyword in keywords)

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
        cp_candidates = []
        for idx, line in enumerate(address_lines):
            match = CP_VILLE_RE.search(line)
            if match:
                cp_candidates.append(
                    {
                        "cp": match.group(1),
                        "ville": match.group(2).strip(),
                        "prefix": line[: match.start()].strip(),
                        "prev_line": address_lines[idx - 1].strip() if idx > 0 else "",
                        "index": idx,
                    }
                )
                continue
            remaining.append(line)
        if cp_candidates:
            cp_choice = self._choose_cp_ville(cp_candidates)
            cp = cp_choice["cp"]
            ville = cp_choice["ville"]
            candidate_by_index = {candidate["index"]: candidate for candidate in cp_candidates}
            rebuilt = []
            for idx, line in enumerate(address_lines):
                candidate = candidate_by_index.get(idx)
                if candidate:
                    if candidate["prefix"]:
                        rebuilt.append(candidate["prefix"])
                    continue
                rebuilt.append(line)
            remaining = rebuilt
        adresse1 = remaining[0] if remaining else ""
        adresse2 = " ".join(remaining[1:]) if len(remaining) > 1 else ""
        return adresse1, adresse2, cp, ville

    def _choose_cp_ville(self, candidates):
        for candidate in candidates:
            if re.search(r"\d+\s+.+", candidate["prev_line"]):
                return candidate
        return candidates[-1]

    def _find_commercial_details(self, lines):
        for idx, line in enumerate(lines):
            lowered = line.lower()
            if "contact commercial" in lowered:
                name = ""
                match = re.search(r"contact commercial\s*:\s*(.+)", line, re.IGNORECASE)
                if match:
                    name = match.group(1).strip()
                for prev in range(idx - 1, -1, -1):
                    previous = lines[prev].strip()
                    if not previous:
                        continue
                    if "contact commercial" in previous.lower():
                        continue
                    if not name:
                        name = previous
                    break
                if name.lower().startswith("contact commercial"):
                    name = ""
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

    def _extract_finitions(self, lines):
        finitions = {}
        in_finition = False
        for line in lines:
            if "FINITION" in line.upper():
                in_finition = True
                continue
            if in_finition and not line.strip().startswith("-"):
                if finitions:
                    break
                continue
            if not in_finition:
                continue
            match = re.search(r"-\s*([^:]+)\s*:\s*(.+)", line)
            if not match:
                continue
            label = match.group(1).strip().lower()
            value = match.group(2).strip()
            if label.startswith("marche"):
                finitions["marche"] = value
            elif label.startswith("structure"):
                finitions["structure"] = value
            elif label.startswith("main courante"):
                finitions["main_courante"] = value
            elif label.startswith("contremarche"):
                finitions["contremarche"] = value
            elif label.startswith("rampe"):
                finitions["rampe"] = value
        return finitions

    def _extract_essence(self, values: list[str]) -> str:
        for value in values:
            if not value:
                continue
            match = ESSENCE_RE.search(value)
            if match:
                return match.group(0)
        for value in values:
            if not value:
                continue
            if re.search(r"\b[eé]paisseur\b", value, re.IGNORECASE):
                continue
            parts = value.split("-", 1)
            essence = parts[0].strip()
            if len(essence) >= 3 and LETTER_RE.search(essence):
                return essence
        return ""

    def _find_main_courante(self, lines):
        for line in lines:
            match = re.search(r"-\s*Main\s+courante\s*:\s*(.+)", line, re.IGNORECASE)
            if match:
                value = match.group(1).strip()
                scellement = ""
                if "scellement" in value.lower():
                    scellement = value
                return value, scellement
        return "", ""

    def _find_nez_de_marches(self, lines):
        for line in lines:
            match = re.search(r"-\s*Nez\s+de\s+marche[s]?\s*:\s*(.+)", line, re.IGNORECASE)
            if match:
                return match.group(1).strip()
        return ""

    def _find_tete_poteau(self, lines):
        for line in lines:
            if "TPA" in line and re.search(r"Poteau", line, re.IGNORECASE):
                return "TPA"
        return ""

    def _find_poteaux_depart(self, lines):
        for line in lines:
            if re.search(r"poteau[x]?\s+de\s+d[eé]part", line, re.IGNORECASE):
                match = re.search(r":\s*(.+)", line)
                if match:
                    value = match.group(1).strip()
                    value = re.sub(r"\([^)]*\)", "", value).strip()
                    return value
        return "" 

    def _find_pose_details(self, lines):
        pose_amount = ""
        pose_sold = False
        saw_prestations = False
        for line in lines:
            if "PRESTATIONS" in line.upper():
                saw_prestations = True
                continue
            if not saw_prestations:
                continue
            if re.search(r"\bpose\b", line, re.IGNORECASE):
                amount = self._extract_pose_amount(line)
                if amount:
                    pose_sold = True
                    pose_amount = amount
                    break
        return pose_sold, pose_amount

    def _extract_pose_amount(self, line: str) -> str:
        euro_matches = re.findall(
            r"([0-9][0-9\s\u202f]*[\.,][0-9]{2})\s*€", line
        )
        if euro_matches:
            return self._normalize_amount(euro_matches[-1])
        matches = AMOUNT_RE.findall(line)
        if not matches:
            return ""
        for match in reversed(matches):
            normalized = self._normalize_amount(match)
            if normalized not in {"1,00", "1.00"}:
                return normalized
        return ""
