import json
from pathlib import Path

from pypdf import PdfReader

from services.bdc_filler import BdcFiller, fill_bdc
from services.devis_parser import parse_devis


def _is_checked(value: object) -> bool:
    if value is None:
        return False
    text = str(value)
    return text not in {"/Off", "Off", "", "False"}


def _read_fields(pdf_path: Path) -> dict:
    reader = PdfReader(str(pdf_path))
    filler = BdcFiller(Path("Templates/bon de commande V1.pdf"))
    return filler._read_field_values(reader)


def test_fill_sets_core_fields(tmp_path: Path) -> None:
    fixture_dir = Path("fixtures/SRX2507AFF046101")
    pdf_path = next(fixture_dir.glob("SRX*.pdf"))
    parsed = parse_devis(pdf_path)

    output_pdf = tmp_path / "output.pdf"
    with Path("config.json").open("r", encoding="utf-8") as handle:
        config = json.load(handle)

    fill_bdc(Path("Templates/bon de commande V1.pdf"), output_pdf, parsed, config)

    values = _read_fields(output_pdf)
    assert values["bdc_client_nom"] == parsed.data.client_nom
    assert values["bdc_devis_annee_mois"] == parsed.data.devis_num_complet
    assert values["bdc_ref_affaire"] == parsed.data.ref_affaire
    assert values["bdc_montant_fourniture_ht"] == parsed.data.fourniture_ht
    assert _is_checked(values.get("bdc_chk_avec-sans-marches"))
    assert _is_checked(values.get("bdc_chk_livraison_poseur"))
    assert not _is_checked(values.get("bdc_chk_livraison_client"))
