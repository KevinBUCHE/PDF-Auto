from pathlib import Path
from datetime import date
import logging
import traceback
from typing import Callable, Optional

from pypdf import PdfReader, PdfWriter
from pypdf.generic import BooleanObject, IndirectObject, NameObject, TextStringObject

from services.address_sanitizer import sanitize_client_address, strip_pollution_lines


TEXT_FIELDS = {
    "bdc_client_adresse",
    "bdc_client_nom",
    "bdc_commercial_nom",
    "bdc_date_commande",
    "bdc_devis_annee_mois",
    "bdc_devis_num",
    "bdc_esc_essence",
    "bdc_esc_finition_contremarche",
    "bdc_esc_finition_mains_courante",
    "bdc_esc_finition_marches",
    "bdc_esc_finition_rampe",
    "bdc_esc_finition_structure",
    "bdc_esc_gamme",
    "bdc_esc_main_courante",
    "bdc_esc_main_courante_scellement",
    "bdc_esc_nez_de_marches",
    "bdc_esc_poteaux_depart",
    "bdc_esc_remplissage_garde_corps_soubassement",
    "bdc_esc_section_poteau",
    "bdc_esc_section_remplissage_garde_corps_etage",
    "bdc_esc_section_remplissage_garde_corps_rampant",
    "bdc_esc_tete_de_poteau",
    "bdc_livraison_bloc",
    "bdc_montant_fourniture_ht",
    "bdc_montant_pose_ht",
    "bdc_ref_affaire",
}

CHECKBOX_FIELDS = {
    "bdc_chk_avec-contre-marches",
    "bdc_chk_avec-sans-marches",
    "bdc_chk_cremaillere",
    "bdc_chk_habillage_de_dalle_complet",
    "bdc_chk_habillage_de_dalle_corniere",
    "bdc_chk_habillage_de_dalle_sans",
    "bdc_chk_habillage_de_dalle_standard",
    "bdc_chk_limon",
    "bdc_chk_limon_centrale",
    "bdc_chk_limon_decoupe",
    "bdc_chk_livraison_client",
    "bdc_chk_livraison_poseur",
    "bdc_chk_main_courante_scellement_cintree",
    "bdc_chk_main_courante_scellement_droite",
    "bdc_chk_marche_arrondi",
    "bdc_chk_marche_devant-poteaux",
    "bdc_chk_marche_droite",
    "bdc_chk_marche_option-double",
    "bdc_chk_marche_option-galbe",
    "bdc_chk_marche_saillante",
    "bdc_chk_nez_de_marches_ferrodo",
    "bdc_chk_nez_de_marches_stries",
    "bdc_chk_nez_de_marches_stries_arrete",
    "bdc_chk_norme_bhc_exist",
    "bdc_chk_norme_bhc_neuf",
    "bdc_chk_norme_erp_exist",
    "bdc_chk_norme_erp_neuf",
    "bdc_chk_norme_nfp",
    "bdc_chk_norme_pmr",
    "bdc_chk_style_demonte",
    "bdc_chk_style_premonte",
    "bdc_chk_style_tradi",
}

CRITICAL_FIELDS = {
    "bdc_client_nom",
    "bdc_devis_num",
    "bdc_ref_affaire",
}


class BdcFiller:
    def __init__(self, logger: Optional[Callable[[str], None]] = None):
        self._logger = logger

    def fill(self, template_path: Path, data: dict, output_path: Path):
        try:
            if not template_path.exists():
                raise FileNotFoundError(template_path)
            reader = PdfReader(str(template_path))
            writer = PdfWriter()
            writer.clone_document_from_reader(reader)
            root = writer._root_object
            acro = root.get("/AcroForm")
            if isinstance(acro, IndirectObject):
                acro = acro.get_object()
            if acro is None:
                raise ValueError("AcroForm absent")
            acro.update({NameObject("/NeedAppearances"): BooleanObject(True)})
            self._log(f"Template utilisé: {template_path}")
            field_names = self._collect_field_names(reader)
            bdc_fields = {name for name in field_names if str(name).startswith("bdc_")}
            self._log(f"Champs bdc_* détectés: {len(bdc_fields)}")
            if self._logger:
                self._log(f"Liste champs bdc_*: {sorted(bdc_fields)}")

            fields = self._build_fields(data)
            checkbox_states = self._build_checkbox_states(data)

            expected_fields = TEXT_FIELDS | CHECKBOX_FIELDS
            missing_critical = [
                name for name in CRITICAL_FIELDS if name not in bdc_fields
            ]
            for name in sorted(expected_fields):
                if name not in bdc_fields:
                    self._log(f"Champ bdc_* introuvable: {name}")
            if missing_critical:
                raise ValueError(
                    "Champs critiques manquants dans le template: "
                    f"{', '.join(missing_critical)}"
                )

            values_to_set = self._build_values_to_set(
                fields, checkbox_states, bdc_fields
            )
            self._log(f"values_to_set={values_to_set}")

            text_values = {
                key: value
                for key, value in values_to_set.items()
                if isinstance(value, str)
            }
            for page in writer.pages:
                self._update_page_fields(writer, page, text_values)
                self._apply_text_values(page, text_values)

            checkbox_values = {
                key: value
                for key, value in values_to_set.items()
                if isinstance(value, bool)
            }
            for page in writer.pages:
                annots = page.get("/Annots")
                if not annots:
                    continue
                annots = annots.get_object()
                for annot in annots:
                    ao = annot.get_object()
                    field_obj, name = self._resolve_field_name(ao)
                    if name not in checkbox_values:
                        continue
                    if field_obj.get("/FT") != "/Btn" and ao.get("/FT") != "/Btn":
                        continue
                    desired = checkbox_values[name]
                    on_value = self._get_checkbox_on_value(ao) or self._get_checkbox_on_value(
                        field_obj
                    )
                    if on_value is None:
                        on_value = NameObject("/Yes")
                    self._set_checkbox_value(field_obj, ao, desired, on_value)

            output_path.parent.mkdir(parents=True, exist_ok=True)
            with open(output_path, "wb") as output_file:
                writer.write(output_file)
            self._validate_output_fields(
                output_path,
                [
                    "bdc_devis_num",
                    "bdc_devis_annee_mois",
                ],
            )
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
            "bdc_esc_finition_structure": data.get("esc_finition_structure", ""),
            "bdc_esc_finition_mains_courante": data.get(
                "esc_finition_mains_courante", ""
            ),
            "bdc_esc_finition_contremarche": data.get("esc_finition_contremarche", ""),
            "bdc_esc_finition_rampe": data.get("esc_finition_rampe", ""),
            "bdc_esc_essence": data.get("esc_essence", ""),
            "bdc_esc_main_courante": data.get("esc_main_courante", ""),
            "bdc_esc_main_courante_scellement": data.get(
                "esc_main_courante_scellement", ""
            ),
            "bdc_esc_nez_de_marches": data.get("esc_nez_de_marches", ""),
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
        clean_data = sanitize_client_address(data)
        direct_lines = strip_pollution_lines(
            (clean_data.get("client_adresse") or "").splitlines()
        )
        if direct_lines:
            return "\n".join(direct_lines)
        lines = strip_pollution_lines(
            [
                clean_data.get("client_adresse1", ""),
                clean_data.get("client_adresse2", ""),
            ]
        )
        cp = (clean_data.get("client_cp") or "").strip()
        ville = (clean_data.get("client_ville") or "").strip()
        cp_ville_line = " ".join(part for part in (cp, ville) if part).strip()
        if cp_ville_line:
            lines.append(cp_ville_line)
        return "\n".join(lines)

    def _build_values_to_set(
        self, fields: dict, checkbox_states: dict, bdc_fields: set[str]
    ) -> dict:
        values_to_set = {}
        for name, value in fields.items():
            if name in TEXT_FIELDS and name in bdc_fields:
                values_to_set[name] = value
        for name, state in checkbox_states.items():
            if name in CHECKBOX_FIELDS and name in bdc_fields:
                values_to_set[name] = state
        return values_to_set

    def _collect_field_names(self, reader: PdfReader) -> set[str]:
        names = set()
        for page in reader.pages:
            annots = page.get("/Annots")
            if not annots:
                continue
            annots = annots.get_object()
            for annot in annots:
                ao = annot.get_object()
                _, name = self._resolve_field_name(ao)
                if name:
                    names.add(name)
        return names

    def _update_page_fields(self, writer: PdfWriter, page, values: dict):
        try:
            writer.update_page_form_field_values(page, values, auto_regenerate=True)
        except TypeError:
            writer.update_page_form_field_values(page, values)

    def _apply_text_values(self, page, values: dict) -> None:
        annots = page.get("/Annots")
        if not annots:
            return
        annots = annots.get_object()
        for annot in annots:
            ao = annot.get_object()
            field_obj, name = self._resolve_field_name(ao)
            if name not in values:
                continue
            value = TextStringObject(values[name])
            field_obj.update({NameObject("/V"): value, NameObject("/DV"): value})
            ao.update({NameObject("/V"): value})
            kids = field_obj.get("/Kids", [])
            for kid in kids:
                kid_obj = kid.get_object() if hasattr(kid, "get_object") else kid
                kid_obj.update({NameObject("/V"): value})

    def _resolve_field_name(self, annotation):
        name = annotation.get("/T")
        field_obj = annotation
        if name is None and annotation.get("/Parent"):
            field_obj = annotation.get("/Parent").get_object()
            name = field_obj.get("/T")
        if isinstance(name, (NameObject, TextStringObject, str)):
            name = str(name)
        return field_obj, name

    def _get_checkbox_on_value(self, field_obj):
        ap = field_obj.get("/AP")
        if not ap:
            return None
        ap = ap.get_object() if hasattr(ap, "get_object") else ap
        normal = ap.get("/N")
        if not normal:
            return None
        normal = normal.get_object() if hasattr(normal, "get_object") else normal
        for key in normal.keys():
            if str(key) != "/Off":
                return NameObject(str(key))
        return None

    def _set_checkbox_value(self, field_obj, widget_obj, desired: bool, on_value):
        value = on_value if desired else NameObject("/Off")
        field_obj.update({NameObject("/V"): value, NameObject("/AS"): value})
        widget_obj.update({NameObject("/AS"): value})
        kids = field_obj.get("/Kids", [])
        for kid in kids:
            kid_obj = kid.get_object() if hasattr(kid, "get_object") else kid
            kid_obj.update({NameObject("/AS"): value})

    def _validate_output_fields(self, output_path: Path, field_names: list[str]):
        reader = PdfReader(str(output_path))
        values = self._extract_field_values(reader, set(field_names))
        for name in field_names:
            value = values.get(name)
            self._log(f"Validation champ {name}: {value!r}")
            if value in (None, "", TextStringObject("")):
                raise ValueError(f"Champ critique manquant dans le PDF: {name}")

    def _extract_field_values(
        self, reader: PdfReader, field_names: set[str]
    ) -> dict[str, str]:
        values = {}
        for page in reader.pages:
            annots = page.get("/Annots")
            if not annots:
                continue
            annots = annots.get_object()
            for annot in annots:
                ao = annot.get_object()
                name = ao.get("/T")
                if isinstance(name, (NameObject, TextStringObject, str)):
                    name = str(name)
                field_obj = ao
                if name is None and ao.get("/Parent"):
                    field_obj = ao.get("/Parent").get_object()
                    name = field_obj.get("/T")
                    if isinstance(name, (NameObject, TextStringObject, str)):
                        name = str(name)
                if name in field_names and name not in values:
                    value = field_obj.get("/V")
                    if isinstance(value, (NameObject, TextStringObject, str)):
                        values[name] = str(value)
                    else:
                        values[name] = value
        return values
