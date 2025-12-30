from __future__ import annotations

import re
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Dict, List, Optional

import pdfplumber

from . import rules, sanitize


@dataclass
class DevisData:
    source_pdf: str
    devis_num_complet: str = ""
    ref_affaire: str = ""
    client_nom: str = ""
    client_contact: str = ""
    client_adresse1: str = ""
    client_adresse2: str = ""
    client_cp: str = ""
    client_ville: str = ""
    client_tel: str = ""
    client_email: str = ""
    commercial_nom: str = ""
    commercial_tel: str = ""
    commercial_tel2: str = ""
    commercial_email: str = ""
    fourniture_ht: str = ""
    prestations_ht: str = ""
    total_ht: str = ""
    esc_gamme: str = ""
    esc_essence: str = ""
    esc_main_courante: str = ""
    esc_main_courante_scellement: str = ""
    esc_nez_de_marches: str = ""
    esc_finition_marches: str = ""
    esc_finition_structure: str = ""
    esc_finition_mains_courante: str = ""
    esc_finition_contremarche: str = ""
    esc_finition_rampe: str = ""
    esc_tete_de_poteau: str = ""
    esc_poteaux_depart: str = ""
    esc_section_remplissage_garde_corps_rampant: str = ""
    esc_section_remplissage_garde_corps_etage: str = ""
    esc_remplissage_garde_corps_soubassement: str = ""
    pose_sold: bool = False
    pose_amount: str = ""
    parse_warning: str = ""


@dataclass
class ParseResult:
    data: DevisData
    has_contremarches: bool = False
    structure_type: str = ""

    def to_dict(self) -> Dict[str, object]:
        return asdict(self.data)


class DevisParser:
    def __init__(self, pdf_path: Path):
        self.pdf_path = Path(pdf_path)
        self.lines: List[str] = []
        self.result = ParseResult(DevisData(source_pdf=str(self.pdf_path)))
        self.warnings: List[str] = []

    def parse(self) -> ParseResult:
        self.lines = self._extract_lines()
        self._parse_identifiers()
        self._parse_reference()
        self._parse_client_block()
        self._parse_commercial_block()
        self._parse_client_email_fallback()
        self._parse_amounts()
        self._parse_pose()
        self._parse_technical_details()
        self.result.data.parse_warning = " | ".join(self.warnings)
        return self.result

    def _extract_lines(self) -> List[str]:
        collected: List[str] = []
        with pdfplumber.open(self.pdf_path) as pdf:
            for page in pdf.pages:
                text = page.extract_text() or ""
                for raw_line in text.splitlines():
                    normalized = sanitize.normalize_line(raw_line)
                    if normalized:
                        collected.append(normalized)
        return collected

    def _parse_identifiers(self) -> None:
        match_name = rules.SRX_PATTERN.search(self.pdf_path.name)
        if match_name:
            self.result.data.devis_num_complet = match_name.group(0)
        else:
            joined = " ".join(self.lines)
            match_line = rules.SRX_PATTERN.search(joined)
            if match_line:
                self.result.data.devis_num_complet = match_line.group(0)
        if not self.result.data.devis_num_complet:
            self.warnings.append("Numéro de devis introuvable")

    def _parse_reference(self) -> None:
        for idx, line in enumerate(self.lines):
            normalized = sanitize.normalize_for_match(line)
            if normalized.startswith("ref affaire") or normalized.startswith("rf affaire"):
                value = line.split(":", 1)[1].strip() if ":" in line else ""
                if not value and idx + 1 < len(self.lines):
                    value = self.lines[idx + 1].strip()
                self.result.data.ref_affaire = value
                return

    def _parse_client_block(self) -> None:
        anchor_index = self._find_line_index("code client")
        if anchor_index is None:
            self.warnings.append("Ligne 'Code client' absente")
            return

        self.result.data.client_nom = self._find_client_name(anchor_index)

        address_lines: List[str] = []
        for raw_line in self.lines[anchor_index + 1 :]:
            normalized = sanitize.normalize_line(raw_line)
            low = sanitize.normalize_for_match(normalized)
            if low.startswith("contact commercial"):
                break
            if self.result.data.client_nom and sanitize.normalize_for_match(normalized) == sanitize.normalize_for_match(
                self.result.data.client_nom
            ):
                continue
            if low.startswith("tel") or low.startswith("te l") or low.startswith("fax") or low.startswith("tl"):
                numbers = sanitize.extract_phone_numbers(normalized)
                for number in numbers:
                    if not sanitize.is_riaux_line(number):
                        self.result.data.client_tel = sanitize.choose_first(
                            [self.result.data.client_tel, number]
                        )
                break
            if sanitize.is_riaux_line(normalized):
                if not self.result.data.client_contact and self._is_contact_line(normalized):
                    self.result.data.client_contact = normalized
                continue
            address_lines.append(normalized)

        self._fill_address_fields(address_lines)

        if not self.result.data.client_cp:
            for raw_line in self.lines[anchor_index + 1 :]:
                normalized = sanitize.normalize_line(raw_line)
                if sanitize.normalize_for_match(normalized).startswith("contact commercial"):
                    break
                if sanitize.is_riaux_line(normalized):
                    continue
                match_cp = rules.POSTAL_CODE_PATTERN.search(normalized)
                if match_cp:
                    self.result.data.client_cp = match_cp.group(1)
                    after_cp = sanitize.normalize_line(normalized[match_cp.end() :]).strip()
                    self.result.data.client_ville = after_cp.upper() if after_cp else ""
                    break

    def _find_client_name(self, anchor_index: int) -> str:
        for offset in range(anchor_index - 1, -1, -1):
            candidate = self.lines[offset].strip()
            normalized = sanitize.normalize_for_match(candidate)
            if not candidate:
                continue
            if any(marker in normalized for marker in rules.CLIENT_NAME_SKIP):
                continue
            return candidate
        for line in self.lines[anchor_index + 1 : anchor_index + 4]:
            candidate = line.strip()
            normalized = sanitize.normalize_for_match(candidate)
            if not candidate:
                continue
            if any(marker in normalized for marker in rules.CLIENT_NAME_SKIP):
                continue
            return candidate
        return ""

    def _fill_address_fields(self, address_lines: List[str]) -> None:
        client_contact = ""
        filtered_lines: List[str] = []
        for line in address_lines:
            if not client_contact and self._is_contact_line(line):
                client_contact = line
                continue
            filtered_lines.append(line)

        cp_line_index: Optional[int] = None
        for idx, line in enumerate(filtered_lines):
            match_cp = rules.POSTAL_CODE_PATTERN.search(line)
            if match_cp:
                self.result.data.client_cp = match_cp.group(1)
                after_cp = sanitize.normalize_line(line[match_cp.end() :]).strip()
                self.result.data.client_ville = after_cp.upper() if after_cp else ""
                cp_line_index = idx
                break

        if filtered_lines:
            self.result.data.client_adresse1 = filtered_lines[0]
        if len(filtered_lines) > 1:
            second_line = filtered_lines[1]
            if cp_line_index is None or cp_line_index != 1:
                self.result.data.client_adresse2 = second_line
            elif len(filtered_lines) > 2:
                self.result.data.client_adresse2 = filtered_lines[2]

        if client_contact:
            self.result.data.client_contact = client_contact

    def _find_line_index(self, needle: str) -> Optional[int]:
        normalized_needle = sanitize.normalize_for_match(needle)
        for idx, line in enumerate(self.lines):
            if normalized_needle in sanitize.normalize_for_match(line):
                return idx
        return None

    def _is_contact_line(self, line: str) -> bool:
        normalized = sanitize.normalize_for_match(line)
        return bool(re.search(r"\b(m\.?|mme|mr|madame|monsieur)\b", normalized))

    def _parse_commercial_block(self) -> None:
        anchor_index = self._find_line_index("contact commercial")
        if anchor_index is None:
            return
        for line in self.lines[anchor_index + 1 :]:
            normalized = sanitize.normalize_line(line)
            normalized_match = sanitize.normalize_for_match(normalized)
            if not self.result.data.commercial_nom:
                if rules.POSTAL_CODE_PATTERN.search(normalized):
                    continue
                if normalized:
                    self.result.data.commercial_nom = normalized
                    continue
            if self.result.data.commercial_email and self.result.data.commercial_tel2:
                break
            email = sanitize.extract_email(normalized)
            if email and not self.result.data.commercial_email:
                self.result.data.commercial_email = email
            numbers = sanitize.extract_phone_numbers(normalized)
            for number in numbers:
                if not self.result.data.commercial_tel:
                    self.result.data.commercial_tel = number
                elif not self.result.data.commercial_tel2 and number != self.result.data.commercial_tel:
                    self.result.data.commercial_tel2 = number
            if "validite" in normalized_match or "valide" in normalized_match:
                break

    def _parse_client_email_fallback(self) -> None:
        if self.result.data.client_email:
            return
        for line in self.lines:
            email = sanitize.extract_email(line)
            if not email or sanitize.is_riaux_line(email):
                continue
            if self.result.data.commercial_email and email == self.result.data.commercial_email:
                continue
            self.result.data.client_email = email
            break

    def _parse_amounts(self) -> None:
        mapping = {
            "fourniture_ht": "prix de la fourniture ht",
            "prestations_ht": "prix prestations et services ht",
            "total_ht": "total hors taxe",
        }
        for key, label in mapping.items():
            value = self._find_amount(label)
            if value:
                setattr(self.result.data, key, value)

    def _find_amount(self, label: str) -> str:
        normalized_label = sanitize.normalize_for_match(label)
        for line in self.lines:
            normalized_line = sanitize.normalize_for_match(line)
            if normalized_label in normalized_line:
                amount = sanitize.extract_amount(line)
                if amount:
                    return amount
        return ""

    def _parse_pose(self) -> None:
        section_started = False
        for line in self.lines:
            normalized = sanitize.normalize_for_match(line)
            if normalized.startswith("prestation"):
                section_started = True
                continue
            if section_started:
                if any(title in normalized for title in rules.SECTION_TITLES if title != "prestations"):
                    break
                if "pose" in normalized:
                    self.result.data.pose_sold = True
        if self.result.data.pose_sold and not self.result.data.pose_amount:
            self.result.data.pose_amount = self.result.data.prestations_ht

    def _parse_technical_details(self) -> None:
        essence_candidates: List[str] = []
        for raw in self.lines:
            normalized = sanitize.normalize_for_match(raw)
            compact = normalized.replace(" ", "")
            if "-modele" in compact:
                self.result.data.esc_gamme = raw.split(":", 1)[1].strip() if ":" in raw else raw
            if "contremarche" in normalized:
                if "sans" in normalized:
                    self.result.has_contremarches = False
                else:
                    self.result.has_contremarches = True
                    if not self.result.data.esc_finition_contremarche:
                        after = raw.split(":", 1)[1].strip() if ":" in raw else raw
                        self.result.data.esc_finition_contremarche = after
            if "limon decoupe" in normalized:
                self.result.structure_type = "limon_decoupe"
            elif "limon centrale" in normalized or "limon central" in normalized:
                self.result.structure_type = "limon_centrale"
            elif "cremaill" in normalized:
                self.result.structure_type = "cremaillere"
            elif "limon" in normalized and not self.result.structure_type:
                self.result.structure_type = "limon"
            if "poteau" in normalized:
                content = raw.split(":", 1)[1].strip() if ":" in raw else raw
                if "tete" in normalized:
                    self.result.data.esc_tete_de_poteau = content
                elif not self.result.data.esc_finition_structure:
                    self.result.data.esc_finition_structure = content
            if "poteau de depart" in normalized or "poteaux de depart" in normalized:
                after = raw.split(":", 1)[1].strip() if ":" in raw else raw
                self.result.data.esc_poteaux_depart = after
            if "main courante" in normalized:
                content = raw.split(":", 1)[1].strip() if ":" in raw else raw
                if "scel" in normalized and not self.result.data.esc_main_courante_scellement:
                    self.result.data.esc_main_courante_scellement = content
                if not self.result.data.esc_main_courante:
                    self.result.data.esc_main_courante = content
                if "finition" in normalized or "hete" in normalized or "hetre" in normalized:
                    if not self.result.data.esc_finition_mains_courante:
                        self.result.data.esc_finition_mains_courante = content
            if normalized.startswith("rampe") or normalized.startswith("-rampe"):
                content = raw.split(":", 1)[1].strip() if ":" in raw else raw
                if not self.result.data.esc_finition_rampe:
                    self.result.data.esc_finition_rampe = content
            if "remplissage" in normalized:
                content = raw.split(":", 1)[1].strip() if ":" in raw else raw
                if "soubassement" in normalized and not self.result.data.esc_remplissage_garde_corps_soubassement:
                    self.result.data.esc_remplissage_garde_corps_soubassement = content
                elif "ramp" in normalized and not self.result.data.esc_section_remplissage_garde_corps_rampant:
                    self.result.data.esc_section_remplissage_garde_corps_rampant = content
                elif "etage" in normalized and not self.result.data.esc_section_remplissage_garde_corps_etage:
                    self.result.data.esc_section_remplissage_garde_corps_etage = content
                elif not self.result.data.esc_section_remplissage_garde_corps_rampant:
                    self.result.data.esc_section_remplissage_garde_corps_rampant = content
                elif not self.result.data.esc_section_remplissage_garde_corps_etage:
                    self.result.data.esc_section_remplissage_garde_corps_etage = content
            if "soubassement" in normalized and "remplissage" not in normalized:
                content = raw.split(":", 1)[1].strip() if ":" in raw else raw
                if not self.result.data.esc_remplissage_garde_corps_soubassement:
                    self.result.data.esc_remplissage_garde_corps_soubassement = content
            if "nez de marche" in normalized and not self.result.data.esc_nez_de_marches:
                self.result.data.esc_nez_de_marches = raw.split(":", 1)[1].strip() if ":" in raw else raw
            if "finition" in normalized and "marche" in normalized and not self.result.data.esc_finition_marches:
                self.result.data.esc_finition_marches = raw.split(":", 1)[1].strip() if ":" in raw else raw
            if "finition" in normalized and "rampe" in normalized and not self.result.data.esc_finition_rampe:
                self.result.data.esc_finition_rampe = raw.split(":", 1)[1].strip() if ":" in raw else raw
            for wood in rules.WOOD_KEYWORDS:
                if wood in normalized:
                    essence_candidates.append(raw)
                    break

        if essence_candidates:
            normalized_first = sanitize.normalize_for_match(essence_candidates[0])
            for key, label in rules.WOOD_LABELS.items():
                if key in normalized_first:
                    self.result.data.esc_essence = label
                    break
            if not self.result.data.esc_essence:
                self.result.data.esc_essence = essence_candidates[0]


def parse_devis(pdf_path: str | Path) -> ParseResult:
    parser = DevisParser(Path(pdf_path))
    return parser.parse()
