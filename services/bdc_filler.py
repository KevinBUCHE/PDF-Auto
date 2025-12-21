from pathlib import Path
from datetime import date
import logging

from pypdf import PdfReader, PdfWriter


class BdcFiller:
    def fill(self, template_path: Path, data: dict, output_path: Path):
        if not template_path.exists():
            raise FileNotFoundError(template_path)
        reader = PdfReader(str(template_path))
        fields_dict = reader.get_fields() or {}
        root = reader.trailer.get("/Root", {})
        acroform = root.get("/AcroForm")
        acroform_fields = acroform.get("/Fields") if acroform else None
        logger = logging.getLogger(__name__)
        logger.info(
            "BDC template loaded: pages=%s fields=%s acroform=%s fields_present=%s",
            len(reader.pages),
            len(fields_dict),
            bool(acroform),
            bool(acroform_fields),
        )
        if not acroform or not acroform_fields:
            raise ValueError(
                "Template PDF is missing /AcroForm or /Fields; cannot fill form fields."
            )
        writer = PdfWriter()
        for page in reader.pages:
            writer.add_page(page)

        acroform.update({"/NeedAppearances": True})
        writer._root_object.update({"/AcroForm": acroform})

        fields = {
            "bdc_devis_annee_mois": data.get("devis_annee_mois", ""),
            "bdc_devis_num": data.get("devis_num", ""),
            "bdc_devis_type": data.get("devis_type", ""),
            "bdc_date_commande": date.today().strftime("%d/%m/%Y"),
            "bdc_ref_affaire": data.get("ref_affaire", ""),
            "bdc_client_nom": data.get("client_nom", ""),
            "bdc_client_adresse": data.get("client_adresse", ""),
            "bdc_commercial_nom": "BUCHE Kevin",
            "bdc_livraison_bloc": "idem" if not data.get("pose_sold") else "",
            "bdc_montant_pose_ht": self._pose_amount(data),
            "bdc_montant_fourniture_ht": data.get("fourniture_ht", ""),
            "bdc_total_ht": data.get("total_ht", ""),
            "bdc_esc_gamme": data.get("esc_gamme", ""),
            "bdc_esc_finition_marches": data.get("esc_finition_marches", ""),
            "bdc_esc_essence": data.get("esc_essence", ""),
            "bdc_esc_tete_de_poteau": data.get("esc_tete_de_poteau", ""),
            "bdc_esc_poteaux_depart": data.get("esc_poteaux_depart", ""),
        }

        checkbox_states = {
            "bdc_chk_livraison_client": not data.get("pose_sold"),
            "bdc_chk_livraison_poseur": bool(data.get("pose_sold")),
        }

        for page in writer.pages:
            writer.update_page_form_field_values(page, fields)
        self._apply_text_fields(writer, fields)
        self._apply_checkboxes(writer, checkbox_states)

        output_path.parent.mkdir(parents=True, exist_ok=True)
        with open(output_path, "wb") as output_file:
            writer.write(output_file)

    def _pose_amount(self, data: dict) -> str:
        if data.get("pose_sold"):
            return data.get("pose_amount") or data.get("prestations_ht", "")
        return data.get("prestations_ht", "")

    def _apply_text_fields(self, writer: PdfWriter, fields: dict):
        acroform = writer._root_object.get("/AcroForm")
        if not acroform:
            return
        root_fields = acroform.get("/Fields", [])
        for name, value in fields.items():
            self._set_field_value(root_fields, name, value)

    def _set_field_value(self, fields, name, value):
        found = False
        for field in fields:
            if field.get("/T") == name:
                field.update({"/V": value, "/DV": value})
                for kid in field.get("/Kids", []):
                    kid.update({"/V": value, "/DV": value})
                found = True
            if self._set_field_value(field.get("/Kids", []), name, value):
                found = True
        return found

    def _apply_checkboxes(self, writer: PdfWriter, checkbox_states: dict):
        acroform = writer._root_object.get("/AcroForm")
        if not acroform:
            return
        root_fields = acroform.get("/Fields", [])
        for name, state in checkbox_states.items():
            value = "/Yes" if state else "/Off"
            self._set_checkbox_value(root_fields, name, value)

    def _set_checkbox_value(self, fields, name, value):
        found = False
        for field in fields:
            if field.get("/T") == name:
                field.update({"/V": value})
                for kid in field.get("/Kids", []):
                    kid.update({"/V": value, "/AS": value})
                found = True
            if self._set_checkbox_value(field.get("/Kids", []), name, value):
                found = True
        return found
