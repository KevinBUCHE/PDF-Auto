import ast
import json
import logging
import re
from typing import Any, Callable, Mapping, Optional

import google.generativeai as genai


STRICT_JSON_PROMPT = (
    "Retourne UNIQUEMENT un objet JSON valide, sans markdown, sans texte.\n"
    "Output MUST be valid JSON.\n"
    "Output MUST be valid JSON.\n"
    "- Utilise des double quotes pour toutes les clés et toutes les chaînes.\n"
    "- Aucune clé non quotée.\n"
    "- Pas de trailing comma.\n"
    "- Pas de commentaire.\n"
    "- Aucun texte avant ou après l'objet JSON.\n"
)


class GeminiExtractor:
    def __init__(
        self,
        api_key: str,
        model: str = "gemini-1.5-pro",
        logger: Optional[Callable[[str], None]] = None,
    ):
        self.api_key = api_key
        self.model = model
        self._logger = logger

        genai.configure(api_key=self.api_key)
        self._model = genai.GenerativeModel(self.model)
        self._generation_config = self._build_generation_config()

    def extract(self, prompt: str, text: str) -> dict:
        response = self._model.generate_content(
            f"{STRICT_JSON_PROMPT}{prompt}\n{text}",
            generation_config=self._generation_config,
        )
        return self._parse_response(response)

    def test_key(self) -> dict:
        response = self._model.generate_content(
            f"{STRICT_JSON_PROMPT}Retourne UNIQUEMENT un objet JSON valide, sans markdown, sans texte, "
            'au format {"status": "ok"}.',
            generation_config=self._generation_config,
        )
        parsed = self._parse_response(response)
        if not isinstance(parsed, dict):
            raise ValueError("Réponse Gemini non JSON")
        return parsed

    def _parse_response(self, response: Any) -> dict:
        direct = self._extract_direct_response(response)
        if direct is not None:
            try:
                raw_length = len(json.dumps(direct, ensure_ascii=False))
            except TypeError:
                raw_length = len(str(direct))
            self._log(f"Gemini raw length={raw_length}")
            self._log("Parse mode: direct")
            return direct

        raw_text = self._extract_response_text(response)
        self._log(f"Gemini raw length={len(raw_text)}")

        cleaned = self._strip_code_fences(raw_text)
        extracted = self._extract_json_object(cleaned)
        parsed = self._try_parse_json(extracted)
        if parsed is not None:
            self._log("Parse mode: extracted")
            return parsed

        parsed = self._try_parse_python_dict(extracted)
        if parsed is not None:
            self._log("Parse mode: literal_eval")
            return parsed

        repaired = self._repair_json_via_gemini(raw_text)
        self._log("Parse mode: repaired")
        return repaired

    def _extract_direct_response(self, response: Any) -> Optional[dict]:
        if isinstance(response, Mapping):
            return dict(response)
        parsed = getattr(response, "parsed", None)
        if isinstance(parsed, Mapping):
            return dict(parsed)
        return None

    def _extract_response_text(self, response: Any) -> str:
        if isinstance(response, str):
            return response
        if isinstance(response, Mapping):
            return json.dumps(response, ensure_ascii=False)
        text_attr = getattr(response, "text", None)
        if text_attr:
            return str(text_attr)
        candidates = getattr(response, "candidates", None)
        if candidates:
            for candidate in candidates:
                content = getattr(candidate, "content", None)
                parts = getattr(content, "parts", None) if content else None
                if not parts:
                    continue
                for part in parts:
                    text_part = getattr(part, "text", None)
                    if text_part:
                        return str(text_part)
        return str(response)

    def _strip_code_fences(self, text: str) -> str:
        fence_re = re.compile(r"```(?:json)?\s*(.*?)```", re.DOTALL | re.IGNORECASE)
        match = fence_re.search(text)
        if match:
            return match.group(1).strip()
        return text.strip()

    def _extract_json_object(self, text: str) -> str:
        start = text.find("{")
        end = text.rfind("}")
        if start == -1 or end == -1 or end <= start:
            return text
        return text[start : end + 1]

    def _try_parse_json(self, text: str) -> Optional[dict]:
        try:
            parsed = json.loads(text)
        except json.JSONDecodeError:
            return None
        if not isinstance(parsed, dict):
            return None
        return parsed

    def _try_parse_python_dict(self, text: str) -> Optional[dict]:
        if "{" not in text or "}" not in text:
            return None
        try:
            parsed = ast.literal_eval(text)
        except (ValueError, SyntaxError):
            return None
        if not isinstance(parsed, dict):
            return None
        return {str(key): value for key, value in parsed.items()}

    def _repair_json_via_gemini(self, bad_text: str) -> dict:
        response = self._model.generate_content(
            f"{STRICT_JSON_PROMPT}Convertis ceci en JSON STRICT valide (double quotes, clés quotées, pas de texte):\n"
            f"{bad_text}",
            generation_config=self._generation_config,
        )
        repaired_text = self._extract_response_text(response)
        cleaned = self._strip_code_fences(repaired_text)
        extracted = self._extract_json_object(cleaned)
        parsed = self._try_parse_json(extracted)
        if parsed is not None:
            return parsed
        parsed = self._try_parse_python_dict(cleaned)
        if parsed is not None:
            return parsed
        raise ValueError("Impossible de réparer la réponse Gemini en JSON.")

    def _build_generation_config(self):
        kwargs = {"temperature": 0, "response_mime_type": "application/json"}
        genai_types = getattr(genai, "types", None)
        if genai_types:
            generator = getattr(genai_types, "GenerateContentConfig", None)
            if generator:
                return generator(**kwargs)
            alt_generator = getattr(genai_types, "GenerationConfig", None)
            if alt_generator:
                return alt_generator(**kwargs)
        fallback_generator = getattr(genai, "GenerationConfig", None)
        if fallback_generator:
            return fallback_generator(**kwargs)
        return kwargs

    def _log(self, message: str):
        if callable(self._logger):
            self._logger(message)
        else:
            logging.getLogger(__name__).info(message)
