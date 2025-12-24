import io
import json
import logging
from pathlib import Path
from typing import Optional, TYPE_CHECKING

import pdfplumber

try:
    import fitz  # PyMuPDF
except ImportError:  # pragma: no cover - runtime guard
    fitz = None

try:
    from google import genai
    from google.genai import types
except ImportError:  # pragma: no cover - runtime guard
    genai = None
    types = None

if TYPE_CHECKING:  # pragma: no cover
    from google.genai import types as genai_types

from services.extraction_validator import validate_and_normalize

MIN_TEXT_LENGTH = 800
MAX_VISION_PAGES = 3


def _read_text_lines(pdf_path: Path) -> tuple[str, list[str]]:
    text_parts = []
    lines = []
    with pdfplumber.open(pdf_path) as pdf:
        for page in pdf.pages:
            page_text = page.extract_text() or ""
            if page_text:
                text_parts.append(page_text)
                for line in page_text.splitlines():
                    cleaned = " ".join(line.replace("\u202f", " ").split()).strip()
                    if cleaned:
                        lines.append(cleaned)
    return "\n".join(text_parts), lines


def _render_images(pdf_path: Path, max_pages: int = MAX_VISION_PAGES):
    images = []
    if not fitz:
        raise RuntimeError("PyMuPDF manquant: pip install PyMuPDF")
    with fitz.open(pdf_path) as doc:
        for page_index, page in enumerate(doc):
            if page_index >= max_pages:
                break
            pix = page.get_pixmap(dpi=200)
            buffer = io.BytesIO()
            buffer.write(pix.tobytes("png"))
            images.append(types.Part.from_bytes(buffer.getvalue(), mime_type="image/png"))
    return images


def _build_prompt() -> str:
    return (
        "Lis attentivement le devis SRX et renvoie UNIQUEMENT le JSON strict suivant, "
        "sans texte additionnel, sans Markdown, sans commentaires. "
        "Respecte exactement les clés et les types. "
        "N'inclus jamais d'autres clés.\n\n"
        "Schéma JSON attendu:\n"
        "{\n"
        '  "devis_annee_mois": "",\n'
        '  "devis_type": "",\n'
        '  "devis_num": "",\n'
        '  "ref_affaire": "",\n'
        '  "client_nom": "",\n'
        '  "client_contact": "",\n'
        '  "client_adresse1": "",\n'
        '  "client_adresse2": "",\n'
        '  "client_cp": "",\n'
        '  "client_ville": "",\n'
        '  "client_tel": "",\n'
        '  "client_email": "",\n'
        '  "commercial_nom": "",\n'
        '  "commercial_tel": "",\n'
        '  "commercial_tel2": "",\n'
        '  "commercial_email": "",\n'
        '  "fourniture_ht": "",\n'
        '  "prestations_ht": "",\n'
        '  "total_ht": "",\n'
        '  "esc_gamme": "",\n'
        '  "esc_essence": "",\n'
        '  "esc_main_courante": "",\n'
        '  "esc_main_courante_scellement": "",\n'
        '  "esc_nez_de_marches": "",\n'
        '  "esc_finition_marches": "",\n'
        '  "esc_finition_structure": "",\n'
        '  "esc_finition_mains_courante": "",\n'
        '  "esc_finition_contremarche": "",\n'
        '  "esc_finition_rampe": "",\n'
        '  "esc_tete_de_poteau": "",\n'
        '  "esc_poteaux_depart": "",\n'
        '  "pose_sold": false,\n'
        '  "pose_amount": "",\n'
        '  "parse_warning": ""\n'
        "}\n\n"
        "Règles obligatoires:\n"
        "- Ne jamais mettre d'informations RIAUX (VAUGARNY, 35560 BAZOUGES LA PEROUSE, RCS RENNES, NAF 1623Z, etc.) dans client_nom/adresse/cp/ville.\n"
        "- client_email et commercial_email doivent être des emails valides sinon vide.\n"
        "- pose_sold est booléen strict. pose_amount contient le montant de la pose si vendue, sinon vide.\n"
        "- Conserve le format français des montants (ex: 1 234,56).\n"
        "- Ne renvoie QUE le JSON valide (pas de ``` ni de texte hors JSON).\n"
        "- Évite les erreurs typiques: client_nom ne doit pas contenir 'DEVIS', 'Réalisé par', 'Date du devis', ni de CP/Ville.\n"
    )


class GeminiExtractor:
    def __init__(self, logger: Optional[callable] = None, debug: bool = False):
        self._logger = logger
        self.debug = debug

    def _log(self, message: str):
        if callable(self._logger):
            self._logger(message)
        else:
            logging.getLogger(__name__).info(message)

    def extract_srx_json(self, pdf_path: Path, api_key: Optional[str] = None) -> dict:
        if not pdf_path.exists():
            raise FileNotFoundError(pdf_path)
        if not genai or not types:
            raise RuntimeError("google-genai manquant: pip install google-genai")
        key = api_key or self._resolve_env_key()
        if not key:
            raise RuntimeError("Clé Gemini absente (UI ou variable d'environnement).")

        text, lines = _read_text_lines(pdf_path)
        prompt = _build_prompt()

        client = genai.Client(api_key=key)
        contents: list = [prompt]
        response = None
        try:
            if len(text) >= MIN_TEXT_LENGTH:
                contents.append(text)
                response = client.models.generate_content(
                    model="gemini-2.5-flash",
                    contents=contents,
                    config=types.GenerateContentConfig(
                        temperature=0.2,
                        max_output_tokens=2048,
                        response_mime_type="application/json",
                    ),
                )
            else:
                raise ValueError("Texte insuffisant, passage en vision")
        except Exception as exc:  # pylint: disable=broad-except
            self._log(f"Gemini texte KO ({exc}), tentative vision...")
            images = _render_images(pdf_path)
            vision_contents: list = [prompt] + images
            response = client.models.generate_content(
                model="gemini-2.5-flash",
                contents=vision_contents,
                config=types.GenerateContentConfig(
                    temperature=0.15,
                    max_output_tokens=2048,
                    response_mime_type="application/json",
                ),
            )

        parsed = self._parse_response(response)
        validated = validate_and_normalize(parsed, lines)
        if self.debug:
            self._log(f"[Gemini] brut: {json.dumps(parsed, ensure_ascii=False)}")
            self._log(f"[Gemini] validé: {json.dumps(validated, ensure_ascii=False)}")
        return validated

    def test_key(self, api_key: Optional[str]) -> bool:
        key = api_key or self._resolve_env_key()
        if not key:
            raise RuntimeError("Aucune clé Gemini fournie.")
        client = genai.Client(api_key=key)
        prompt = "Réponds uniquement par le texte OK"
        response = client.models.generate_content(
            model="gemini-2.5-flash",
            contents=[prompt],
            config=types.GenerateContentConfig(
                temperature=0.0,
                max_output_tokens=4,
            ),
        )
        return (response.text or "").strip().upper().startswith("OK")

    def _parse_response(self, response) -> dict:
        if not response:
            raise ValueError("Réponse vide de Gemini.")
        text = (response.text or "").strip()
        if not text:
            raise ValueError("Réponse Gemini vide.")
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            start = text.find("{")
            end = text.rfind("}")
            if start >= 0 and end > start:
                snippet = text[start : end + 1]
                return json.loads(snippet)
            raise

    def _resolve_env_key(self) -> str:
        from os import getenv

        return getenv("GEMINI_API_KEY") or getenv("GOOGLE_API_KEY") or ""
