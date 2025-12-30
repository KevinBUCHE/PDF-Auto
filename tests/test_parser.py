import json
from pathlib import Path

import pytest

from services.devis_parser import parse_devis


FIXTURE_DIRS = sorted(Path("fixtures").glob("SRX*"))


def load_expected(fixture_dir: Path) -> dict:
    expected_path = fixture_dir / "expected.json"
    with expected_path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


@pytest.mark.parametrize("fixture_dir", FIXTURE_DIRS, ids=lambda p: p.name)
def test_parse_matches_expected(fixture_dir: Path) -> None:
    pdf_files = list(fixture_dir.glob("SRX*.pdf"))
    assert pdf_files, f"No PDF found in {fixture_dir}"
    parsed = parse_devis(pdf_files[0])
    assert parsed.to_dict() == load_expected(fixture_dir)
