import json
import sys
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parents[1]))

from services.devis_parser import DevisParser


def iter_fixtures(fixtures_root: Path):
    for entry in sorted(fixtures_root.iterdir()):
        if not entry.is_dir():
            continue
        expected_path = entry / "expected.json"
        if expected_path.exists():
            yield entry, expected_path


def load_expected(expected_path: Path) -> dict:
    with expected_path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def resolve_source_pdf(expected: dict, fixture_dir: Path) -> Path | None:
    source = expected.get("source_pdf")
    if source:
        candidate = Path(source)
        if candidate.exists():
            return candidate
        candidate = fixture_dir / Path(source).name
        if candidate.exists():
            return candidate
    pdfs = sorted(fixture_dir.glob("*.pdf"))
    return pdfs[0] if pdfs else None


def compare_expected(parsed: dict, expected: dict) -> list[str]:
    mismatches = []
    for key, expected_value in expected.items():
        if key == "source_pdf":
            continue
        actual_value = parsed.get(key, "")
        if actual_value != expected_value:
            mismatches.append(
                f"{key}: expected '{expected_value}' got '{actual_value}'"
            )
    return mismatches


def context_lines(lines: list[str], anchor: str, window: int = 3) -> list[str]:
    anchor_lower = anchor.lower()
    for idx, line in enumerate(lines):
        if anchor_lower in line.lower():
            start = max(idx - window, 0)
            end = min(idx + window + 1, len(lines))
            return [
                f"{line_idx + 1:03d}: {lines[line_idx]}"
                for line_idx in range(start, end)
            ]
    return []


def main() -> int:
    fixtures_root = Path("fixtures")
    parser = DevisParser()
    failures = 0
    if not fixtures_root.exists():
        print("No fixtures directory found.")
        return 1

    for fixture_dir, expected_path in iter_fixtures(fixtures_root):
        expected = load_expected(expected_path)
        source_pdf = resolve_source_pdf(expected, fixture_dir)
        if not source_pdf:
            print(f"[{fixture_dir.name}] Missing source PDF.")
            failures += 1
            continue
        parsed = parser.parse(source_pdf)
        mismatches = compare_expected(parsed, expected)
        if mismatches:
            failures += 1
            print(f"\n[{fixture_dir.name}] Mismatches:")
            for mismatch in mismatches:
                print(f" - {mismatch}")
            print("Context around 'Code client':")
            for line in context_lines(parsed.get("lines", []), "Code client"):
                print(f"   {line}")
            print("Context around 'Contact commercial':")
            for line in context_lines(parsed.get("lines", []), "Contact commercial"):
                print(f"   {line}")

    if failures:
        print(f"\n{failures} fixture(s) failed.")
        return 1
    print("All fixtures matched expected values.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
