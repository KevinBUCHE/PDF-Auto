from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Sequence

import pdfplumber

from .rules import INTERNAL_ADDRESSES


DEVIS_PATTERN = re.compile(r"SRX[0-9A-Z]+")
REF_AFFAIRE_RE = re.compile(r"r[ée]f affaire", flags=re.IGNORECASE)
CODE_CLIENT_RE = re.compile(r"code client", flags=re.IGNORECASE)
CONTACT_COMMERCIAL_RE = re.compile(r"contact commercial", flags=re.IGNORECASE)
TEL_RE = re.compile(r"t[ée]l", flags=re.IGNORECASE)
CP_VILLE_RE = re.compile(r"\b(?P<cp>\d{5})\s+(?P<city>.+)")
AMOUNT_RE = re.compile(r"([0-9][0-9\s\u202f]*[.,][0-9]{2})")


@dataclass
class ParsedDevis:
    raw_lines: list[str]
    bdc_devis_annee_mois: str = ""
    bdc_ref_affaire: str = ""
    bdc_client_nom: str = ""
    bdc_client_adresse: str = ""
    bdc_client_cp: str = ""
    bdc_client_ville: str = ""
    bdc_commercial_nom: str = ""
    bdc_esc_gamme: str = ""
    bdc_chk_avec_contre_marches: bool = False
    bdc_chk_sans_contre_marches: bool = False
    bdc_structure_checkboxes: dict[str, bool] | None = None
    bdc_esc_tete_de_poteau: str = ""
    bdc_esc_section_remplissage_garde_corps_rampant: str = ""
    bdc_esc_section_remplissage_garde_corps_etage: str = ""
    bdc_esc_remplissage_garde_corps_soubassement: str = ""
    bdc_esc_essence: str = ""
    bdc_esc_finition_marches: str = ""
    bdc_esc_finition_contremarche: str = ""
    bdc_esc_finition_structure: str = ""
    bdc_esc_finition_mains_courante: str = ""
    bdc_montant_fourniture_ht: str = ""
    bdc_montant_pose_ht: str = ""
    pose_vendue: bool = False


class DevisParser:
    """Deterministic parser for SRX devis PDFs based on plain text rules."""

    def __init__(self, debug: bool = False):
        self.debug = debug

    def parse(self, pdf_path: Path) -> ParsedDevis:
        text = self._extract_text(pdf_path)
        return self.parse_text(text)

    def parse_text(self, text: str) -> ParsedDevis:
        lines = [self._clean_line(line) for line in text.splitlines()]
        lines = [line for line in lines if line]

        devis_value = self._extract_devis_reference(lines)
        ref_affaire = self._extract_ref_affaire(lines)
        client_name, client_block = self._extract_client(lines)
        client_cp, client_city = self._extract_cp_ville(client_block)
        client_address_lines = self._build_address_lines(client_block, client_cp, client_city)
        commercial_name = self._extract_line_after_anchor(lines, CONTACT_COMMERCIAL_RE)
        montant_fourniture = self._extract_amount(lines, "PRIX DE LA FOURNITURE HT")
        montant_prestations = self._extract_amount(lines, "PRIX PRESTATIONS ET SERVICES HT")
        gamme = self._extract_after_label(lines, r"-\s*Mod[èe]le\s*:")
        contre_marche = self._extract_after_label(lines, r"-\s*Contremarche\s*:")
        structure_checkboxes = self._extract_structure(lines)
        tete_poteau = self._extract_after_label(lines, r"Poteau t[êe]te\s*:")
        remplissage = self._extract_remplissage(lines)
        essence, finition_marches, finition_cm, finition_structure, finition_mc = self._extract_essence_et_finition(
            lines
        )
        pose_vendue = self._detect_pose(montant_prestations, lines)

        return ParsedDevis(
            raw_lines=lines,
            bdc_devis_annee_mois=devis_value,
            bdc_ref_affaire=ref_affaire,
            bdc_client_nom=client_name,
            bdc_client_adresse="\n".join(client_address_lines).strip(),
            bdc_client_cp=client_cp,
            bdc_client_ville=client_city,
            bdc_commercial_nom=commercial_name,
            bdc_esc_gamme=gamme,
            bdc_chk_avec_contre_marches=contre_marche.lower().startswith("avec") if contre_marche else False,
            bdc_chk_sans_contre_marches=contre_marche.lower().startswith("sans") if contre_marche else False,
            bdc_structure_checkboxes=structure_checkboxes,
            bdc_esc_tete_de_poteau=tete_poteau,
            bdc_esc_section_remplissage_garde_corps_rampant=remplissage.get("rampant", ""),
            bdc_esc_section_remplissage_garde_corps_etage=remplissage.get("etage", ""),
            bdc_esc_remplissage_garde_corps_soubassement=remplissage.get("soubassement", ""),
            bdc_esc_essence=essence,
            bdc_esc_finition_marches=finition_marches,
            bdc_esc_finition_contremarche=finition_cm,
            bdc_esc_finition_structure=finition_structure,
            bdc_esc_finition_mains_courante=finition_mc,
            bdc_montant_fourniture_ht=montant_fourniture,
            bdc_montant_pose_ht=montant_prestations,
            pose_vendue=pose_vendue,
        )

    def _extract_text(self, pdf_path: Path) -> str:
        if not pdf_path.exists():
            raise FileNotFoundError(pdf_path)
        text_parts: list[str] = []
        with pdfplumber.open(pdf_path) as pdf:
            for page in pdf.pages:
                page_text = page.extract_text() or ""
                text_parts.append(page_text)
        return "\n".join(text_parts)

    def _clean_line(self, line: str) -> str:
        cleaned = line.replace("\u202f", " ")
        cleaned = re.sub(r"\s+", " ", cleaned)
        return cleaned.strip()

    def _extract_devis_reference(self, lines: Sequence[str]) -> str:
        for line in lines:
            if "DEVIS" not in line.upper():
                continue
            match = DEVIS_PATTERN.search(line.replace(" ", ""))
            if match:
                return match.group(0)
        for line in lines:
            match = DEVIS_PATTERN.search(line.replace(" ", ""))
            if match:
                return match.group(0)
        return ""

    def _extract_ref_affaire(self, lines: Sequence[str]) -> str:
        for idx, line in enumerate(lines):
            if REF_AFFAIRE_RE.search(line):
                inline = self._extract_after_colon(line)
                if inline:
                    return inline
                return self._next_non_empty(lines, idx + 1)
        return ""

    def _extract_client(self, lines: Sequence[str]) -> tuple[str, list[str]]:
        anchor_index = self._find_first_index(lines, CODE_CLIENT_RE)
        if anchor_index is not None:
            block = self._collect_block(lines, anchor_index + 1)
            name = self._first_valid_line(block)
            cleaned_block = [line for line in block if line.strip() and line.strip() != name]
            return name, cleaned_block

        stop_index = self._find_first_index(lines, CONTACT_COMMERCIAL_RE)
        window = lines if stop_index is None else lines[:stop_index]
        tel_index = self._find_first_index(window, TEL_RE)
        if tel_index is not None:
            window = window[:tel_index]
        name = self._first_valid_line(window)
        cleaned_window = [line for line in window if line.strip() and line.strip() != name]
        return name, list(cleaned_window)

    def _first_valid_line(self, lines: Iterable[str]) -> str:
        for line in lines:
            upper = line.upper()
            if any(token in upper for token in ("DATE DU DEVIS", "RÉF AFFAIRE", "REF AFFAIRE", "DEVIS")):
                continue
            if "SRX" in upper:
                continue
            if self._is_internal_line(line):
                continue
            if line.strip():
                return line.strip()
        return ""

    def _is_internal_line(self, line: str) -> bool:
        normalized = line.upper().strip()
        return any(addr.upper() in normalized for addr in INTERNAL_ADDRESSES)

    def _collect_block(self, lines: Sequence[str], start: int) -> list[str]:
        collected: list[str] = []
        for line in lines[start:]:
            lowered = line.lower()
            if CONTACT_COMMERCIAL_RE.search(line) or REF_AFFAIRE_RE.search(line):
                break
            if "prix" in lowered:
                break
            if TEL_RE.search(line):
                break
            collected.append(line)
        return collected

    def _extract_cp_ville(self, block: Sequence[str]) -> tuple[str, str]:
        for line in block:
            match = CP_VILLE_RE.search(line)
            if match:
                return match.group("cp"), match.group("city").strip()
        return "", ""

    def _build_address_lines(self, block: Sequence[str], cp: str, city: str) -> list[str]:
        address_lines: list[str] = []
        for line in block:
            if self._is_internal_line(line):
                continue
            if CP_VILLE_RE.search(line):
                continue
            if not line.strip():
                continue
            if line.strip() == cp or line.strip() == city:
                continue
            address_lines.append(line.strip())
        if cp and city:
            address_lines.append(f"{cp} {city}")
        return address_lines

    def _extract_line_after_anchor(self, lines: Sequence[str], anchor: re.Pattern[str]) -> str:
        for idx, line in enumerate(lines):
            if anchor.search(line):
                inline = self._extract_after_colon(line)
                if inline:
                    return inline
                return self._next_non_empty(lines, idx + 1)
        return ""

    def _extract_after_label(self, lines: Sequence[str], pattern: str) -> str:
        compiled = re.compile(pattern, flags=re.IGNORECASE)
        for idx, line in enumerate(lines):
            match = compiled.search(line)
            if match:
                inline = self._extract_after_colon(line)
                if inline:
                    return inline
                return self._next_non_empty(lines, idx + 1)
        return ""

    def _extract_amount(self, lines: Sequence[str], label: str) -> str:
        label_upper = label.upper()
        for line in lines:
            if label_upper not in line.upper():
                continue
            match = AMOUNT_RE.search(line)
            if match:
                amount = match.group(1)
                amount = amount.replace("\u202f", " ").replace(" ", "")
                if "," in amount and "." in amount:
                    amount = amount.replace(".", "")
                return amount.replace(".", ",")
        return ""

    def _extract_structure(self, lines: Sequence[str]) -> dict[str, bool]:
        checkboxes = {
            "bdc_chk_limon": False,
            "bdc_chk_limon_centrale": False,
            "bdc_chk_limon_decoupe": False,
            "bdc_chk_cremaillere": False,
        }
        for line in lines:
            lower = line.lower()
            if "limon" in lower:
                checkboxes["bdc_chk_limon"] = True
                if "centr" in lower:
                    checkboxes["bdc_chk_limon_centrale"] = True
                if "découp" in lower or "decoup" in lower:
                    checkboxes["bdc_chk_limon_decoupe"] = True
            if "crémaillère" in lower or "cremaill" in lower:
                checkboxes["bdc_chk_cremaillere"] = True
        return checkboxes

    def _extract_remplissage(self, lines: Sequence[str]) -> dict[str, str]:
        remplissage = {"rampant": "", "etage": "", "soubassement": ""}
        for line in lines:
            lower = line.lower()
            if "rampant" in lower and not remplissage["rampant"]:
                remplissage["rampant"] = self._extract_after_colon(line) or line
            if "etage" in lower and not remplissage["etage"]:
                remplissage["etage"] = self._extract_after_colon(line) or line
            if "soubassement" in lower and not remplissage["soubassement"]:
                remplissage["soubassement"] = self._extract_after_colon(line) or line
        return remplissage

    def _extract_essence_et_finition(
        self, lines: Sequence[str]
    ) -> tuple[str, str, str, str, str]:
        essence = ""
        finition_marches = ""
        finition_cm = ""
        finition_structure = ""
        finition_mc = ""

        for line in lines:
            lower = line.lower()
            if "essence" in lower and not essence:
                essence = self._extract_after_colon(line) or line
            if "marches" in lower and not finition_marches:
                finition_marches = self._extract_after_colon(line) or line
            if "contremarche" in lower and not finition_cm:
                finition_cm = self._extract_after_colon(line) or line
            if "structure" in lower and not finition_structure:
                finition_structure = self._extract_after_colon(line) or line
            if "main courante" in lower and not finition_mc:
                finition_mc = self._extract_after_colon(line) or line
        return essence, finition_marches, finition_cm, finition_structure, finition_mc

    def _detect_pose(self, montant_prestations: str, lines: Sequence[str]) -> bool:
        if montant_prestations:
            try:
                value = float(montant_prestations.replace(" ", "").replace(",", "."))
                if value > 0:
                    return True
            except ValueError:
                pass
        for line in lines:
            if "pose" in line.lower():
                return True
        return False

    def _extract_after_colon(self, line: str) -> str:
        if ":" not in line:
            return ""
        return line.split(":", 1)[1].strip()

    def _next_non_empty(self, lines: Sequence[str], start: int) -> str:
        for idx in range(start, len(lines)):
            if lines[idx].strip():
                return lines[idx].strip()
        return ""

    def _find_first_index(self, lines: Sequence[str], pattern: re.Pattern[str]) -> int | None:
        for idx, line in enumerate(lines):
            if pattern.search(line):
                return idx
        return None
