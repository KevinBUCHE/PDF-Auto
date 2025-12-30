# Fixtures

Each folder in this directory contains:

- A sample SRX* quote PDF.
- A matching `expected.json` file containing the deterministic extraction output produced by `services.devis_parser.parse_devis`.

When adding a new fixture, run the parser and store its output so tests can assert against it:

```bash
python - <<'PY'
from pathlib import Path
import json
from services.devis_parser import parse_devis
fixture_pdf = Path("fixtures/NEW_CASE/SRXXXXX.pdf")
result = parse_devis(fixture_pdf)
with (fixture_pdf.parent / "expected.json").open("w", encoding="utf-8") as handle:
    json.dump(result.to_dict(), handle, ensure_ascii=False, indent=2)
PY
```
