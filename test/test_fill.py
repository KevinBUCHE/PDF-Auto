import json
from pathlib import Path

from services.bdc_filler import BdcFiller
from services.validator import validate_and_fix


def resolve_template_path(repo_root: Path) -> Path:
    template = repo_root / "Templates" / "bon de commande V1.pdf"
    if template.exists():
        return template
    fallback = repo_root / "Sample" / "bon de commande V1.pdf"
    if fallback.exists():
        return fallback
    raise FileNotFoundError("Template PDF introuvable (Templates/ ou Sample/).")


def test_fill_pdf_from_expected():
    repo_root = Path(__file__).resolve().parents[1]
    fixture_dir = repo_root / "fixtures" / "SRX2507AFF046101"
    expected_path = fixture_dir / "expected.json"
    with expected_path.open("r", encoding="utf-8") as handle:
        expected = json.load(handle)
    data, _ = validate_and_fix(expected)

    filler = BdcFiller(logger=print)
    template_path = resolve_template_path(repo_root)
    output_path = fixture_dir / "output_bdc_test.pdf"
    filler.fill(template_path, data, output_path)
    assert output_path.exists()
