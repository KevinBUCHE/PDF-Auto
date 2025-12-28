import json
import sys
from pathlib import Path

from pypdf import PdfReader

from services.bdc_filler import BdcFiller
from services.devis_parser import DevisParser


EXPECTED_KEYS = [
    "client_nom",
    "ref_affaire",
    "devis_annee_mois",
    "devis_num",
    "fourniture_ht",
    "prestations_ht",
    "pose_sold",
]

FIELD_CHECKS = {
    "bdc_client_nom": "client_nom",
    "bdc_ref_affaire": "ref_affaire",
    "bdc_devis_annee_mois": "devis_annee_mois",
    "bdc_devis_num": "devis_num",
    "bdc_montant_fourniture_ht": "fourniture_ht",
    "bdc_montant_pose_ht": "prestations_ht",
}


def load_expected(fixture_dir: Path) -> dict:
    expected_path = fixture_dir / "expected.json"
    if not expected_path.exists():
        raise FileNotFoundError(f"expected.json introuvable: {expected_path}")
    with expected_path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def resolve_pdf_path(fixture_dir: Path, repo_root: Path, expected: dict) -> Path:
    source_pdf = expected.get("source_pdf")
    if source_pdf:
        candidate = Path(source_pdf)
        if not candidate.is_absolute():
            candidate = repo_root / candidate
        if candidate.exists():
            return candidate.resolve()
    pdfs = sorted(fixture_dir.glob("*.pdf"))
    if len(pdfs) == 1:
        return pdfs[0]
    raise FileNotFoundError(
        "PDF devis introuvable dans la fixture. "
        "Ajoutez un fichier PDF ou 'source_pdf' dans expected.json."
    )


def resolve_template_path(repo_root: Path) -> Path:
    template = repo_root / "Templates" / "bon de commande V1.pdf"
    if template.exists():
        return template
    fallback = repo_root / "Sample" / "bon de commande V1.pdf"
    if fallback.exists():
        return fallback
    raise FileNotFoundError("Template PDF introuvable (Templates/ ou Sample/).")


def assert_expected(data: dict, expected: dict) -> list[str]:
    failures = []
    for key in EXPECTED_KEYS:
        expected_value = expected.get(key)
        actual_value = data.get(key)
        if expected_value != actual_value:
            failures.append(
                f"MISMATCH {key}: expected={expected_value!r} actual={actual_value!r}"
            )
    return failures


def extract_field_values(pdf_path: Path, field_names: set[str]) -> dict[str, str]:
    reader = PdfReader(str(pdf_path))
    values: dict[str, str] = {}
    for page in reader.pages:
        annots = page.get("/Annots")
        if not annots:
            continue
        annots = annots.get_object()
        for annot in annots:
            ao = annot.get_object()
            name = ao.get("/T")
            if name is None and ao.get("/Parent"):
                parent = ao.get("/Parent").get_object()
                name = parent.get("/T")
                field_obj = parent
            else:
                field_obj = ao
            if name is None:
                continue
            name = str(name)
            if name not in field_names or name in values:
                continue
            value = field_obj.get("/V")
            values[name] = "" if value is None else str(value)
    return values


def main() -> int:
    repo_root = Path(__file__).resolve().parents[1]
    fixture_dir = repo_root / "fixtures" / "SRX2507AFF046101"
    expected = load_expected(fixture_dir)
    pdf_path = resolve_pdf_path(fixture_dir, repo_root, expected)

    devis_parser = DevisParser(debug=False)
    data = devis_parser.parse(pdf_path)

    failures = assert_expected(data, expected)
    if failures:
        for failure in failures:
            print(failure)
        return 1

    template_path = resolve_template_path(repo_root)
    output_path = fixture_dir / "output_bdc.pdf"
    filler = BdcFiller(logger=print)
    filler.fill(template_path, data, output_path)

    field_values = extract_field_values(output_path, set(FIELD_CHECKS.keys()))
    for field_name, expected_key in FIELD_CHECKS.items():
        expected_value = expected.get(expected_key, "")
        actual_value = field_values.get(field_name)
        if expected_value != actual_value:
            print(
                "MISMATCH_FIELD "
                f"{field_name}: expected={expected_value!r} actual={actual_value!r}"
            )
            return 1

    print("Fixture OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
