import json
from pathlib import Path

import pytest

from services.devis_parser import DevisParser, ParserError


FIXTURE_DIR = Path("fixtures")


def _fixture_dirs() -> list[Path]:
    return sorted(path for path in FIXTURE_DIR.iterdir() if path.is_dir())


@pytest.mark.parametrize("fixture_dir", _fixture_dirs())
def test_parser_compare_expected(fixture_dir: Path):
    expected_path = fixture_dir / "expected.json"
    pdf_candidates = sorted(fixture_dir.glob("*.pdf"))
    assert pdf_candidates, f"Aucun PDF trouvé pour {fixture_dir}"
    expected = json.loads(expected_path.read_text(encoding="utf-8"))

    parser = DevisParser()
    result = parser.parse(pdf_candidates[0]).values
    for key, expected_value in expected.items():
        assert result.get(key) == expected_value, key


def test_missing_anchor_raises(tmp_path: Path):
    # génère un PDF sans ancre pour vérifier l'erreur bloquante
    pdf_path = tmp_path / "missing.pdf"
    from pypdf import PdfWriter

    writer = PdfWriter()
    writer.add_blank_page(width=100, height=100)
    with pdf_path.open("wb") as handle:
        writer.write(handle)
    parser = DevisParser()
    with pytest.raises(ParserError):
        parser.parse(pdf_path)
