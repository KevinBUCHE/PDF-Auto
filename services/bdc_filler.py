from pathlib import Path

from pypdf import PdfReader, PdfWriter


class BdcFiller:
    def fill(self, template_path: Path, data: dict, output_path: Path):
        if not template_path.exists():
            raise FileNotFoundError(template_path)
        reader = PdfReader(str(template_path))
        writer = PdfWriter()
        for page in reader.pages:
            writer.add_page(page)

        fields = {
            "bdc_devis_annee_mois": data.get("devis_annee_mois", ""),
            "bdc_devis_num": data.get("devis_num", ""),
            "bdc_devis_type": data.get("devis_type", ""),
            "bdc_livraison_bloc": "idem" if not data.get("pose_sold") else "",
            "bdc_montant_pose_ht": self._pose_amount(data),
            "bdc_prestations_ht": data.get("prestations_ht", ""),
            "bdc_fourniture_ht": data.get("fourniture_ht", ""),
            "bdc_total_ht": data.get("total_ht", ""),
        }

        checkbox_states = {
            "bdc_livraison_client": not data.get("pose_sold"),
            "bdc_livraison_poseur": bool(data.get("pose_sold")),
        }

        for page in writer.pages:
            writer.update_page_form_field_values(page, fields)
        self._apply_checkboxes(writer, checkbox_states)

        if "/AcroForm" in reader.trailer.get("/Root", {}):
            acroform = reader.trailer["/Root"]["/AcroForm"]
            acroform.update({"/NeedAppearances": True})
            writer._root_object.update({"/AcroForm": acroform})
        else:
            writer._root_object.update({"/AcroForm": {"/NeedAppearances": True}})

        output_path.parent.mkdir(parents=True, exist_ok=True)
        with open(output_path, "wb") as output_file:
            writer.write(output_file)

    def _pose_amount(self, data: dict) -> str:
        if data.get("pose_sold"):
            return data.get("pose_amount") or data.get("prestations_ht", "")
        return data.get("prestations_ht", "")

    def _apply_checkboxes(self, writer: PdfWriter, checkbox_states: dict):
        fields = writer.get_fields() or {}
        for name, state in checkbox_states.items():
            field = fields.get(name)
            if not field:
                continue
            value = "/Yes" if state else "/Off"
            field.update({"/V": value, "/AS": value})
