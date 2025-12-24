import argparse
import json
import sys
from pathlib import Path

from services.bdc_filler import BdcFiller
from services.devis_parser import DevisParser
from services.address_sanitizer import sanitize_client_address


KEYS_TO_ASSERT = [
    "client_nom",
    "client_cp",
    "client_ville",
    "commercial_nom",
    "ref_affaire",
    "devis_annee_mois",
    "devis_num",
    "fourniture_ht",
    "prestations_ht",
    "pose_sold",
]


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
    for key in KEYS_TO_ASSERT:
        expected_value = expected.get(key)
        actual_value = data.get(key)
        if expected_value != actual_value:
            failures.append(
                f"MISMATCH {key}: expected={expected_value!r} actual={actual_value!r}"
            )
    return failures


def main() -> int:
    parser = argparse.ArgumentParser(description="Run SRX fixture parsing test")
    parser.add_argument("fixture", type=Path, help="Path to fixture directory")
    args = parser.parse_args()

    fixture_dir = args.fixture.resolve()
    if not fixture_dir.exists():
        raise FileNotFoundError(f"Fixture introuvable: {fixture_dir}")

    expected = load_expected(fixture_dir)
    repo_root = Path(__file__).resolve().parents[1]
    pdf_path = resolve_pdf_path(fixture_dir, repo_root, expected)

    devis_parser = DevisParser(debug=False)
    data = sanitize_client_address(devis_parser.parse(pdf_path))

    data["pose_sold"] = bool(data.get("pose_sold"))

    failures = assert_expected(data, expected)
    filler = BdcFiller(logger=print)
    address = filler._build_client_adresse(data)
    for pollution in ("35560", "BAZOUGES", "VAUGARNY"):
        if pollution.lower() in address.lower():
            failures.append(f"Adresse polluée par {pollution!r}: {address!r}")
    if failures:
        for failure in failures:
            print(failure)
        return 1

    template_path = resolve_template_path(repo_root)
    output_path = fixture_dir / "output_bdc.pdf"
    filler.fill(template_path, data, output_path)

    print("Fixture OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
