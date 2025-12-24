# BDC Generator

**Simple CLI application** to generate purchase orders (BDC) from SRX quote PDFs.

## Objective

Take a SRX PDF quote from RIAUX and generate a purchase order PDF by filling the AcroForm template: `Templates/bon de commande V1.pdf`.

## Key Features

- **Robust extraction**: CLIENT / COMMERCIAL / RÉF AFFAIRE / MONTANTS from SRX PDFs
- **RIAUX contamination prevention**: Ensures RIAUX company information (address, phone, registration) is NEVER injected into client fields
- **Simple CLI interface**: No GUI, command-line only
- **Minimal dependencies**: Only pdfplumber and pypdf

## Installation

### Prerequisites
- Python 3.11+ (tested with 3.12)
- pip (Python package installer)

### Setup

⚠️ **IMPORTANT**: You must install dependencies before running the application.

```bash
# Clone the repository
git clone https://github.com/KevinBUCHE/PDF-Auto.git
cd PDF-Auto

# Install dependencies (REQUIRED)
pip install -r requirements.txt

# Verify installation
python main.py --version

# Ensure template exists
# Place your template at: Templates/bon de commande V1.pdf
```

If you get `ModuleNotFoundError`, make sure you ran `pip install -r requirements.txt` first.

## Usage

### Basic Usage
```bash
# Process a single devis
python main.py SRX2511AFF037501.pdf

# Process multiple devis
python main.py SRX*.pdf

# Verbose mode
python main.py -v SRX2511AFF037501.pdf
```

### Batch Processing
```bash
# Process all SRX PDFs in a directory
python main.py --batch ./devis_folder

# Specify output directory
python main.py --output ./my_output --batch ./devis_folder
```

### Options
- `-b, --batch DIR`: Process all SRX PDFs in directory
- `-o, --output DIR`: Output directory (default: ./BDC_Output)
- `-v, --verbose`: Verbose output
- `--version`: Show version

## Project Structure

```
PDF-Auto/
├── main.py                      # CLI application entry point
├── services/
│   ├── devis_parser.py         # SRX PDF parsing with RIAUX filtering
│   ├── bdc_filler.py           # AcroForm template filling
│   └── sanitize.py             # RIAUX contamination prevention
├── tests/
│   ├── test_parser.py          # Parser unit tests
│   ├── test_fill.py            # Filler unit tests
│   └── run_fixture.py          # Fixture-based integration test
├── fixtures/                    # Test fixtures
├── Templates/                   # BDC template location
│   └── bon de commande V1.pdf  # Required template
└── requirements.txt             # Minimal dependencies
```

## Testing

### Run Unit Tests
```bash
# Run all tests
python -m unittest discover tests

# Run parser tests
python -m unittest tests.test_parser

# Run filler tests
python -m unittest tests.test_fill
```

### Run Fixture Tests
```bash
python -m tests.run_fixture fixtures/SRX2507AFF046101
```

## Key Constraints

1. **Simplicity > Everything**: Minimal dependencies, clear code
2. **CLI First**: No GUI, command-line interface only
3. **Robust Extraction**: Reliable parsing of CLIENT, COMMERCIAL, RÉF AFFAIRE, and MONTANTS
4. **RIAUX Contamination Prevention**: **ABSOLUTE PROHIBITION** - NEVER inject RIAUX information (VAUGARNY, 35560 BAZOUGES LA PEROUSE, RCS/NAF/tel/etc.) into client fields

## Template Requirements

The template `Templates/bon de commande V1.pdf` must:
- Be an AcroForm PDF with named fields
- Include critical fields: `bdc_client_nom`, `bdc_devis_num`, `bdc_ref_affaire`
- Support checkbox fields for delivery options

## Output

Generated BDCs are saved to `BDC_Output/` (or specified directory) with naming format:
```
CDE <CLIENT_NOM> Ref <REF_AFFAIRE>.pdf
```

Example: `CDE BERVAL MAISONS Ref SALEIX.pdf`

## Dependencies

- `pdfplumber==0.11.4`: PDF text extraction
- `pypdf==4.2.0`: PDF form filling

## Troubleshooting

### "ModuleNotFoundError: No module named 'pdfplumber'" or "No module named 'pypdf'"

This means dependencies are not installed. Run:
```bash
pip install -r requirements.txt
```

### "Template PDF not found"

Ensure `Templates/bon de commande V1.pdf` exists in your repository.

### "Not a SRX file"

The application only processes PDF files starting with "SRX" in the filename.

### Verify Installation

To verify everything is set up correctly:
```bash
# Should display version
python main.py --version

# Run tests
python -m unittest discover tests -q
```

## License

See repository license file.

## Notes

- The PDF output is never flattened (remains editable)
- NeedAppearances is activated for proper form rendering
- Pose detection is automatic based on PRESTATIONS section content
