# PDF Auto BDC Generator

Generates a filled "bon de commande" PDF from SRX quote PDFs using deterministic, rule-based parsing (pdfplumber) and form filling with pypdf. The tool targets Windows and produces a portable CLI binary via PyInstaller.

## Requirements
- Python 3.11+
- No external services (Gemini/OCR/Qt/PySide/fitz are not used).
- Dependencies are listed in `requirements.txt` (production) and `requirements-dev.txt` (development/testing/build).

## Usage (CLI)
From a Python environment with dependencies installed:

```bash
python main.py --input "fixtures/SRX2512AFF040301/SRX2512AFF040301.pdf" --pose auto --outdir "./BDC_Output"
```

Arguments:
- `--input`: Path to an SRX*.pdf quote.
- `--pose`: `yes`, `no`, or `auto` (default) to force or infer whether installation/pose is sold.
- `--outdir`: Output directory (defaults to `BDC_Output` or the value in `config.json`).

The command produces a filled PDF named `CDE <client_nom> Ref <ref_affaire>.pdf` and a JSON extraction file alongside it.

## Development
- Run the parser tests:
  ```bash
  python -m pytest
  ```
- Update fixtures by regenerating `expected.json` files after parser changes (see `fixtures/README.md`).

## Portable build
Use the PowerShell helper to build the Windows portable bundle (onedir) with PyInstaller and stage the template, config, RUN.bat, and an output folder:

```powershell
pwsh scripts/build_portable.ps1 -PythonExe python
```

The resulting folder is `dist/BDC_Generator/`. CI publishes a zipped version of this folder as an artifact.

## GitHub Actions
The `clean-build.yml` workflow (Windows) installs dependencies via `python -m pip`, runs `python -m pytest`, builds with `python -m PyInstaller`, and uploads the portable ZIP artifact.

## Notes on parsing
- Parsing is 100% rule-based (pdfplumber text extraction only).
- Riaux depot markers (Bazouges la Pérouse, Vaugarny, etc.) are filtered from client addresses.
- Full SRX numbers are sourced from the filename when available, otherwise from PDF text.
- Pose detection checks the PRESTATIONS section for "pose" lines and toggles delivery/auto-liquidation accordingly.
