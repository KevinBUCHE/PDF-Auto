import json
import re
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Callable, Optional

DEFAULT_GEMINI_MODEL = "gemini-2.5-flash"
SYSTEM_INSTRUCTION = """Tu es un extracteur de données pour devis RIAUX (PDF). Objectif: produire un JSON STRICT et fiable pour remplir un “Bon de commande RIAUX”.

RÈGLES ABSOLUES
1) Tu dois retourner UNIQUEMENT un JSON valide (pas de texte autour).
2) Ne JAMAIS inclure l’adresse de RIAUX / Groupe RIAUX dans les champs client.
   - Exemples d’éléments INTERDITS côté client: “35560 BAZOUGES LA PEROUSE”, “groupe-riaux”, “RIAUX”, “BUCHE Kevin” (qui est le commercial).
3) client_* = informations du CLIENT (constructeur / donneur d’ordre) uniquement.
4) commercial_* = informations de la section “Contact commercial” (nom, email, téléphones).
   - ATTENTION: le nom du commercial est généralement sur la ligne APRÈS “Contact commercial :”
   - Ne prends JAMAIS un CP/Ville comme nom de commercial.
5) ref_affaire: valeur après “Réf affaire :” (sans rajouter “Réf affaire :” dans la valeur).
6) devis_annee_mois / devis_type / devis_num: extraire depuis SRXYYMMTTTNNNNNN (ex: SRX2511AFF037501).
7) Montants:
   - fourniture_ht = “PRIX DE LA FOURNITURE HT”
   - prestations_ht = “PRIX PRESTATIONS ET SERVICES HT” (ou somme SERVICES + ECO si présent séparément)
   - total_ht = “TOTAL HORS TAXE”
   - Les montants doivent rester au format français “1 234,56”
   - Vérifie cohérence: fourniture_ht + prestations_ht ≈ total_ht (tolérance 0,02). Si incohérent, corrige en te basant sur les libellés les plus explicites.
8) Champs techniques: extraire modèle/gamme + finitions + essence + main courante + poteaux si présents. Si absent: "".

SOURCES
- Tu reçois en entrée un PDF de devis.
- Utilise la mise en page (titres / blocs) pour distinguer CLIENT vs COMMERCIAL.
- Ignore les lignes “DEVIS N …”, “Réalisé par …”, “Validité …”, tableaux de désignation, etc. si elles polluent.

FORMAT DE SORTIE
Retourne exactement ce JSON (toutes les clés présentes, même vides):
{
  "devis_annee_mois": "",
  "devis_type": "",
  "devis_num": "",
  "ref_affaire": "",

  "client_nom": "",
  "client_contact": "",
  "client_adresse1": "",
  "client_adresse2": "",
  "client_cp": "",
  "client_ville": "",
  "client_tel": "",
  "client_email": "",

  "commercial_nom": "",
  "commercial_tel": "",
  "commercial_tel2": "",
  "commercial_email": "",

  "fourniture_ht": "",
  "prestations_ht": "",
  "total_ht": "",

  "esc_gamme": "",
  "esc_essence": "",
  "esc_main_courante": "",
  "esc_main_courante_scellement": "",
  "esc_nez_de_marches": "",

  "esc_finition_marches": "",
  "esc_finition_structure": "",
  "esc_finition_mains_courante": "",
  "esc_finition_contremarche": "",
  "esc_finition_rampe": "",

  "esc_tete_de_poteau": "",
  "esc_poteaux_depart": "",

  "pose_sold": true,
  "pose_amount": "",

  "parse_warning": ""
}

Return ONLY valid JSON, double quotes, no markdown."""


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
            "systemInstruction": {"parts": [{"text": SYSTEM_INSTRUCTION}]},
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

    def _build_prompt(self, text: str, retry_note: str | None = None) -> str:
        note = f"\nAttention: {retry_note}\n" if retry_note else ""
        return (
            "Analyse le devis suivant et renvoie uniquement le JSON demandé ci-dessus. "
            "N'invente rien, laisse vide si absent." + note + "\nTexte du devis :\n" + text
        )

    def extract_from_text(self, text: str, retry_note: str | None = None) -> GeminiResult:
        if not text or not text.strip():
            raise ValueError("Texte devis vide pour Gemini.")
        prompt = self._build_prompt(text, retry_note=retry_note)
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
