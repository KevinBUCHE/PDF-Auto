from pathlib import Path
from datetime import date
import logging
import traceback
from typing import Callable, Optional

from pypdf import PdfReader, PdfWriter
from pypdf.generic import BooleanObject, NameObject, TextStringObject


TEXT_FIELDS = {
    "bdc_date_commande",
    "bdc_client_nom",
    "bdc_client_adresse",
    "bdc_commercial_nom",
    "bdc_ref_affaire",
    "bdc_devis_annee_mois",
    "bdc_devis_num",
    "bdc_montant_fourniture_ht",
    "bdc_montant_pose_ht",
    "bdc_livraison_bloc",
    "bdc_esc_gamme",
    "bdc_esc_essence",
    "bdc_esc_finition_marches",
    "bdc_esc_tete_de_poteau",
    "bdc_esc_poteaux_depart",
}

CHECKBOX_FIELDS = {
    "bdc_chk_livraison_poseur",
    "bdc_chk_livraison_client",
}

CRITICAL_FIELDS = {
    "bdc_devis_annee_mois",
    "bdc_devis_num",
}


class BdcFiller:
    def __init__(self, logger: Optional[Callable[[str], None]] = None):
        self._logger = logger

    def fill(self, template_path: Path, data: dict, output_path: Path):
        try:
            if not template_path.exists():
                raise FileNotFoundError(template_path)
            reader = PdfReader(str(template_path))
            acroform, field_map = self._extract_fields(reader)
            acroform_fields = acroform.get("/Fields") if acroform else None
            self._log(f"Template utilisé: {template_path}")
            bdc_fields = {
                name for name in field_map.keys() if str(name).startswith("bdc_")
            }
            self._log(f"Champs bdc_* détectés: {len(bdc_fields)}")
            self._log(f"Liste champs bdc_*: {sorted(bdc_fields)}")
            if not acroform or not acroform_fields:
                raise ValueError(
                    "Template PDF is missing /AcroForm or /Fields; cannot fill form fields."
                )
            writer = PdfWriter()
            for page in reader.pages:
                writer.add_page(page)

            acroform.update({NameObject("/NeedAppearances"): BooleanObject(True)})
            writer._root_object.update({NameObject("/AcroForm"): acroform})

            fields = self._build_fields(data)
            checkbox_states = self._build_checkbox_states(data)

            missing_critical = [
                name for name in CRITICAL_FIELDS if name not in bdc_fields
            ]
            for name in sorted(TEXT_FIELDS | CHECKBOX_FIELDS):
                if name not in bdc_fields:
                    self._log(f"Champ bdc_* introuvable: {name}")
            if missing_critical:
                raise ValueError(
                    "Champs critiques manquants dans le template: "
                    f"{', '.join(missing_critical)}"
                )

            self._apply_text_fields(field_map, fields, bdc_fields)
            self._apply_checkboxes(field_map, checkbox_states, bdc_fields)

            output_path.parent.mkdir(parents=True, exist_ok=True)
            with open(output_path, "wb") as output_file:
                writer.write(output_file)
        except Exception as exc:
            self._log(f"Erreur: {type(exc).__name__}: {exc}")
            self._log(traceback.format_exc())
            raise

    def _log(self, message: str):
        if callable(self._logger):
            self._logger(message)
        else:
            logging.getLogger(__name__).info(message)

    def _build_fields(self, data: dict):
        pose_sold = bool(data.get("pose_sold"))
        livraison_bloc = "" if pose_sold else "idem"
        client_adresse = self._build_client_adresse(data)
        return {
            "bdc_client_nom": data.get("client_nom", ""),
            "bdc_client_adresse": client_adresse,
            "bdc_commercial_nom": data.get("commercial_nom", ""),
            "bdc_date_commande": date.today().strftime("%d/%m/%Y"),
            "bdc_ref_affaire": data.get("ref_affaire", ""),
            "bdc_devis_annee_mois": data.get("devis_annee_mois", ""),
            "bdc_devis_num": data.get("devis_num", ""),
            "bdc_montant_fourniture_ht": data.get("fourniture_ht", ""),
            "bdc_montant_pose_ht": self._pose_amount(data),
            "bdc_livraison_bloc": livraison_bloc,
            "bdc_esc_gamme": data.get("esc_gamme", ""),
            "bdc_esc_finition_marches": data.get("esc_finition_marches", ""),
            "bdc_esc_essence": data.get("esc_essence", ""),
            "bdc_esc_tete_de_poteau": data.get("esc_tete_de_poteau", ""),
            "bdc_esc_poteaux_depart": data.get("esc_poteaux_depart", ""),
        }

    def _build_checkbox_states(self, data: dict):
        pose_sold = bool(data.get("pose_sold"))
        return {
            "bdc_chk_livraison_client": not pose_sold,
            "bdc_chk_livraison_poseur": pose_sold,
        }

    def _pose_amount(self, data: dict) -> str:
        if data.get("pose_sold"):
            return data.get("pose_amount") or data.get("prestations_ht", "")
        return data.get("prestations_ht", "")

    def _build_client_adresse(self, data: dict) -> str:
        lines = []
        for key in ("client_adresse1", "client_adresse2"):
            value = (data.get(key) or "").strip()
            if value:
                lines.append(value)
        cp = (data.get("client_cp") or "").strip()
        ville = (data.get("client_ville") or "").strip()
        if cp or ville:
            lines.append(" ".join(part for part in (cp, ville) if part))
        return "\n".join(lines)

    def _apply_text_fields(self, field_map: dict, fields: dict, bdc_fields: set[str]):
        for name, value in fields.items():
            if name not in bdc_fields:
                continue
            entry = field_map.get(name)
            if not entry:
                continue
            field = entry["field"]
            text_value = TextStringObject("" if value is None else str(value))
            field.update({NameObject("/V"): text_value})

    def _apply_checkboxes(
        self, field_map: dict, checkbox_states: dict, bdc_fields: set[str]
    ):
        for name, state in checkbox_states.items():
            if name not in bdc_fields:
                continue
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
