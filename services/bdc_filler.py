from __future__ import annotations

from pathlib import Path
from typing import Dict, Optional

from pypdf import PdfReader, PdfWriter
from pypdf.generic import ArrayObject, BooleanObject, DictionaryObject, NameObject

from .devis_parser import ParseResult
from . import sanitize


class BdcFiller:
    def __init__(self, template_path: Path):
        self.template_path = Path(template_path)

    def fill(self, output_pdf: Path, parsed: ParseResult, config: Dict[str, str]) -> None:
        reader = PdfReader(str(self.template_path))
        writer = PdfWriter()
        writer.clone_reader_document_root(reader)

        field_names = self._collect_field_names(reader)
        checkbox_on_values = self._collect_checkbox_on_values(reader)

        address_lines = [
            parsed.data.client_contact,
            parsed.data.client_adresse1,
            parsed.data.client_adresse2,
            " ".join(part for part in [parsed.data.client_cp, parsed.data.client_ville] if part).strip(),
        ]
        address_block = "\n".join([line for line in address_lines if line])

        text_updates = {
            "bdc_client_nom": parsed.data.client_nom,
            "bdc_client_adresse": address_block,
            "bdc_ref_affaire": parsed.data.ref_affaire,
            "bdc_commercial_nom": parsed.data.commercial_nom,
            "bdc_montant_fourniture_ht": parsed.data.fourniture_ht,
            "bdc_montant_pose_ht": parsed.data.prestations_ht,
            "bdc_esc_gamme": parsed.data.esc_gamme,
            "bdc_esc_essence": parsed.data.esc_essence,
            "bdc_esc_nez_de_marches": parsed.data.esc_nez_de_marches,
            "bdc_esc_tete_de_poteau": parsed.data.esc_tete_de_poteau,
            "bdc_esc_section_poteau": parsed.data.esc_poteaux_depart,
            "bdc_esc_poteaux_depart": parsed.data.esc_poteaux_depart,
            "bdc_esc_main_courante": parsed.data.esc_main_courante,
            "bdc_esc_main_courante_scellement": parsed.data.esc_main_courante_scellement,
            "bdc_esc_section_remplissage_garde_corps_rampant": parsed.data.esc_section_remplissage_garde_corps_rampant,
            "bdc_esc_section_remplissage_garde_corps_etage": parsed.data.esc_section_remplissage_garde_corps_etage,
            "bdc_esc_remplissage_garde_corps_soubassement": parsed.data.esc_remplissage_garde_corps_soubassement,
            "bdc_esc_finition_marches": parsed.data.esc_finition_marches,
            "bdc_esc_finition_structure": parsed.data.esc_finition_structure,
            "bdc_esc_finition_mains_courante": parsed.data.esc_finition_mains_courante,
            "bdc_esc_finition_rampe": parsed.data.esc_finition_rampe,
            "bdc_esc_finition_contremarche": parsed.data.esc_finition_contremarche,
            "bdc_devis_annee_mois": parsed.data.devis_num_complet,
            "bdc_devis_num": parsed.data.devis_num_complet,
            "bdc_client_tel": parsed.data.client_tel,
            "bdc_client_email": parsed.data.client_email,
        }

        adresse_depot_key = "bdc_adresse_depot_pose"
        if parsed.data.pose_sold and adresse_depot_key in field_names:
            text_updates[adresse_depot_key] = config.get("adresse_depot_pose", "")
        elif adresse_depot_key in field_names:
            text_updates[adresse_depot_key] = ""

        self._update_text_fields(writer, text_updates)

        self._set_checkbox(
            writer, "bdc_chk_avec-contre-marches", parsed.has_contremarches, checkbox_on_values, field_names
        )
        self._set_checkbox(
            writer, "bdc_chk_avec-sans-marches", not parsed.has_contremarches, checkbox_on_values, field_names
        )

        structure_mapping = {
            "limon": "bdc_chk_limon",
            "cremaillere": "bdc_chk_cremaillere",
            "limon_decoupe": "bdc_chk_limon_decoupe",
            "limon_centrale": "bdc_chk_limon_centrale",
        }
        for key, field_name in structure_mapping.items():
            self._set_checkbox(writer, field_name, parsed.structure_type == key, checkbox_on_values, field_names)

        autoliquidation_field = "bdc_chk_autoliquidation"
        self._set_checkbox(writer, autoliquidation_field, parsed.data.pose_sold, checkbox_on_values, field_names)

        livraison_poseur = parsed.data.pose_sold
        self._set_checkbox(writer, "bdc_chk_livraison_poseur", livraison_poseur, checkbox_on_values, field_names)
        self._set_checkbox(writer, "bdc_chk_livraison_client", not livraison_poseur, checkbox_on_values, field_names)

        if not livraison_poseur:
            self._update_text_fields(writer, {"bdc_livraison_bloc": "idem"})

        self._set_need_appearances(writer)

        with output_pdf.open("wb") as handle:
            writer.write(handle)

        self._validate_output(output_pdf)

    def _collect_field_names(self, reader: PdfReader) -> set[str]:
        names: set[str] = set()

        def walk(fields):
            for field in fields:
                obj = field.get_object() if hasattr(field, "get_object") else field
                if isinstance(obj, ArrayObject):
                    walk(obj)
                    continue
                if not isinstance(obj, DictionaryObject):
                    continue
                name = obj.get("/T")
                if name:
                    names.add(name)
                kids = obj.get("/Kids")
                if kids:
                    walk(kids)

        form = reader.trailer.get("/Root", {}).get("/AcroForm")
        if form and form.get("/Fields"):
            walk(form.get("/Fields"))
        return names

    def _collect_checkbox_on_values(self, reader: PdfReader) -> Dict[str, str]:
        mapping: Dict[str, str] = {}

        def walk(fields):
            for field in fields:
                obj = field.get_object() if hasattr(field, "get_object") else field
                if isinstance(obj, ArrayObject):
                    walk(obj)
                    continue
                if not isinstance(obj, DictionaryObject):
                    continue
                name = obj.get("/T")
                if name:
                    on_value = self._extract_on_value(obj)
                    if on_value:
                        mapping[name] = on_value
                kids = obj.get("/Kids")
                if kids:
                    walk(kids)

        form = reader.trailer.get("/Root", {}).get("/AcroForm")
        if form and form.get("/Fields"):
            walk(form.get("/Fields"))
        return mapping

    def _extract_on_value(self, field) -> Optional[str]:
        appearances = field.get("/AP")
        if isinstance(appearances, DictionaryObject):
            normal = appearances.get("/N")
            if isinstance(normal, DictionaryObject):
                try:
                    for key in normal.keys():
                        if key != "/Off":
                            return key
                except Exception:
                    return None
        return None

    def _set_checkbox(
        self,
        writer: PdfWriter,
        field_name: str,
        value: bool,
        checkbox_on_values: Dict[str, str],
        field_names: set[str],
    ) -> None:
        if field_name not in checkbox_on_values and field_name not in field_names:
            return
        target = checkbox_on_values.get(field_name, "/Yes") if value else "/Off"
        target_name = NameObject(target if target.startswith("/") else f"/{target}")
        for page in writer.pages:
            annotations = page.get("/Annots")
            if not annotations:
                continue
            for annotation in annotations:
                obj = annotation.get_object()
                if obj.get("/T") == field_name:
                    obj.update({NameObject("/V"): target_name, NameObject("/AS"): target_name})

    def _update_text_fields(self, writer: PdfWriter, updates: Dict[str, str]) -> None:
        for page in writer.pages:
            writer.update_page_form_field_values(page, updates)

    def _set_need_appearances(self, writer: PdfWriter) -> None:
        root = writer._root_object
        if "/AcroForm" not in root:
            root.update({NameObject("/AcroForm"): writer._add_object({})})
        form = root[NameObject("/AcroForm")]
        form.update({NameObject("/NeedAppearances"): BooleanObject(True)})

    def _validate_output(self, pdf_path: Path) -> None:
        reader = PdfReader(str(pdf_path))
        fields = self._read_field_values(reader)
        required = ["bdc_client_nom", "bdc_devis_annee_mois", "bdc_ref_affaire", "bdc_montant_fourniture_ht"]
        missing = [name for name in required if not fields.get(name)]
        if missing:
            raise ValueError(f"Champs obligatoires manquants: {', '.join(missing)}")

    def _read_field_values(self, reader: PdfReader) -> Dict[str, str]:
        values: Dict[str, str] = {}
        try:
            raw_fields = reader.get_fields() or {}
            for name, data in raw_fields.items():
                candidate = data.get("/V") or data.get("/DV")
                if candidate:
                    values[name] = str(candidate)
        except Exception:
            form = reader.trailer.get("/Root", {}).get("/AcroForm")
            if not form or not form.get("/Fields"):
                return values

            def walk(fields):
                for field in fields:
                    obj = field.get_object() if hasattr(field, "get_object") else field
                    if isinstance(obj, ArrayObject):
                        walk(obj)
                        continue
                    if not isinstance(obj, DictionaryObject):
                        continue
                    name = obj.get("/T")
                    value = obj.get("/V") or obj.get("/DV")
                    if name and value:
                        values[name] = str(value)
                    kids = obj.get("/Kids")
                    if kids:
                        walk(kids)

            walk(form.get("/Fields"))
        return values


def fill_bdc(template_path: Path, output_pdf: Path, parsed: ParseResult, config: Dict[str, str]) -> None:
    filler = BdcFiller(template_path)
    filler.fill(output_pdf, parsed, config)
