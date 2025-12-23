import json
import sys
import tempfile
from pathlib import Path

from pypdf import PdfReader

from services.bdc_filler import BdcFiller
from services.devis_parser import DevisParser


FIXTURE_DIR = Path("Sample/ixtures/SRX2507AFF046101")
TEMPLATE_PATH = Path("Templates/bon de commande V1.pdf")


def _load_expected() -> dict:
    expected_path = FIXTURE_DIR / "expected.json"
    if not expected_path.exists():
        raise FileNotFoundError(expected_path)
    return json.loads(expected_path.read_text(encoding="utf-8"))


def _resolve_source_pdf(expected: dict) -> Path:
    expected_name = expected.get("source_pdf") or ""
    if expected_name:
        candidate = FIXTURE_DIR / expected_name
        if candidate.exists():
            return candidate
    pdfs = sorted(FIXTURE_DIR.glob("SRX*.pdf"))
    if not pdfs:
        raise FileNotFoundError("Aucun PDF SRX trouvé dans les fixtures.")
    return pdfs[0]


def _collect_bdc_values(reader: PdfReader) -> dict:
    values = {}
    for page in reader.pages:
        annots = page.get("/Annots")
        if not annots:
            continue
        annots = annots.get_object()
        for annot in annots:
            ao = annot.get_object()
            name = ao.get("/T")
            field_obj = ao
            if name is None and ao.get("/Parent"):
                field_obj = ao.get("/Parent").get_object()
                name = field_obj.get("/T")
            if name is None:
                continue
            name = str(name)
            if not name.startswith("bdc_"):
                continue
            value = field_obj.get("/V")
            values[name] = "" if value is None else str(value)
    return values


def _assert_equal(label: str, actual: str, expected: str) -> None:
    if actual != expected:
        raise AssertionError(f"{label}: attendu {expected!r}, obtenu {actual!r}")


def run() -> None:
    expected = _load_expected()
    source_pdf = _resolve_source_pdf(expected)
    parser = DevisParser(debug=True)
    data = parser.parse(source_pdf)

    checks = [
        ("client_nom", data.get("client_nom", ""), expected.get("client_nom", "")),
        ("commercial_nom", data.get("commercial_nom", ""), expected.get("commercial_nom", "")),
        ("ref_affaire", data.get("ref_affaire", ""), expected.get("ref_affaire", "")),
        ("devis_annee_mois", data.get("devis_annee_mois", ""), expected.get("devis_annee_mois", "")),
        ("devis_num", data.get("devis_num", ""), expected.get("devis_num", "")),
        ("fourniture_ht", data.get("fourniture_ht", ""), expected.get("fourniture_ht", "")),
        ("prestations_ht", data.get("prestations_ht", ""), expected.get("prestations_ht", "")),
    ]
    for label, actual, expected_value in checks:
        _assert_equal(label, actual, expected_value)
    if bool(data.get("pose_sold")) != bool(expected.get("pose_sold")):
        raise AssertionError(
            f"pose_sold: attendu {expected.get('pose_sold')}, obtenu {data.get('pose_sold')}"
        )

    if not TEMPLATE_PATH.exists():
        raise FileNotFoundError(TEMPLATE_PATH)

    with tempfile.TemporaryDirectory() as tmp_dir:
        output_path = Path(tmp_dir) / "bdc_test.pdf"
        BdcFiller().fill(TEMPLATE_PATH, data, output_path)
        reader = PdfReader(str(output_path))
        values = _collect_bdc_values(reader)
        required_fields = [
            "bdc_client_nom",
            "bdc_ref_affaire",
            "bdc_devis_annee_mois",
            "bdc_devis_num",
            "bdc_montant_fourniture_ht",
        ]
        missing = [name for name in required_fields if name not in values]
        if missing:
            raise AssertionError(f"Champs bdc_* manquants dans le PDF: {missing}")
        empty = [name for name in required_fields if not values.get(name)]
        if empty:
            raise AssertionError(f"Champs bdc_* vides après écriture: {empty}")

    print("Fixture SRX2507AFF046101: OK")


if __name__ == "__main__":
    try:
        run()
    except Exception as exc:  # pylint: disable=broad-except
        print(f"ERROR: {exc}")
        sys.exit(1)
