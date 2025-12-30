import re

SRX_PATTERN = re.compile(r"SRX\d{4}[A-Z]{3}\d{6}", re.IGNORECASE)
POSTAL_CODE_PATTERN = re.compile(r"\b(\d{5})\b")
EMAIL_PATTERN = re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+", re.IGNORECASE)
PHONE_PATTERN = re.compile(r"0[1-9](?:[ .]?\d{2}){4,5}")
WOOD_KEYWORDS = [
    "chene",
    "hete",
    "hetre",
    "frene",
    "sapin",
    "pin",
    "erable",
    "sipo",
    "hemlock",
]
WOOD_LABELS = {
    "chene": "Chêne",
    "hetre": "Hêtre",
    "hete": "Hêtre",
    "frene": "Frêne",
    "sapin": "Sapin",
    "pin": "Pin",
    "erable": "Érable",
    "sipo": "Sipo",
    "hemlock": "Hemlock",
}
RIAUX_MARKERS = [
    "bazouges la perouse",
    "vaugarny",
    "rcs rennes",
    "groupe-riaux",
    "riaux escaliers",
    "02 99 97 45 40",
    "naf 1623z",
    "capital social",
]
CLIENT_NAME_SKIP = [
    "ref affaire",
    "réf affaire",
    "rf affaire",
    "ralis par",
    "date du devis",
    "devis n",
    "realise par",
    "réalisé par",
    "code client",
]
SECTION_TITLES = [
    "prestation",
    "prestations",
    "services",
    "eco-contribution",
    "finition",
]
