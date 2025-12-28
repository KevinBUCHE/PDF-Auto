import re
import unicodedata


INVALID_FILENAME_CHARS = r'[^A-Za-z0-9._ -]'


def sanitize_filename(value: str, default: str = "output") -> str:
    """
    Produce a filesystem-safe filename fragment.
    """
    if not value:
        return default
    normalized = unicodedata.normalize("NFKD", value)
    stripped = "".join(ch for ch in normalized if not unicodedata.combining(ch))
    cleaned = re.sub(INVALID_FILENAME_CHARS, "-", stripped).strip(" .-_")
    cleaned = re.sub(r"-{2,}", "-", cleaned)
    return cleaned or default
