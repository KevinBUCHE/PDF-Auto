import re
from pathlib import Path
from typing import List, Tuple

import pdfplumber

AMOUNT_RE = re.compile(r"([0-9][0-9\s\u202f]*[\.,][0-9]{2})")
SRX_RE = re.compile(r"SRX(\d{4})AFF(\d{1,6})", re.IGNORECASE)
DEVIS_RE = re.compile(r"(DEVIS\s*N[°o]?\s*SRX[^\s]*)", re.IGNORECASE)
DATE_RE = re.compile(r"\b\d{1,2}/\d{1,2}/\d{2,4}\b")
LETTER_RE = re.compile(r"[A-Za-zÀ-ÖØ-öø-ÿ]")
BANNED_CLIENT_TOKENS = ["devis", "réalisé par", "riaux", "vaugarny", "bazouges", "35560"]
STOP_CLIENT_TOKENS = [
    "tel",
    "fax",
    "mail",
    "contact commercial",
    "validité",
    "désignation",
]


class DevisParser:
    def __init__(self, debug: bool = False):
        self.debug = debug

    def parse(self, path: Path) -> dict:
        text = self._extract_text(path)
        lines = [line.rstrip() for line in text.splitlines()]
        data = self.parse_lines(lines)
        return data

    def parse_lines(self, lines: List[str]) -> dict:
        normalized_lines = [line.strip() for line in lines if line and line.strip()]
        parse_warnings = []
        if not normalized_lines:
            parse_warnings.append("Texte du devis illisible ou vide.")

        fourniture_ht = self._find_amount_before(normalized_lines, "PRIX DE LA FOURNITURE HT")
        prestations_ht = self._find_amount_before(
            normalized_lines, "PRIX PRESTATIONS ET SERVICES HT"
        )
        total_ht = self._find_amount_before(normalized_lines, "TOTAL HORS TAXE")

        devis_reference, devis_num, devis_type = self._find_devis_reference(normalized_lines)
        ref_affaire = self._find_ref_affaire(normalized_lines)
        client_nom, client_adresse = self._find_client(normalized_lines)
        commercial_nom = self._find_commercial(normalized_lines)
        esc_gamme = self._find_modele(normalized_lines)
        contremarche_sans, contremarche_avec = self._find_contremarche(normalized_lines)
        structure_type = self._find_structure(normalized_lines)
        esc_finition_marches, esc_essence = self._find_marche(normalized_lines)
        finish_contremarche = self._find_contremarche_finition(normalized_lines)
        finish_structure, essence_structure = self._find_structure_finition(normalized_lines)
        finish_main_courante, essence_main_courante = self._find_main_courante(normalized_lines)
        esc_essence = esc_essence or essence_structure or essence_main_courante
        esc_tete_de_poteau, esc_poteaux_depart = self._find_poteau_info(normalized_lines)
        (
            remplissage_rampant,
            remplissage_etage,
            remplissage_soubassement,
            remplissage_warning,
        ) = self._find_remplissage(normalized_lines)
        if remplissage_warning:
            parse_warnings.append(remplissage_warning)

        parse_warning_text = " | ".join(parse_warnings)

        data = {
            "lines": normalized_lines,
            "fourniture_ht": fourniture_ht,
            "prestations_ht": prestations_ht,
            "total_ht": total_ht,
            "devis_annee_mois": devis_reference,
            "devis_num": devis_num,
            "devis_type": devis_type,
            "ref_affaire": ref_affaire,
            "client_nom": client_nom,
            "client_adresse": client_adresse,
            "commercial_nom": commercial_nom,
            "esc_gamme": esc_gamme,
            "esc_finition_marches": esc_finition_marches,
            "esc_finition_contremarche": finish_contremarche,
            "esc_finition_structure": finish_structure,
            "esc_finition_mains_courante": finish_main_courante,
            "esc_essence": esc_essence,
            "esc_tete_de_poteau": esc_tete_de_poteau,
            "esc_poteaux_depart": esc_poteaux_depart,
            "contremarche_sans": contremarche_sans,
            "contremarche_avec": contremarche_avec,
            "structure_type": structure_type,
            "remplissage_rampant": remplissage_rampant,
            "remplissage_etage": remplissage_etage,
            "remplissage_soubassement": remplissage_soubassement,
            "parse_warning": parse_warning_text,
        }
        if self.debug:
            data["debug"] = [
                f"devis_annee_mois={devis_reference}",
                f"devis_type={devis_type}",
                f"devis_num={devis_num}",
                f"ref_affaire={ref_affaire}",
                f"client_nom={client_nom}",
                f"client_adresse={client_adresse}",
                f"commercial_nom={commercial_nom}",
                f"fourniture_ht={fourniture_ht}",
                f"prestations_ht={prestations_ht}",
                f"total_ht={total_ht}",
                f"esc_gamme={esc_gamme}",
                f"esc_finition_marches={esc_finition_marches}",
                f"esc_finition_contremarche={finish_contremarche}",
                f"esc_finition_structure={finish_structure}",
                f"esc_finition_mains_courante={finish_main_courante}",
                f"esc_essence={esc_essence}",
                f"esc_tete_de_poteau={esc_tete_de_poteau}",
                f"esc_poteaux_depart={esc_poteaux_depart}",
                f"structure_type={structure_type}",
                f"remplissage_rampant={remplissage_rampant}",
                f"remplissage_etage={remplissage_etage}",
                f"remplissage_soubassement={remplissage_soubassement}",
            ]
        return data

    def _extract_text(self, path: Path) -> str:
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

    def _find_amount_before(self, lines, label):
        for idx, line in enumerate(lines):
            if label.lower() in line.lower():
                amount = self._extract_amount(line)
                if amount:
                    return amount
                if idx > 0:
                    amount = self._extract_amount(lines[idx - 1])
                    if amount:
                        return amount
                if idx + 1 < len(lines):
                    amount = self._extract_amount(lines[idx + 1])
                    if amount:
                        return amount
        return ""

    def _normalize_amount(self, value: str) -> str:
        value = value.replace("\u202f", " ")
        value = re.sub(r"\s+", " ", value).strip()
        if "," in value and "." in value:
            value = value.replace(".", "")
        if "." in value:
            value = value.replace(".", ",")
        return value

    def _find_devis_reference(self, lines) -> Tuple[str, str, str]:
        for line in lines:
            match = DEVIS_RE.search(line)
            if match:
                reference = match.group(1).strip()
                srx_match = SRX_RE.search(reference.replace(" ", ""))
                devis_num = ""
                if srx_match:
                    devis_num = srx_match.group(2).zfill(6)
                return reference, devis_num, "AFF"
        return "", "", ""

    def _find_ref_affaire(self, lines):
        for idx, line in enumerate(lines):
            match = re.search(r"réf\s*affaire\s*:?\s*(.*)", line, re.IGNORECASE)
            if match:
                value = match.group(1).strip(" :-")
                if value:
                    return value
                return self._next_non_empty(lines, idx + 1)
        return ""

    def _find_client(self, lines: List[str]) -> Tuple[str, str]:
        for idx, line in enumerate(lines):
            if re.search(r"\bcode\s*client\b", line, re.IGNORECASE):
                name = ""
                address_lines = []
                for next_idx in range(idx + 1, len(lines)):
                    candidate = lines[next_idx].strip()
                    if not candidate:
                        continue
                    if self._is_stop_line(candidate):
                        break
                    if not name:
                        if self._is_banned_client(candidate):
                            continue
                        name = candidate
                        continue
                    address_lines.append(candidate)
                return name, "\n".join(address_lines)
        return "", ""

    def _is_stop_line(self, line: str) -> bool:
        lowered = line.lower()
        return any(token in lowered for token in STOP_CLIENT_TOKENS)

    def _is_banned_client(self, line: str) -> bool:
        lowered = line.lower()
        return any(token in lowered for token in BANNED_CLIENT_TOKENS)

    def _find_commercial(self, lines: List[str]) -> str:
        for idx, line in enumerate(lines):
            if re.search(r"contact\s+commercial", line, re.IGNORECASE):
                return self._next_non_empty(lines, idx + 1)
        return ""

    def _next_non_empty(self, lines: List[str], start_idx: int) -> str:
        for idx in range(start_idx, len(lines)):
            value = lines[idx].strip()
            if value:
                return value
        return ""

    def _find_modele(self, lines):
        for line in lines:
            match = re.search(r"-\s*Mod[eè]le\s*:\s*(.+)", line, re.IGNORECASE)
            if match:
                return match.group(1).strip()
        return ""

    def _find_contremarche(self, lines: List[str]) -> Tuple[bool, bool]:
        for line in lines:
            match = re.search(r"-\s*Contremarche\s*:\s*(.+)", line, re.IGNORECASE)
            if not match:
                continue
            value = match.group(1).strip()
            lowered = value.lower()
            if any(key in lowered for key in ["sans", "aucune", "non"]):
                return True, False
            if value:
                return False, True
        return False, False

    def _find_structure(self, lines: List[str]) -> str:
        for line in lines:
            match = re.search(r"-\s*Structure\s*:\s*(.+)", line, re.IGNORECASE)
            if match:
                value = match.group(1).strip().lower()
                if "crémaill" in value or "cremaill" in value:
                    return "cremaillere"
                if "limon central" in value:
                    return "limon_central"
                if "découp" in value or "decoup" in value:
                    return "limon_decoupe"
                if "limon" in value:
                    return "limon"
        return ""

    def _find_marche(self, lines: List[str]) -> Tuple[str, str]:
        for line in lines:
            match = re.search(r"-\s*Marche\s*:\s*(.+)", line, re.IGNORECASE)
            if match:
                value = match.group(1).strip()
                essence, finition = self._split_essence_finition(value)
                return finition, essence
        return "", ""

    def _find_contremarche_finition(self, lines: List[str]) -> str:
        for line in lines:
            match = re.search(r"-\s*Contremarche\s*:\s*(.+)", line, re.IGNORECASE)
            if match:
                value = match.group(1).strip()
                _, finition = self._split_essence_finition(value)
                return finition
        return ""

    def _find_structure_finition(self, lines: List[str]) -> Tuple[str, str]:
        for line in lines:
            match = re.search(r"-\s*Structure\s*:\s*(.+)", line, re.IGNORECASE)
            if match:
                value = match.group(1).strip()
                essence, finition = self._split_essence_finition(value)
                return finition, essence
        return "", ""

    def _find_main_courante(self, lines: List[str]) -> Tuple[str, str]:
        for line in lines:
            match = re.search(r"main\s*courante\s*:\s*(.+)", line, re.IGNORECASE)
            if match:
                value = match.group(1).strip()
                essence, finition = self._split_essence_finition(value)
                return finition, essence
        return "", ""

    def _split_essence_finition(self, value: str) -> Tuple[str, str]:
        parts = [part.strip() for part in value.split("-", 1)]
        essence = parts[0] if parts else ""
        finition = parts[1] if len(parts) > 1 else ""
        return essence, finition

    def _find_poteau_info(self, lines: List[str]) -> Tuple[str, str]:
        tete = ""
        depart = ""
        for line in lines:
            if "poteau" not in line.lower():
                continue
            content = re.sub(r"^[\-\s]*poteau\s*:?\s*", "", line, flags=re.IGNORECASE).strip()
            if not content:
                continue
            if "(" in content and ")" in content:
                match = re.search(r"\(([^)]+)\)", content)
                if match:
                    tete = match.group(1).strip()
            # remove parenthesis to find departure shape
            without_parenthesis = re.sub(r"\([^)]*\)", "", content).strip()
            if without_parenthesis and not depart:
                depart = without_parenthesis
        return tete, depart

    def _find_remplissage(self, lines: List[str]) -> Tuple[str, str, str, str]:
        rampant = ""
        etage = ""
        soubassement = ""
        warning = ""
        for line in lines:
            match = re.search(
                r"remplissage\s*([\wàâäéèêëîïôöùûüç-]*)\s*:?\s*(.+)", line, re.IGNORECASE
            )
            if not match:
                continue
            zone = match.group(1).lower()
            zone_normalized = (
                zone.replace("é", "e").replace("è", "e").replace("ê", "e").replace("à", "a")
            )
            value = match.group(2).strip()
            if zone_normalized.startswith("ramp"):
                rampant = value
            elif zone_normalized.startswith("etag"):
                etage = value
            elif zone_normalized.startswith("soub"):
                soubassement = value
            else:
                if not rampant:
                    rampant = value
                warning = "Remplissage sans précision affecté aux rampants."
        return rampant, etage, soubassement, warning
