from __future__ import annotations

from dataclasses import asdict
from typing import Iterable

from .devis_parser import ParsedDevis
from .rules import INTERNAL_ADDRESSES


class ValidationError(Exception):
    """Raised when the parsed devis data is invalid."""


def _contains_internal_address(value: str) -> bool:
    upper_value = value.upper()
    return any(addr.upper() in upper_value for addr in INTERNAL_ADDRESSES)


def validate_parsed_devis(parsed: ParsedDevis) -> ParsedDevis:
    """Validate parsed data and enforce anti-RIAUX rules."""
    if _contains_internal_address(parsed.bdc_client_adresse) or _contains_internal_address(parsed.bdc_client_ville):
        raise ValidationError("Adresse interne détectée: refus de générer.")

    if parsed.bdc_client_cp and parsed.bdc_client_ville:
        cp_city = f"{parsed.bdc_client_cp} {parsed.bdc_client_ville}"
        if _contains_internal_address(cp_city):
            raise ValidationError("Adresse interne détectée: refus de générer.")

    mandatory = {
        "bdc_client_nom": parsed.bdc_client_nom,
        "bdc_ref_affaire": parsed.bdc_ref_affaire,
        "bdc_devis_annee_mois": parsed.bdc_devis_annee_mois,
    }
    missing = [key for key, value in mandatory.items() if not value]
    if missing:
        raise ValidationError(f"Champs obligatoires manquants: {', '.join(missing)}")

    return parsed


def to_dict(parsed: ParsedDevis) -> dict:
    """Helper to convert ParsedDevis into a plain dictionary for filling."""
    return asdict(parsed)
