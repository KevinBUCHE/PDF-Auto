from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from services.bdc_filler import fill_bdc
from services.devis_parser import parse_devis
from services import sanitize


def load_config(config_path: Path) -> dict:
    if config_path.exists():
        with config_path.open("r", encoding="utf-8") as handle:
            return json.load(handle)
    return {"default_output_dir": "BDC_Output", "adresse_depot_pose": ""}


def build_argument_parser(default_outdir: str) -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Génère un bon de commande depuis un devis SRX*.")
    parser.add_argument("--input", required=True, help="Chemin vers le devis SRX*.pdf")
    parser.add_argument(
        "--pose",
        choices=["yes", "no", "auto"],
        default="auto",
        help="Force l'indicateur de pose vendue (auto = détection du devis).",
    )
    parser.add_argument(
        "--outdir",
        default=default_outdir,
        help="Dossier de sortie pour le PDF et le JSON (défaut: BDC_Output).",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    config = load_config(Path("config.json"))
    parser = build_argument_parser(config.get("default_output_dir", "BDC_Output"))
    args = parser.parse_args(argv)

    pdf_path = Path(args.input)
    if not pdf_path.exists():
        print(f"Fichier introuvable: {pdf_path}", file=sys.stderr)
        return 1

    parsed = parse_devis(pdf_path)
    if args.pose != "auto":
        parsed.data.pose_sold = args.pose == "yes"

    output_dir = Path(args.outdir or config.get("default_output_dir", "BDC_Output"))
    sanitize.ensure_directory(output_dir)

    client_part = sanitize.safe_filename(parsed.data.client_nom or pdf_path.stem)
    ref_part = sanitize.safe_filename(parsed.data.ref_affaire or "SansRef")
    output_pdf = output_dir / f"CDE {client_part} Ref {ref_part}.pdf"
    output_json = output_pdf.with_suffix(".json")

    try:
        fill_bdc(Path("Templates/bon de commande V1.pdf"), output_pdf, parsed, config)
    except Exception as exc:  # pragma: no cover - surfaced in CLI errors
        print(f"Erreur lors du remplissage du PDF: {exc}", file=sys.stderr)
        return 1

    with output_json.open("w", encoding="utf-8") as handle:
        json.dump(parsed.to_dict(), handle, ensure_ascii=False, indent=2)

    print(f"PDF généré: {output_pdf}")
    print(f"JSON généré: {output_json}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
