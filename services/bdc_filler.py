from pathlib import Path
from datetime import date
import logging

from pypdf import PdfReader, PdfWriter
from pypdf.generic import BooleanObject, NameObject, TextStringObject


class BdcFiller:
    def fill(self, template_path: Path, data: dict, output_path: Path):
        if not template_path.exists():
            raise FileNotFoundError(template_path)
        reader = PdfReader(str(template_path))
        acroform, field_map = self._extract_fields(reader)
        acroform_fields = acroform.get("/Fields") if acroform else None
        logger = logging.getLogger(__name__)
        logger.info(
            "BDC template loaded: pages=%s acroform=%s fields_present=%s",
            len(reader.pages),
            bool(acroform),
            bool(acroform_fields),
        )
        logger.info(
            "BDC template fields (fallback): count=%s sample=%s",
            len(field_map),
            list(field_map.keys())[:10],
        )
        if not acroform or not acroform_fields:
            raise ValueError(
                "Template PDF is missing /AcroForm or /Fields; cannot fill form fields."
            )
        writer = PdfWriter()
        for page in reader.pages:
            writer.add_page(page)

        acroform.update({NameObject("/NeedAppearances"): BooleanObject(True)})
        writer._root_object.update({NameObject("/AcroForm"): acroform})

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
        self._apply_text_fields(field_map, fields)
        self._apply_checkboxes(field_map, checkbox_states)

        output_path.parent.mkdir(parents=True, exist_ok=True)
        with open(output_path, "wb") as output_file:
            writer.write(output_file)

    def _pose_amount(self, data: dict) -> str:
        if data.get("pose_sold"):
            return data.get("pose_amount") or data.get("prestations_ht", "")
        return data.get("prestations_ht", "")

    def _apply_text_fields(self, field_map: dict, fields: dict):
        for name, value in fields.items():
            entry = field_map.get(name)
            if not entry:
                continue
            field = entry["field"]
            text_value = TextStringObject("" if value is None else str(value))
            field.update({NameObject("/V"): text_value, NameObject("/DV"): text_value})
            for kid in field.get("/Kids", []):
                kid.update({NameObject("/V"): text_value, NameObject("/DV"): text_value})

    def _apply_checkboxes(self, field_map: dict, checkbox_states: dict):
        for name, state in checkbox_states.items():
            entry = field_map.get(name)
            if not entry:
                continue
            field = entry["field"]
            widgets = entry.get("widgets", [])
            on_value = self._get_checkbox_on_value(widgets)
            value = on_value if state else NameObject("/Off")
            field.update({NameObject("/V"): value})
            for widget in widgets:
                widget.update({NameObject("/AS"): value})

    def _get_checkbox_on_value(self, widgets):
        for widget in widgets:
            ap = widget.get("/AP")
            if not ap:
                continue
            normal = ap.get("/N")
            if not normal:
                continue
            for key in normal.keys():
                if str(key) != "/Off":
                    return NameObject(str(key))
        return NameObject("/Yes")

    def _extract_fields(self, reader: PdfReader):
        root = reader.trailer.get("/Root", {})
        acroform = root.get("/AcroForm")
        fields = acroform.get("/Fields", []) if acroform else []
        field_map = {}

        def walk(nodes):
            for node in nodes:
                name = node.get("/T")
                name_str = None
                if isinstance(name, (NameObject, TextStringObject, str)):
                    name_str = str(name)
                entry = None
                if name_str:
                    entry = field_map.setdefault(
                        name_str, {"field": node, "widgets": []}
                    )
                if node.get("/Subtype") == "/Widget" and entry is not None:
                    entry["widgets"].append(node)
                kids = node.get("/Kids", [])
                if entry is not None:
                    for kid in kids:
                        if kid.get("/Subtype") == "/Widget":
                            entry["widgets"].append(kid)
                if kids:
                    walk(kids)

        walk(fields)
        return acroform, field_map
