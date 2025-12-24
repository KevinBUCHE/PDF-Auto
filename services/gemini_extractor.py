import json
import os
from pathlib import Path
from typing import Any, Callable, Optional

from services.extraction_normalizer import normalize_extracted_data


PROMPT_INSTRUCTIONS = """
You are extracting structured data from a French SRX staircase quote PDF.
Return ONLY valid JSON using double quotes (no markdown). If unknown, empty string.

Extraction rules:
- devis_annee_mois: string YYMM (e.g. "2512")
- devis_type: string (e.g. "AFF")
- devis_num: string of exactly 6 digits without the SRX prefix (e.g. "040301")
- fourniture_ht, prestations_ht, total_ht, pose_amount: strings formatted in French with spaces as thousands separators and a comma decimal separator, always two decimals (e.g. "2 464,71")
- pose_sold: boolean
- client_adresse can be multi-line.
""".strip()


class GeminiExtractor:
    def __init__(
        self,
        api_key: Optional[str] = None,
        model_name: str = "gemini-2.5-flash",
        logger: Optional[Callable[[str], None]] = None,
    ):
        self.api_key = api_key or os.getenv("GOOGLE_API_KEY") or os.getenv("GEMINI_API_KEY")
        self.model_name = model_name
        self._logger = logger

    def _log(self, message: str) -> None:
        if callable(self._logger):
            self._logger(message)

    def _build_prompt(self, content: str) -> str:
        return (
            f"{PROMPT_INSTRUCTIONS}\n\n"
            "Text to extract from:\n"
            f"{content}\n\n"
            "Return ONLY the JSON object."
        )

    def _parse_response(self, response_text: str) -> dict:
        cleaned = response_text.strip().strip("`")
        if cleaned.startswith("json"):
            cleaned = cleaned[4:].lstrip()
        return json.loads(cleaned)

    def extract(self, pdf_path: Path, text_content: str) -> dict:
        try:
            import google.generativeai as genai
        except ImportError as exc:  # pragma: no cover - dependency optional in tests
            raise RuntimeError(
                "Le module google-generativeai est requis pour Gemini."
            ) from exc

        if not self.api_key:
            raise RuntimeError("Clé API Gemini manquante (GOOGLE_API_KEY).")

        genai.configure(api_key=self.api_key)
        generation_config: dict[str, Any] = {"temperature": 0}
        generation_config["response_mime_type"] = "application/json"

        model = genai.GenerativeModel(
            model_name=self.model_name,
            generation_config=generation_config,
        )
        prompt = self._build_prompt(text_content)
        self._log(f"Gemini prompt prêt (fichier: {pdf_path.name})")

        response = model.generate_content(prompt)
        raw = getattr(response, "text", None) or ""
        self._log(f"Gemini brut: {raw}")
        parsed = self._parse_response(raw)
        normalized = normalize_extracted_data(parsed)
        self._log(f"Gemini normalisé: {normalized}")
        return normalized
