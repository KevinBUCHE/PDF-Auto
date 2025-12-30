from __future__ import annotations

from pathlib import Path

from pypdf import PdfReader, PdfWriter
from pypdf.generic import BooleanObject, NameObject

from .validator import ValidationError


CHECKBOX_ON = "/Yes"


class BdcFiller:
    def __init__(self, logger=None):
        self.logger = logger or (lambda message: None)

    def build_field_values(self, data: dict) -> dict:
        values: dict = {}

        def set_text(field: str, value: str | None):
            if value:
                values[field] = value

        def set_checkbox(field: str, checked: bool):
            if checked:
                values[field] = CHECKBOX_ON

        set_text("bdc_devis_annee_mois", data.get("bdc_devis_annee_mois"))
        set_text("bdc_ref_affaire", data.get("bdc_ref_affaire"))
        set_text("bdc_client_nom", data.get("bdc_client_nom"))
        set_text("bdc_client_adresse", data.get("bdc_client_adresse"))
        set_text("bdc_client_cp", data.get("bdc_client_cp"))
        set_text("bdc_client_ville", data.get("bdc_client_ville"))
        set_text("bdc_commercial_nom", data.get("bdc_commercial_nom"))
        set_text("bdc_esc_gamme", data.get("bdc_esc_gamme"))

        set_checkbox("bdc_chk_avec-contre-marches", data.get("bdc_chk_avec_contre_marches", False))
        set_checkbox("bdc_chk_avec-sans-marches", data.get("bdc_chk_sans_contre_marches", False))

        structure = data.get("bdc_structure_checkboxes") or {}
        for field, checked in structure.items():
            set_checkbox(field, bool(checked))

        set_text("bdc_esc_tete_de_poteau", data.get("bdc_esc_tete_de_poteau"))
        set_text(
            "bdc_esc_section_remplissage_garde_corps_rampant",
            data.get("bdc_esc_section_remplissage_garde_corps_rampant"),
        )
        set_text(
            "bdc_esc_section_remplissage_garde_corps_etage",
            data.get("bdc_esc_section_remplissage_garde_corps_etage"),
        )
        set_text(
            "bdc_esc_remplissage_garde_corps_soubassement",
            data.get("bdc_esc_remplissage_garde_corps_soubassement"),
        )

        set_text("bdc_esc_essence", data.get("bdc_esc_essence"))
        set_text("bdc_esc_finition_marches", data.get("bdc_esc_finition_marches"))
        set_text("bdc_esc_finition_contremarche", data.get("bdc_esc_finition_contremarche"))
        set_text("bdc_esc_finition_structure", data.get("bdc_esc_finition_structure"))
        set_text("bdc_esc_finition_mains_courante", data.get("bdc_esc_finition_mains_courante"))

        set_text("bdc_montant_fourniture_ht", data.get("bdc_montant_fourniture_ht"))
        set_text("bdc_montant_pose_ht", data.get("bdc_montant_pose_ht"))

        pose_vendue = bool(data.get("pose_vendue"))
        set_checkbox("bdc_chk_livraison_poseur", pose_vendue)
        set_checkbox("bdc_chk_livraison_client", not pose_vendue)
        set_checkbox("bdc_chk_autoliquidation", pose_vendue)
        if pose_vendue:
            depot_text = data.get("bdc_client_adresse", "")
            if data.get("bdc_client_cp") and data.get("bdc_client_ville"):
                depot_text = depot_text + "\n" + f"{data.get('bdc_client_cp')} {data.get('bdc_client_ville')}"
            set_text("bdc_livraison_bloc", depot_text.strip())

        return values

    def fill(self, template_path: Path, data: dict, output_path: Path) -> Path:
        values = self.build_field_values(data)
        reader = PdfReader(template_path)
        writer = PdfWriter()
        writer.append(reader)

        if "/AcroForm" in writer._root_object:  # type: ignore[attr-defined]
            writer._root_object["/AcroForm"].update({NameObject("/NeedAppearances"): BooleanObject(True)})  # type: ignore[attr-defined]

        writer.update_page_form_field_values(writer.pages, values)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        with output_path.open("wb") as handle:
            writer.write(handle)

        self._validate_output(output_path, values)
        self.logger(f"BDC généré: {output_path}")
        return output_path

    def _validate_output(self, output_path: Path, expected: dict) -> None:
        reader = PdfReader(output_path)
        fields = reader.get_fields() or {}
        for field in ("bdc_client_nom", "bdc_ref_affaire", "bdc_devis_annee_mois"):
            value = ""
            if field in fields and "/V" in fields[field]:
                value = str(fields[field]["/V"]).strip()
            if not value and expected.get(field):
                raise ValidationError(f"Champ '{field}' absent du PDF généré.")
