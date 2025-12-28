from datetime import date
from pathlib import Path

from pypdf import PdfReader, PdfWriter


class BdcFiller:
    def fill(self, template_path: Path, data: dict, output_path: Path, depot_adresse: str = ""):
        if not template_path.exists():
            raise FileNotFoundError(template_path)
        reader = PdfReader(str(template_path))
        writer = PdfWriter()
        for page in reader.pages:
            writer.add_page(page)

        if "/AcroForm" in reader.trailer.get("/Root", {}):
            acroform = reader.trailer["/Root"]["/AcroForm"]
            acroform.update({"/NeedAppearances": True})
            writer._root_object.update({"/AcroForm": acroform})
        else:
            writer._root_object.update({"/AcroForm": {"/NeedAppearances": True}})

        fields = {
            "bdc_devis_annee_mois": data.get("devis_annee_mois", ""),
            "bdc_devis_num": data.get("devis_num", ""),
            "bdc_devis_type": data.get("devis_type", ""),
            "bdc_date_commande": date.today().strftime("%d/%m/%Y"),
            "bdc_ref_affaire": data.get("ref_affaire", ""),
            "bdc_client_nom": data.get("client_nom", ""),
            "bdc_client_adresse": data.get("client_adresse", ""),
            "bdc_commercial_nom": data.get("commercial_nom") or "BUCHE Kevin",
            "bdc_livraison_bloc": self._delivery_block(data, depot_adresse),
            "bdc_montant_pose_ht": self._pose_amount(data),
            "bdc_montant_fourniture_ht": data.get("fourniture_ht", ""),
            "bdc_total_ht": data.get("total_ht", ""),
            "bdc_esc_gamme": data.get("esc_gamme", ""),
            "bdc_esc_finition_marches": data.get("esc_finition_marches", ""),
            "bdc_esc_finition_contremarche": data.get("esc_finition_contremarche", ""),
            "bdc_esc_finition_structure": data.get("esc_finition_structure", ""),
            "bdc_esc_finition_mains_courante": data.get("esc_finition_mains_courante", ""),
            "bdc_esc_essence": data.get("esc_essence", ""),
            "bdc_esc_tete_de_poteau": data.get("esc_tete_de_poteau", ""),
            "bdc_esc_poteaux_depart": data.get("esc_poteaux_depart", ""),
            "bdc_esc_section_remplissage_garde_corps_rampant": data.get(
                "remplissage_rampant", ""
            ),
            "bdc_esc_section_remplissage_garde_corps_etage": data.get(
                "remplissage_etage", ""
            ),
            "bdc_esc_remplissage_garde_corps_soubassement": data.get(
                "remplissage_soubassement", ""
            ),
        }

        checkbox_states = {
            "bdc_chk_livraison_client": not data.get("pose_sold"),
            "bdc_chk_livraison_poseur": bool(data.get("pose_sold")),
            "bdc_chk_autoliquidation": self._autoliquidation_state(data),
            "bdc_chk_avec-sans-marches": bool(data.get("contremarche_sans")),
            "bdc_chk_avec-contre-marches": bool(data.get("contremarche_avec")),
            "bdc_chk_cremaillere": data.get("structure_type") == "cremaillere",
            "bdc_chk_limon_centrale": data.get("structure_type") == "limon_central",
            "bdc_chk_limon_decoupe": data.get("structure_type") == "limon_decoupe",
            "bdc_chk_limon": data.get("structure_type") == "limon",
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
        return ""

    def _autoliquidation_state(self, data: dict) -> bool:
        amount = self._pose_amount(data)
        if not amount or amount == "0,00":
            return False
        return True

    def _delivery_block(self, data: dict, depot_adresse: str) -> str:
        if data.get("pose_sold"):
            return depot_adresse
        return "idem"

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
