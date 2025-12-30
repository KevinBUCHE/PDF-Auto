import json
from pathlib import Path

import pytest

from services.devis_parser import DevisParser
from services.validator import ValidationError, validate_parsed_devis


def test_parse_text_with_code_client_anchor():
    text = """
    DEVIS N° SRX2511AFF037501
    Réf affaire : AFF-42
    Code client :
    CLIENT ABC
    12 rue Exemple
    75001 PARIS
    Tél : 01 02 03 04 05
    Contact commercial :
    Jean Commercial
    - Modèle : Escalier bois
    - Contremarche : Avec
    Structure : limon centrale découpé
    Poteau tête : Poteau acier
    Remplissage garde corps rampant : Barreaudage horizontal
    Remplissage garde corps étage : Verre
    Remplissage garde corps soubassement : Plein
    Essence : Hêtre
    Marches : Hêtre verni
    Contremarche : Hêtre brut
    Structure : Acier peint
    Main courante : Chêne huilé
    PRIX DE LA FOURNITURE HT : 12 345,67
    PRIX PRESTATIONS ET SERVICES HT : 1 200,00
    """
    parser = DevisParser()
    parsed = parser.parse_text(text)
    parsed = validate_parsed_devis(parsed)

    assert parsed.bdc_devis_annee_mois == "SRX2511AFF037501"
    assert parsed.bdc_ref_affaire == "AFF-42"
    assert parsed.bdc_client_nom == "CLIENT ABC"
    assert "75001 PARIS" in parsed.bdc_client_adresse
    assert parsed.bdc_client_cp == "75001"
    assert parsed.bdc_client_ville.upper() == "PARIS"
    assert parsed.bdc_commercial_nom == "Jean Commercial"
    assert parsed.bdc_chk_avec_contre_marches is True
    assert parsed.bdc_structure_checkboxes["bdc_chk_limon"] is True
    assert parsed.bdc_structure_checkboxes["bdc_chk_limon_centrale"] is True
    assert parsed.bdc_structure_checkboxes["bdc_chk_limon_decoupe"] is True
    assert parsed.pose_vendue is True


def test_parse_text_without_code_client_anchor():
    text = """
    DATE DU DEVIS : 02/12/2025
    RIAUX CONSTRUCTIONS
    SRX2512AFF040301
    Réf affaire : AFF-99
    SOCIETE CLIENTE
    5 avenue du Test
    13001 MARSEILLE
    Tél : 04 88 77 66 55
    Contact commercial :
    Marie Vente
    - Modèle : Escalier métal
    - Contremarche : Sans
    PRIX DE LA FOURNITURE HT : 8 000,00
    PRIX PRESTATIONS ET SERVICES HT : 0,00
    """
    parser = DevisParser()
    parsed = parser.parse_text(text)
    parsed = validate_parsed_devis(parsed)

    assert parsed.bdc_client_nom == "SOCIETE CLIENTE"
    assert "5 avenue du Test" in parsed.bdc_client_adresse
    assert parsed.bdc_client_cp == "13001"
    assert parsed.bdc_client_ville.upper() == "MARSEILLE"
    assert parsed.bdc_chk_sans_contre_marches is True
    assert parsed.pose_vendue is False


def test_reject_internal_address():
    text = """
    DEVIS N° SRX2510AFF012345
    Réf affaire : AFF-77
    Code client :
    Test Client
    1 rue Interne
    35560 BAZOUGES LA PEROUSE
    Tél : 01 23 45 67 89
    """
    parser = DevisParser()
    parsed = parser.parse_text(text)
    with pytest.raises(ValidationError):
        validate_parsed_devis(parsed)


@pytest.mark.skipif(not Path("fixtures").exists(), reason="No fixtures directory present")
def test_parse_pdf_fixtures_if_available():
    fixtures_dir = Path("fixtures")
    pdfs = sorted(fixtures_dir.glob("*.pdf"))
    if not pdfs:
        pytest.skip("No PDF fixtures available")

    parser = DevisParser()
    for pdf_path in pdfs:
        parsed = parser.parse(pdf_path)
        parsed = validate_parsed_devis(parsed)
        expected_json = pdf_path.with_suffix(".json")
        if expected_json.exists():
            with expected_json.open("r", encoding="utf-8") as handle:
                expected = json.load(handle)
            assert parsed.bdc_devis_annee_mois == expected.get("bdc_devis_annee_mois")
            assert parsed.bdc_ref_affaire == expected.get("bdc_ref_affaire")
            assert parsed.bdc_client_nom == expected.get("bdc_client_nom")
