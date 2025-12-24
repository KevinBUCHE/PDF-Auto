import json
import sys
from pathlib import Path

from pypdf import PdfReader

repo_root = Path(__file__).resolve().parents[1]
if str(repo_root) not in sys.path:
    sys.path.insert(0, str(repo_root))

from services.bdc_filler import BdcFiller
from services.devis_parser import DevisParser
from services.extraction_normalizer import normalize_extracted_data

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
    for key, expected_value in expected.items():
        if key == "source_pdf":
            continue
        actual_value = data.get(key, "")
        if actual_value is None:
            actual_value = ""
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
    fixtures_root = repo_root / "fixtures"
    fixture_dirs = [path for path in sorted(fixtures_root.iterdir()) if path.is_dir()]
    exit_code = 0
    for fixture_dir in fixture_dirs:
        expected = load_expected(fixture_dir)
        try:
            pdf_path = resolve_pdf_path(fixture_dir, repo_root, expected)
        except FileNotFoundError as exc:
            print(f"[SKIP] {fixture_dir.name}: {exc}")
            continue

        devis_parser = DevisParser(debug=False)
        data = normalize_extracted_data(devis_parser.parse(pdf_path))

        failures = assert_expected(data, expected)
        if failures:
            print(f"[FAIL] {fixture_dir.name}")
            for failure in failures:
                print(failure)
            exit_code = 1
            continue

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
                    "[FAIL_FIELD] "
                    f"{fixture_dir.name} {field_name}: expected={expected_value!r} actual={actual_value!r}"
                )
                exit_code = 1
                break
        else:
            print(f"[OK] {fixture_dir.name}")

    return exit_code


if __name__ == "__main__":
    sys.exit(main())
