#!/usr/bin/env python3
"""
BDC Generator - CLI Application

Simple CLI tool to generate purchase orders (BDC) from SRX quote PDFs.

Usage:
    python main.py <devis.pdf> [<devis2.pdf> ...]
    python main.py --batch <directory>

Objective:
    Take a SRX PDF quote from RIAUX and generate a purchase order PDF
    by filling the AcroForm template: Templates/bon de commande V1.pdf

Key Features:
    - Robust extraction: CLIENT / COMMERCIAL / RÉF AFFAIRE / MONTANTS
    - RIAUX contamination prevention: never inject RIAUX address/details into client fields
    - Simple CLI interface, no GUI
    - Minimal dependencies
"""

import argparse
import sys
from pathlib import Path
from datetime import datetime

from services.devis_parser import DevisParser
from services.bdc_filler import BdcFiller
from services.sanitize import validate_client_extraction


APP_NAME = "BDC Generator"
VERSION = "1.0.0"


class BdcGeneratorCLI:
    """CLI interface for BDC Generator"""
    
    def __init__(self, verbose: bool = False):
        self.verbose = verbose
        self.parser = DevisParser(debug=verbose)
        self.bdc_filler = BdcFiller(logger=self.log if verbose else None)
        self.template_path = self._find_template()
        
    def log(self, message: str):
        """Log a message to stdout"""
        timestamp = datetime.now().strftime("%H:%M:%S")
        print(f"[{timestamp}] {message}")
    
    def error(self, message: str):
        """Log an error message to stderr"""
        print(f"ERROR: {message}", file=sys.stderr)
    
    def _find_template(self) -> Path:
        """Find the BDC template PDF"""
        # Try multiple locations
        locations = [
            Path(__file__).parent / "Templates" / "bon de commande V1.pdf",
            Path.home() / ".config" / APP_NAME / "Templates" / "bon de commande V1.pdf",
            Path(__file__).parent / "Sample" / "bon de commande V1.pdf",
        ]
        
        for location in locations:
            if location.exists():
                return location
        
        raise FileNotFoundError(
            "Template PDF not found. Please place 'bon de commande V1.pdf' "
            "in the Templates/ directory."
        )
    
    def process_devis(self, devis_path: Path, output_dir: Path) -> bool:
        """
        Process a single devis PDF and generate BDC.
        
        Args:
            devis_path: Path to the devis PDF
            output_dir: Output directory for generated BDC
            
        Returns:
            True if successful, False otherwise
        """
        if not devis_path.exists():
            self.error(f"File not found: {devis_path}")
            return False
        
        if not devis_path.suffix.lower() == ".pdf":
            self.error(f"Not a PDF file: {devis_path}")
            return False
        
        # Check if it's a SRX file
        if not devis_path.name.upper().startswith("SRX"):
            self.error(f"Not a SRX file (filename should start with SRX): {devis_path.name}")
            return False
        
        try:
            if self.verbose:
                self.log(f"Parsing: {devis_path.name}")
            
            # Parse devis
            data = self.parser.parse(devis_path)
            
            # Check for parse warnings
            if data.get("parse_warning"):
                self.error(f"Parse warnings: {data['parse_warning']}")
            
            # Validate no RIAUX contamination
            contamination_warnings = validate_client_extraction(data)
            if contamination_warnings:
                self.error("RIAUX contamination detected!")
                for warning in contamination_warnings:
                    self.error(f"  - {warning}")
                return False
            
            # Check required fields
            required_fields = ["client_nom", "devis_num", "ref_affaire"]
            missing = [f for f in required_fields if not data.get(f)]
            if missing:
                self.error(f"Missing required fields: {', '.join(missing)}")
                return False
            
            # Generate output filename
            output_name = self._build_output_name(data)
            output_path = output_dir / output_name
            
            if self.verbose:
                self.log(f"Generating BDC: {output_name}")
                self.log(f"  Client: {data.get('client_nom')}")
                self.log(f"  Ref affaire: {data.get('ref_affaire')}")
                self.log(f"  Devis: SRX{data.get('devis_annee_mois')}{data.get('devis_type')}{data.get('devis_num')}")
                self.log(f"  Fourniture HT: {data.get('fourniture_ht')}")
                self.log(f"  Prestations HT: {data.get('prestations_ht')}")
                self.log(f"  Pose: {'Oui' if data.get('pose_sold') else 'Non'}")
            
            # Fill BDC
            self.bdc_filler.fill(self.template_path, data, output_path)
            
            print(f"✓ Generated: {output_path}")
            return True
            
        except Exception as exc:
            self.error(f"Failed to process {devis_path.name}: {exc}")
            if self.verbose:
                import traceback
                traceback.print_exc()
            return False
    
    def _build_output_name(self, data: dict) -> str:
        """Build output filename from devis data"""
        import re
        
        client_nom = data.get("client_nom", "").strip() or "CLIENT"
        ref_affaire = data.get("ref_affaire", "").strip() or "REF"
        
        # Clean ref_affaire
        ref_affaire = re.sub(r"^réf\s+affaire\s*:?\s*", "", ref_affaire, flags=re.IGNORECASE)
        
        base = f"CDE {client_nom} Ref {ref_affaire}"
        
        # Remove invalid filename characters
        base = re.sub(r'[\\/:*?"<>|]', " ", base)
        base = re.sub(r"\s+", " ", base).strip()
        
        # Limit length
        max_base = 150 - len(".pdf")
        if len(base) > max_base:
            base = base[:max_base].rstrip()
        
        return f"{base}.pdf"
    
    def process_batch(self, input_dir: Path, output_dir: Path) -> tuple[int, int]:
        """
        Process all SRX PDFs in a directory.
        
        Args:
            input_dir: Directory containing devis PDFs
            output_dir: Output directory for generated BDCs
            
        Returns:
            Tuple of (successful_count, failed_count)
        """
        if not input_dir.exists():
            self.error(f"Directory not found: {input_dir}")
            return 0, 0
        
        if not input_dir.is_dir():
            self.error(f"Not a directory: {input_dir}")
            return 0, 0
        
        # Find all SRX PDF files
        pdf_files = sorted(input_dir.glob("SRX*.pdf"))
        
        if not pdf_files:
            self.error(f"No SRX*.pdf files found in {input_dir}")
            return 0, 0
        
        print(f"Found {len(pdf_files)} SRX PDF file(s)")
        
        successful = 0
        failed = 0
        
        for pdf_path in pdf_files:
            if self.process_devis(pdf_path, output_dir):
                successful += 1
            else:
                failed += 1
        
        return successful, failed


def main():
    """Main entry point"""
    parser = argparse.ArgumentParser(
        description=f"{APP_NAME} - Generate purchase orders from SRX quotes",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python main.py SRX2511AFF037501.pdf
  python main.py SRX*.pdf
  python main.py --batch ./devis_folder
  python main.py --output ./output SRX2511AFF037501.pdf
        """
    )
    
    parser.add_argument(
        "inputs",
        nargs="*",
        type=Path,
        help="Input devis PDF file(s) (SRX*.pdf)"
    )
    
    parser.add_argument(
        "-b", "--batch",
        type=Path,
        metavar="DIR",
        help="Process all SRX PDFs in directory"
    )
    
    parser.add_argument(
        "-o", "--output",
        type=Path,
        metavar="DIR",
        help="Output directory (default: ./BDC_Output)"
    )
    
    parser.add_argument(
        "-v", "--verbose",
        action="store_true",
        help="Verbose output"
    )
    
    parser.add_argument(
        "--version",
        action="version",
        version=f"{APP_NAME} {VERSION}"
    )
    
    args = parser.parse_args()
    
    # Validate arguments
    if not args.inputs and not args.batch:
        parser.error("Please provide input file(s) or use --batch")
    
    # Set output directory
    output_dir = args.output or Path("./BDC_Output")
    output_dir.mkdir(parents=True, exist_ok=True)
    
    # Create CLI instance
    cli = BdcGeneratorCLI(verbose=args.verbose)
    
    if args.verbose:
        cli.log(f"{APP_NAME} v{VERSION}")
        cli.log(f"Template: {cli.template_path}")
        cli.log(f"Output directory: {output_dir.resolve()}")
    
    # Process files
    successful = 0
    failed = 0
    
    try:
        if args.batch:
            # Batch mode
            succ, fail = cli.process_batch(args.batch, output_dir)
            successful += succ
            failed += fail
        else:
            # Individual files
            for input_path in args.inputs:
                if cli.process_devis(input_path, output_dir):
                    successful += 1
                else:
                    failed += 1
        
        # Summary
        print(f"\nSummary: {successful} successful, {failed} failed")
        
        if failed > 0:
            return 1
        return 0
        
    except KeyboardInterrupt:
        cli.error("\nInterrupted by user")
        return 130
    except Exception as exc:
        cli.error(f"Unexpected error: {exc}")
        if args.verbose:
            import traceback
            traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(main())
