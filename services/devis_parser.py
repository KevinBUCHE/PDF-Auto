from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Tuple

import pdfplumber

from .rules import (
    ADDRESS_STOP_PREFIXES,
    BANNED_CLIENT_TERMS,
    DEVISE_REGEX,
    NEGATIVE_CONTREMARCHE,
    STRUCTURE_MAP,
    ParsedValues,
    extract_after_colon,
    extract_essence,
    find_first,
    find_regex_in_lines,
    is_banned_client_line,
    normalize_line,
    normalize_price,
)


class ParserError(Exception):
    """Raised when a blocking business rule is violated."""


@dataclass
class ParserResult:
    values: Dict[str, str | bool]


class DevisParser:
    def __init__(self, logger: logging.Logger | None = None):
        self.logger = logger or logging.getLogger(__name__)

    def parse(self, pdf_path: Path) -> ParserResult:
        lines, raw_text = self._extract_lines(pdf_path)
        parsed = self._extract_values(lines, raw_text)
        payload = self._build_payload(parsed)
        return ParserResult(values=payload)

    def _extract_lines(self, pdf_path: Path) -> Tuple[List[str], str]:
        with pdfplumber.open(pdf_path) as pdf:
            pages = [page.extract_text() or "" for page in pdf.pages]
        raw_text = "\n".join(pages)
        lines = [line.rstrip() for line in raw_text.splitlines()]
        return lines, raw_text

    def _extract_values(self, lines: List[str], raw_text: str) -> ParsedValues:
        devis_ref = self._extract_devis_ref(lines, raw_text)
        ref_affaire = self._extract_ref_affaire(lines)
        client_nom, client_adresse = self._extract_client_block(lines)
        commercial = self._extract_commercial(lines)
        modele = self._extract_modele(lines)
        contremarche_flag = self._extract_contremarche(lines)
        structure_flag = self._extract_structure(lines)
        tete_poteau = self._extract_tete_poteau(lines)
        essence, fin_marches, fin_structure, fin_main, fin_contremarche, fin_rampe = (
            self._extract_finitions(lines)
        )
        fourniture_ht, prestation_ht = self._extract_prices(lines)

        return ParsedValues(
            devis_ref=devis_ref,
            ref_affaire=ref_affaire,
            client_nom=client_nom,
            client_adresse=client_adresse,
            commercial=commercial,
            modele=modele,
            contremarche_flag=contremarche_flag,
            structure_flag=structure_flag,
            tete_poteau=tete_poteau,
            essence=essence,
            finition_marches=fin_marches,
            finition_structure=fin_structure,
            finition_main_courante=fin_main,
            finition_contremarche=fin_contremarche,
            finition_rampe=fin_rampe,
            fourniture_ht=fourniture_ht,
            prestation_ht=prestation_ht,
        )

    def _build_payload(self, parsed: ParsedValues) -> Dict[str, str | bool]:
        payload: Dict[str, str | bool] = {
            "bdc_devis_annee_mois": parsed.devis_ref,
            "bdc_ref_affaire": parsed.ref_affaire,
            "bdc_client_nom": parsed.client_nom,
            "bdc_client_adresse": parsed.client_adresse,
            "bdc_commercial_nom": parsed.commercial,
            "bdc_esc_gamme": parsed.modele,
            "bdc_esc_tete_de_poteau": parsed.tete_poteau,
            "bdc_esc_essence": parsed.essence,
            "bdc_esc_finition_marches": parsed.finition_marches,
            "bdc_esc_finition_structure": parsed.finition_structure,
            "bdc_esc_finition_mains_courante": parsed.finition_main_courante,
            "bdc_esc_finition_contremarche": parsed.finition_contremarche,
            "bdc_esc_finition_rampe": parsed.finition_rampe,
            "bdc_montant_fourniture_ht": parsed.fourniture_ht,
            "bdc_montant_pose_ht": parsed.prestation_ht,
        }

        payload.update(
            {
                "bdc_chk_avec-contre-marches": parsed.contremarche_flag == "with",
                "bdc_chk_avec-sans-marches": parsed.contremarche_flag == "without",
                "bdc_chk_cremaillere": parsed.structure_flag == "bdc_chk_cremaillere",
                "bdc_chk_limon": parsed.structure_flag == "bdc_chk_limon",
                "bdc_chk_limon_decoupe": parsed.structure_flag
                == "bdc_chk_limon_decoupe",
                "bdc_chk_limon_centrale": parsed.structure_flag
                == "bdc_chk_limon_centrale",
            }
        )
        return payload

    def _extract_devis_ref(self, lines: List[str], raw_text: str) -> str:
        for line in lines:
            if "devis" in line.lower():
                match = DEVISE_REGEX.search(line)
                if match:
                    return match.group(0)
        global_match = DEVISE_REGEX.search(raw_text)
        if global_match:
            return global_match.group(0)
        raise ParserError("Référence devis introuvable (bloquant)")

    def _extract_ref_affaire(self, lines: List[str]) -> str:
        idx = find_first(lines, lambda l: "réf affaire" in l.lower() or "ref affaire" in l.lower())
        if idx is None:
            return ""
        inline = extract_after_colon(lines[idx])
        if inline:
            return inline
        for line in lines[idx + 1 :]:
            if line.strip():
                return line.strip()
        return ""

    def _extract_client_block(self, lines: List[str]) -> Tuple[str, str]:
        anchor_idx = find_first(lines, lambda l: "code client" in l.lower())
        if anchor_idx is None:
            raise ParserError("Ancre 'Code client' manquante (bloquant)")
        client_line_idx = None
        for idx in range(anchor_idx + 1, len(lines)):
            candidate = lines[idx].strip()
            if not candidate:
                continue
            if is_banned_client_line(candidate):
                raise ParserError("Ligne client invalide (bloquant)")
            client_line_idx = idx
            client_nom = candidate
            break
        if client_line_idx is None:
            raise ParserError("Client introuvable sous l'ancre (bloquant)")

        address_lines: List[str] = []
        for line in lines[client_line_idx + 1 :]:
            stripped = line.strip()
            lowered = stripped.lower()
            if not stripped:
                continue
            if any(lowered.startswith(prefix) for prefix in ADDRESS_STOP_PREFIXES):
                break
            if is_banned_client_line(stripped):
                self.logger.warning("Ligne d'adresse ignorée (pollution détectée): %s", stripped)
                continue
            address_lines.append(stripped)
        client_adresse = "\n".join(address_lines)
        return client_nom, client_adresse

    def _extract_commercial(self, lines: List[str]) -> str:
        anchor_idx = find_first(lines, lambda l: "contact commercial" in l.lower())
        if anchor_idx is None:
            self.logger.warning("Contact commercial introuvable (non bloquant)")
            return ""
        for candidate in lines[anchor_idx + 1 :]:
            candidate = candidate.strip()
            if candidate:
                return candidate
        return ""

    def _extract_modele(self, lines: List[str]) -> str:
        for line in lines:
            if "modèle" in line.lower() or "modele" in line.lower():
                if "-" in line and "mod" in line.lower():
                    after = extract_after_colon(line)
                    if after:
                        return after
        return ""

    def _extract_contremarche(self, lines: List[str]) -> str | None:
        for line in lines:
            lower = line.lower()
            if "contremarche" in lower:
                value = extract_after_colon(line).lower()
                if any(token in value for token in NEGATIVE_CONTREMARCHE):
                    return "without"
                if value.strip():
                    return "with"
        return None

    def _extract_structure(self, lines: List[str]) -> str | None:
        for line in lines:
            lower = normalize_line(line.lower())
            if "structure" not in lower:
                continue
            value = extract_after_colon(lower)
            for needle, flag in STRUCTURE_MAP:
                if needle in value:
                    return flag
        return None

    def _extract_tete_poteau(self, lines: List[str]) -> str:
        for line in lines:
            lower = line.lower()
            if "poteau" in lower and "(" in lower and ")" in lower:
                return extract_after_colon(line) or line.strip()
        return ""

    def _extract_finitions(
        self, lines: List[str]
    ) -> Tuple[str, str, str, str, str, str]:
        essence = ""
        fin_marches = ""
        fin_structure = ""
        fin_main = ""
        fin_contremarche = ""
        fin_rampe = ""
        for line in lines:
            lower = line.lower()
            if ":" not in line:
                continue
            value = extract_after_colon(line)
            if not value:
                continue
            if "marche" in lower:
                fin_marches = fin_marches or value
                essence = essence or extract_essence(value)
            if "structure" in lower:
                fin_structure = fin_structure or value
                essence = essence or extract_essence(value)
            if "main courante" in lower:
                fin_main = fin_main or value
                essence = essence or extract_essence(value)
            if "contremarche" in lower:
                fin_contremarche = fin_contremarche or value
                essence = essence or extract_essence(value)
            if "rampe" in lower:
                fin_rampe = fin_rampe or value
                essence = essence or extract_essence(value)
        return essence, fin_marches, fin_structure, fin_main, fin_contremarche, fin_rampe

    def _extract_prices(self, lines: List[str]) -> Tuple[str, str]:
        fourniture = ""
        prestation = ""
        for line in lines:
            lower = line.lower()
            if "prix de la fourniture ht" in lower:
                fourniture = normalize_price(line)
            if "prix prestations et services ht" in lower:
                prestation = normalize_price(line)
        if not fourniture:
            raise ParserError("Prix fourniture HT manquant (bloquant)")
        return fourniture, prestation
