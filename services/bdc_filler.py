from __future__ import annotations

import logging
import inspect
from pathlib import Path
from typing import Dict

from pypdf import PdfReader, PdfWriter
from pypdf.generic import BooleanObject, NameObject


CRITICAL_FIELDS = ["bdc_client_nom", "bdc_devis_annee_mois", "bdc_ref_affaire"]
OFF_NAME = NameObject("/Off")
SUPPORTS_AUTO_REGENERATE = "auto_regenerate" in inspect.signature(
    PdfWriter.update_page_form_field_values
).parameters


class BdcFiller:
    def __init__(self, template_path: Path, logger: logging.Logger | None = None):
        self.template_path = template_path
        self.logger = logger or logging.getLogger(__name__)

    def fill(self, data: Dict[str, str | bool], output_path: Path) -> Path:
        reader = PdfReader(self.template_path)
        writer = PdfWriter()
        writer.clone_reader_document_root(reader)

        acro_form = writer._root_object.get("/AcroForm")
        if acro_form is None:
            raise ValueError("Le template ne contient pas de champs de formulaire.")
        acro_form.update({NameObject("/NeedAppearances"): BooleanObject(True)})

        text_values = {
            key: value
            for key, value in data.items()
            if not key.startswith("bdc_chk_") and isinstance(value, str)
        }
        update_kwargs = {"auto_regenerate": True} if SUPPORTS_AUTO_REGENERATE else {}
        for page in writer.pages:
            writer.update_page_form_field_values(page, text_values, **update_kwargs)

        self._fill_checkboxes(writer, data)

        output_path.parent.mkdir(parents=True, exist_ok=True)
        with output_path.open("wb") as handle:
            writer.write(handle)

        self._validate_written_file(output_path, data)
        return output_path

    def _fill_checkboxes(self, writer: PdfWriter, data: Dict[str, str | bool]) -> None:
        acro_form = writer._root_object["/AcroForm"]
        fields = acro_form.get("/Fields", [])
        checkbox_values = {k: v for k, v in data.items() if k.startswith("bdc_chk_")}
        for field_ref in fields:
            field = field_ref.get_object()
            name = field.get("/T")
            if name in checkbox_values:
                self._set_checkbox(field, bool(checkbox_values[name]))

    def _set_checkbox(self, field, flag: bool) -> None:
        on_value = self._checkbox_on_value(field)
        target = NameObject(on_value)
        field.update({NameObject("/V"): target if flag else OFF_NAME})
        for kid in field.get("/Kids", []):
            kid_obj = kid.get_object()
            kid_obj.update({NameObject("/AS"): target if flag else OFF_NAME})

    def _checkbox_on_value(self, field) -> str:
        appearances = field.get("/AP")
        if appearances:
            normal = appearances.get("/N")
            if normal:
                try:
                    keys = list(normal.keys())
                except Exception:
                    keys = []
                for key in keys:
                    if key != OFF_NAME:
                        return str(key)
        return "/Yes"

    def _validate_written_file(self, output_path: Path, data: Dict[str, str | bool]) -> None:
        reader = PdfReader(output_path)
        acro_form = reader.trailer["/Root"].get("/AcroForm")
        if not acro_form:
            raise ValueError("PDF généré sans formulaire.")
        fields = acro_form.get("/Fields", [])
        values = {}
        for field_ref in fields:
            obj = field_ref.get_object()
            name = obj.get("/T")
            if not name:
                continue
            value = obj.get("/V")
            if hasattr(value, "name"):
                values[name] = value.name
            else:
                values[name] = str(value) if value is not None else ""
        for key in CRITICAL_FIELDS:
            expected = data.get(key, "")
            actual = values.get(key, "")
            if expected and expected not in actual:
                raise ValueError(f"Le champ {key} n'a pas été persisté correctement.")
