import json
from pathlib import Path

from services.rule_based_parser import RuleBasedParser
from services.validator import validate_and_fix

FIXTURE_ROOT = Path("fixtures")
KEYS_TO_CHECK = [
    "devis_annee_mois",
    "devis_type",
    "devis_num",
    "ref_affaire",
    "client_nom",
    "client_cp",
    "client_ville",
    "client_adresse1",
    "client_adresse2",
    "commercial_nom",
    "fourniture_ht",
    "prestations_ht",
    "total_ht",
]


def load_expected(fixture_dir: Path) -> dict:
    with (fixture_dir / "expected.json").open("r", encoding="utf-8") as handle:
        return json.load(handle)


def load_pdf_path(fixture_dir: Path, expected: dict) -> Path:
    source_pdf = expected.get("source_pdf")
    if source_pdf:
        candidate = Path(source_pdf)
        if not candidate.is_absolute():
            candidate = fixture_dir.parent / candidate
        if candidate.exists():
            return candidate
    pdfs = list(fixture_dir.glob("*.pdf"))
    if not pdfs:
        raise FileNotFoundError(f"Aucun PDF dans {fixture_dir}")
    return pdfs[0]


def test_rule_based_parser_on_fixtures():
    parser = RuleBasedParser(debug=False)
    for fixture_dir in FIXTURE_ROOT.glob("SRX*"):
        expected = load_expected(fixture_dir)
        pdf_path = load_pdf_path(fixture_dir, expected)
        data = parser.parse(pdf_path)
        data, warnings = validate_and_fix(data)
        assert not any(token in (data.get("client_nom", "") or "").upper() for token in ("RIAUX", "VAUGARNY", "BAZOUGES"))
        for key in KEYS_TO_CHECK:
            assert data.get(key, "") == expected.get(key, ""), f"{fixture_dir.name} mismatch for {key}: got {data.get(key)} expected {expected.get(key)}. warnings={warnings}"
