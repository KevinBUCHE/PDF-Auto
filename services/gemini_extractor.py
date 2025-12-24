import json
import re
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Callable, Optional

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

    def _build_request(self, prompt: str) -> dict:
        return {
            "contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": {
                "temperature": 0,
                "responseMimeType": "application/json",
            },
        }

    def _call_model(self, prompt: str) -> str:
        if not self.api_key:
            raise ValueError("Clé Gemini manquante.")
        body = json.dumps(self._build_request(prompt)).encode("utf-8")
        url = (
            f"https://generativelanguage.googleapis.com/v1beta/models/{self.model_name}:generateContent"
            f"?key={self.api_key}"
        )
        request = urllib.request.Request(
            url,
            data=body,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            self._log(f"Gemini model used: {self.model_name} (payload chars={len(prompt)})")
            with urllib.request.urlopen(request) as response:
                payload = response.read().decode("utf-8")
        except urllib.error.HTTPError as exc:  # pragma: no cover
            error_detail = exc.read().decode("utf-8") if hasattr(exc, "read") else str(exc)
            raise ValueError(f"Appel Gemini KO: {exc.reason}: {error_detail}") from exc
        except urllib.error.URLError as exc:  # pragma: no cover
            raise ValueError(f"Appel Gemini KO: {exc.reason}") from exc

        try:
            data = json.loads(payload)
        except json.JSONDecodeError as exc:
            raise ValueError(f"Réponse Gemini illisible: {exc}") from exc
        candidates = (data.get("candidates") or [])
        if not candidates:
            raise ValueError("Réponse Gemini vide.")
        parts = candidates[0].get("content", {}).get("parts") or []
        text_chunks = []
        for part in parts:
            if "text" in part:
                text_chunks.append(part["text"])
        text = "\n".join(text_chunks).strip()
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
            repaired = self._extract_first_json_object(cleaned)
            if not repaired:
                repaired = self._repair_json(cleaned)
            return json.loads(repaired)

    def _extract_first_json_object(self, text: str) -> str:
        brace_stack = []
        start_idx = None
        for idx, char in enumerate(text):
            if char == "{":
                if start_idx is None:
                    start_idx = idx
                brace_stack.append(char)
            elif char == "}":
                if brace_stack:
                    brace_stack.pop()
                    if not brace_stack and start_idx is not None:
                        return text[start_idx : idx + 1]
        return ""

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
            "Analyse le devis suivant et renvoie UNIQUEMENT un JSON strict (pas de markdown) avec les règles précises :\n"
            "- devis_annee_mois : chaîne YYMM (ex: \"2512\"), pas de préfixe \"SRX\", pas d'année sur 4 chiffres.\n"
            "- devis_type : chaîne (ex: \"AFF\").\n"
            "- devis_num : chaîne de 6 chiffres uniquement (ex: \"040301\"), jamais le préfixe \"SRX\".\n"
            "- ref_affaire, client_nom, client_contact, client_adresse1, client_adresse2, client_cp, client_ville, client_tel, client_email,\n"
            "  commercial_nom, commercial_tel, commercial_tel2, commercial_email : chaînes.\n"
            "- fourniture_ht, prestations_ht, total_ht, pose_amount : chaînes au format français avec espaces milliers et virgule décimale sur 2 décimales (ex: \"2 464,71\").\n"
            "- pose_sold : booléen true/false.\n"
            "- Si une valeur est inconnue, renvoyer une chaîne vide.\n"
            "Return ONLY valid JSON, double quotes, no markdown.\n"
            "Texte du devis :\n"
            f"{text}\n"
        )

    def extract_from_text(self, text: str) -> GeminiResult:
        if not text or not text.strip():
            raise ValueError("Texte devis vide pour Gemini.")
        prompt = self._build_prompt(text)
        raw = self._call_model(prompt)
        data = self._parse_json(raw)
        self._log("Gemini JSON OK")
        return GeminiResult(data=data, raw_text=raw)

    def test_model(self) -> dict:
        prompt = 'Return ONLY valid JSON, double quotes, no markdown: {"status": "ok"}'
        raw = self._call_model(prompt)
        parsed = self._parse_json(raw)
        self._log(f"Test clé Gemini OK (model={self.model_name})")
        return parsed
