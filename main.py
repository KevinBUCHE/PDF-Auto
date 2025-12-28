from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

from services.bdc_filler import BdcFiller
from services.devis_parser import DevisParser, ParserError
from services.sanitize import sanitize_filename


DEFAULT_TEMPLATE = Path("Templates/bon de commande V1.pdf")
DEFAULT_OUTPUT_DIR = Path("BDC_Output")


def build_output_name(client: str, ref_affaire: str) -> str:
    client_fragment = sanitize_filename(client or "CLIENT")
    ref_fragment = sanitize_filename(ref_affaire or "REFERENCE")
    return f"CDE {client_fragment} Ref {ref_fragment}.pdf"


def run(args: argparse.Namespace, logger: logging.Logger) -> Path:
    devis_path = Path(args.devis)
    if not devis_path.exists():
        raise FileNotFoundError(f"Devis introuvable: {devis_path}")
    template_path = Path(args.template)
    if not template_path.exists():
        raise FileNotFoundError(f"Template introuvable: {template_path}")

    parser = DevisParser(logger=logger)
    try:
        parsed = parser.parse(devis_path)
    except ParserError as exc:
        logger.error("Extraction bloquante: %s", exc)
        raise SystemExit(1) from exc

    data = parsed.values
    if args.pose:
        data["bdc_chk_livraison_poseur"] = True
        data["bdc_chk_livraison_client"] = False
        # si la prestation est absente, on laisse vide mais on reste cohérent
        data["bdc_montant_pose_ht"] = data.get("bdc_montant_pose_ht", "")
    else:
        data["bdc_chk_livraison_poseur"] = False
        data["bdc_chk_livraison_client"] = True
        data["bdc_montant_pose_ht"] = ""
        data["bdc_livraison_bloc"] = "idem"

    output_dir = Path(args.output_dir)
    output_name = build_output_name(
        data.get("bdc_client_nom", ""), data.get("bdc_ref_affaire", "")
    )
    output_path = output_dir / output_name

    filler = BdcFiller(template_path=template_path, logger=logger)
    result = filler.fill(data, output_path)
    logger.info("BDC généré: %s", result)
    return result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Génération déterministe de bon de commande (BDC) depuis un devis SRX."
    )
    parser.add_argument("devis", type=Path, help="Chemin du PDF devis SRX.")
    parser.add_argument(
        "--template",
        type=Path,
        default=DEFAULT_TEMPLATE,
        help="Chemin du template BDC (AcroForm).",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=DEFAULT_OUTPUT_DIR,
        help="Dossier de sortie (BDC_Output).",
    )
    parser.add_argument(
        "--pose",
        action="store_true",
        help="Marque la pose comme vendue et copie le prix de prestation.",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Active les logs détaillés.",
    )
    args = parser.parse_args(argv)

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO, format="%(message)s"
    )
    logger = logging.getLogger("bdc")

    try:
        run(args, logger=logger)
    except FileNotFoundError as exc:
        logger.error(str(exc))
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
