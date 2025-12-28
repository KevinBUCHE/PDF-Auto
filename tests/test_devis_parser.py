import json
from pathlib import Path

import pytest

from services.devis_parser import DevisParser


FIXTURES_DIR = Path(__file__).parent / "fixtures"


def load_lines(filename: str):
    content = (FIXTURES_DIR / filename).read_text(encoding="utf-8")
    return content.splitlines()


def test_parse_sample_lines_matches_expected_snapshot():
    parser = DevisParser(debug=False)
    lines = load_lines("sample_lines.txt")
    data = parser.parse_lines(lines)
    expected = json.loads((FIXTURES_DIR / "expected.json").read_text(encoding="utf-8"))

    for key, expected_value in expected.items():
        assert data.get(key) == expected_value, f"Mismatch for {key}"


def test_remplissage_without_zone_adds_warning():
    parser = DevisParser(debug=False)
    lines = [
        "Remplissage : Barreaudage",
    ]
    data = parser.parse_lines(lines)
    assert data["remplissage_rampant"] == "Barreaudage"
    assert "Remplissage sans précision" in data.get("parse_warning", "")


@pytest.mark.parametrize(
    "client_line",
    ["RIAUX", "BAZOUGES", "VAUGARNY", "35560", "DEVIS RIAUX"],
)
def test_client_banned_tokens_are_skipped(client_line):
    parser = DevisParser(debug=False)
    lines = [
        "Code client :",
        client_line,
        "Client Final",
        "123 Rue test",
        "Contact commercial",
    ]
    data = parser.parse_lines(lines)
    assert data["client_nom"] == "Client Final"
