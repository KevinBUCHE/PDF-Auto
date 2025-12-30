from __future__ import annotations

import argparse
import sys
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox

from services.bdc_filler import BdcFiller
from services.devis_parser import DevisParser
from services.rules import APP_NAME, TEMPLATE_NAME
from services.template_locator import TemplateNotFoundError, locate_template
from services.validator import ValidationError, to_dict, validate_parsed_devis
from utils.logging_util import append_log


def resolve_base_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).parent
    return Path(__file__).resolve().parent


def build_output_path(devis_path: Path) -> Path:
    return devis_path.with_name(f"{devis_path.stem}_BDC.pdf")


class Application(tk.Tk):
    def __init__(self) -> None:
        super().__init__()
        self.title(APP_NAME)
        self.geometry("640x360")
        self.resizable(False, False)

        self.base_dir = resolve_base_dir()
        self.parser = DevisParser()
        self.filler = BdcFiller(logger=self._log)
        self.selected_devis: Path | None = None
        self.log_path = self.base_dir / "logs" / "bdc_generator.log"

        self._build_ui()
        self._refresh_template_status()

    def _build_ui(self) -> None:
        frame = tk.Frame(self, padx=12, pady=12)
        frame.pack(fill=tk.BOTH, expand=True)

        tk.Label(
            frame,
            text=(
                "Sélectionnez un devis PDF SRX puis générez le BDC en remplissant "
                f"le template '{TEMPLATE_NAME}'."
            ),
            justify=tk.LEFT,
            wraplength=600,
        ).pack(anchor="w")

        self.template_status = tk.Label(frame, fg="red", font=("Arial", 10, "bold"))
        self.template_status.pack(anchor="w", pady=(8, 4))

        buttons = tk.Frame(frame)
        buttons.pack(anchor="w", pady=(4, 4))
        tk.Button(buttons, text="Choisir devis PDF", command=self._choose_devis).grid(row=0, column=0, padx=4)
        tk.Button(buttons, text="Générer BDC", command=self._generate_bdc).grid(row=0, column=1, padx=4)

        self.selected_label = tk.Label(frame, text="Aucun devis sélectionné", fg="#444")
        self.selected_label.pack(anchor="w", pady=(6, 6))

        tk.Label(frame, text="Journal:", font=("Arial", 10, "bold")).pack(anchor="w")
        self.log_widget = tk.Text(frame, height=10, state=tk.DISABLED)
        self.log_widget.pack(fill=tk.BOTH, expand=True, pady=(4, 0))

    def _choose_devis(self) -> None:
        filename = filedialog.askopenfilename(filetypes=[("PDF files", "*.pdf")])
        if filename:
            self.selected_devis = Path(filename)
            self.selected_label.config(text=str(self.selected_devis))
            self._log(f"Devis sélectionné: {self.selected_devis}")

    def _generate_bdc(self) -> None:
        if not self.selected_devis:
            messagebox.showerror(APP_NAME, "Aucun devis PDF sélectionné.")
            return
        try:
            template_path = locate_template(self.base_dir)
        except TemplateNotFoundError as exc:
            messagebox.showerror(APP_NAME, str(exc))
            self._log(str(exc))
            return

        try:
            parsed = self.parser.parse(self.selected_devis)
            parsed = validate_parsed_devis(parsed)
            data = to_dict(parsed)
            output_path = build_output_path(self.selected_devis)
            self.filler.fill(template_path, data, output_path)
            self._log(f"BDC généré: {output_path}")
            messagebox.showinfo(APP_NAME, f"BDC généré: {output_path}")
        except ValidationError as exc:
            messagebox.showerror(APP_NAME, str(exc))
            self._log(str(exc))
        except Exception as exc:  # pylint: disable=broad-except
            messagebox.showerror(APP_NAME, f"Erreur: {exc}")
            self._log(f"Erreur: {exc}")

    def _refresh_template_status(self) -> None:
        try:
            path = locate_template(self.base_dir)
            self.template_status.config(text=f"Template OK: {path}", fg="#1b8f1b")
        except TemplateNotFoundError as exc:
            self.template_status.config(text=str(exc), fg="red")

    def _log(self, message: str) -> None:
        self.log_widget.configure(state=tk.NORMAL)
        self.log_widget.insert(tk.END, message + "\n")
        self.log_widget.configure(state=tk.DISABLED)
        append_log(self.log_path, message)
        self.log_widget.see(tk.END)


def run_cli(args: argparse.Namespace) -> int:
    base_dir = resolve_base_dir()
    parser = DevisParser()
    filler = BdcFiller(logger=print)
    try:
        template_path = locate_template(base_dir)
    except TemplateNotFoundError as exc:
        print(exc)
        return 1

    devis_path = Path(args.devis)
    parsed = parser.parse(devis_path)
    parsed = validate_parsed_devis(parsed)
    data = to_dict(parsed)
    output_path = build_output_path(devis_path)
    filler.fill(template_path, data, output_path)
    print(f"BDC généré: {output_path}")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="BDC Generator minimal")
    parser.add_argument("--cli", action="store_true", help="Exécuter en ligne de commande (sans interface Tk)")
    parser.add_argument("--devis", help="Chemin du devis PDF SRX (pour --cli)")
    args = parser.parse_args()

    if args.cli:
        if not args.devis:
            parser.error("--devis est requis en mode --cli")
        return run_cli(args)

    app = Application()
    app.mainloop()
    return 0


if __name__ == "__main__":
    sys.exit(main())
