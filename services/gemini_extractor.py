import importlib.util
import json
import re
from dataclasses import dataclass
from typing import Callable, Optional

_genai_spec = importlib.util.find_spec("google.generativeai")
if _genai_spec:
    import google.generativeai as genai
    from google.api_core import exceptions as google_exceptions
else:
    from services import gemini_stub as genai
    from services.gemini_stub import exceptions as google_exceptions

DEFAULT_GEMINI_MODEL = "gemini-2.5-flash"


@dataclass
class GeminiResult:
    data: dict
    raw_text: str


class GeminiExtractor:
    def __init__(
        self,
        api_key: str,
        model: str = DEFAULT_GEMINI_MODEL,
        logger: Optional[Callable[[str], None]] = None,
    ):
        self.api_key = (api_key or "").strip()
        self.model_name = (model or DEFAULT_GEMINI_MODEL).strip()
        self._logger = logger
        self._model = None

    def _log(self, message: str):
        if callable(self._logger):
            self._logger(message)

    def _ensure_model(self):
        if not self.api_key:
            raise ValueError("Clé Gemini manquante.")
        if self._model is not None:
            return
        genai.configure(api_key=self.api_key)
        try:
            self._model = genai.GenerativeModel(self.model_name)
        except (google_exceptions.NotFound, ValueError) as exc:
            raise ValueError(f"Model not found / not supported: {self.model_name} (Modèle non disponible)") from exc
        self._log(f"Gemini model used: {self.model_name}")

    def _generation_config(self) -> dict:
        return {
            "temperature": 0,
            "response_mime_type": "application/json",
        }

    def _call_model(self, prompt: str) -> str:
        self._ensure_model()
        response = self._model.generate_content(
            prompt,
            generation_config=self._generation_config(),
        )
        text = getattr(response, "text", "") or ""
        if not text:
            raise ValueError("Réponse Gemini vide.")
        return text

    def _strip_json_fences(self, value: str) -> str:
        cleaned = value.strip()
        fence_match = re.search(r"```(?:json)?(.*?)```", cleaned, flags=re.DOTALL | re.IGNORECASE)
        if fence_match:
            cleaned = fence_match.group(1).strip()
        brace_match = re.search(r"\{.*\}", cleaned, flags=re.DOTALL)
        if brace_match:
            cleaned = brace_match.group(0)
        return cleaned

    def _parse_json(self, payload: str) -> dict:
        cleaned = self._strip_json_fences(payload)
        try:
            return json.loads(cleaned)
        except json.JSONDecodeError:
            repaired = self._repair_json(cleaned)
            return json.loads(repaired)

    def _repair_json(self, broken_json: str) -> str:
        prompt = (
            "The following JSON is invalid. Fix it and return ONLY valid JSON with double quotes, no markdown, "
            "no extra text:\n"
            f"{broken_json}"
        )
        repaired = self._call_model(prompt)
        cleaned = self._strip_json_fences(repaired)
        return cleaned

    def _build_prompt(self, text: str) -> str:
        return (
            "Analyse le devis suivant et renvoie uniquement un JSON strict avec les champs suivants : "
            "devis_annee_mois, devis_num, devis_type, ref_affaire, client_nom, client_contact, "
            "client_adresse1, client_adresse2, client_cp, client_ville, client_tel, client_email, "
            "commercial_nom, commercial_tel, commercial_tel2, commercial_email, fourniture_ht, "
            "prestations_ht, total_ht, pose_sold, pose_amount. "
            "Return ONLY valid JSON, double quotes, no markdown. "
            "Si une valeur est inconnue, renvoie une chaîne vide. "
            "Utilise le texte suivant :\n"
            f"{text}"
        )

    def extract_from_text(self, text: str) -> GeminiResult:
        if not text or not text.strip():
            raise ValueError("Texte devis vide pour Gemini.")
        prompt = self._build_prompt(text)
        raw = self._call_model(prompt)
        data = self._parse_json(raw)
        return GeminiResult(data=data, raw_text=raw)

    def test_model(self) -> dict:
        prompt = 'Return ONLY valid JSON, double quotes, no markdown: {"status": "ok"}'
        raw = self._call_model(prompt)
        parsed = self._parse_json(raw)
        self._log(f"Test clé Gemini OK (model={self.model_name})")
        return parsed
