import json
from pathlib import Path

import pytest
from pypdf import PdfReader

from services.bdc_filler import BdcFiller
from services.devis_parser import DevisParser


TEMPLATE_PATH = Path("Templates/bon de commande V1.pdf")
CRITICAL_FIELDS = ["bdc_client_nom", "bdc_devis_annee_mois", "bdc_ref_affaire"]


def _read_field(reader: PdfReader, name: str) -> str:
    acro_form = reader.trailer["/Root"].get("/AcroForm")
    if not acro_form:
        return ""
    for field_ref in acro_form.get("/Fields", []):
        obj = field_ref.get_object()
        if obj.get("/T") == name:
            value = obj.get("/V")
            if hasattr(value, "name"):
                return value.name
            return str(value) if value is not None else ""
    return ""


@pytest.mark.parametrize(
    "fixture_dir",
    [
        Path("fixtures/SRX2507AFF046101"),
        Path("fixtures/SRX2511AFF037501"),
    ],
)
def test_fill_persists_critical_fields(tmp_path: Path, fixture_dir: Path):
    pdf_candidates = sorted(fixture_dir.glob("*.pdf"))
    assert pdf_candidates, f"Aucun PDF trouvé pour {fixture_dir}"
    expected = json.loads((fixture_dir / "expected.json").read_text(encoding="utf-8"))

    parser = DevisParser()
    parsed = parser.parse(pdf_candidates[0]).values
    parsed["bdc_chk_livraison_poseur"] = False
    parsed["bdc_chk_livraison_client"] = True

    filler = BdcFiller(template_path=TEMPLATE_PATH)
    output_path = tmp_path / "output.pdf"
    filler.fill(parsed, output_path)

    reader = PdfReader(output_path)
    for key in CRITICAL_FIELDS:
        value = _read_field(reader, key)
        assert expected.get(key) in value
