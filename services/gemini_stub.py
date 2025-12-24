import json
import re
from dataclasses import dataclass


class NotFound(Exception):
    """Stub NotFound exception to mirror google.api_core.exceptions.NotFound."""


class _Exceptions:
    NotFound = NotFound


exceptions = _Exceptions()


@dataclass
class _MockResponse:
    text: str


def configure(api_key: str | None = None, **kwargs):
    return None


class GenerativeModel:
    def __init__(self, model: str):
        self.model = model

    def generate_content(self, prompt, generation_config=None):
        candidate = None
        if isinstance(prompt, str):
            match = re.search(r"\{.*\}", prompt, flags=re.DOTALL)
            if match:
                candidate_section = match.group(0)
                try:
                    json.loads(candidate_section)
                    candidate = candidate_section
                except json.JSONDecodeError:
                    candidate = candidate_section.replace("'", '"')
        if candidate is None:
            candidate = '{"status":"ok"}'
        return _MockResponse(candidate)
