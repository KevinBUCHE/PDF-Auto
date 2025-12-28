from typing import Tuple

BANNED_CLIENT_TOKENS = ["riaux", "vaugarny", "bazouges", "35560"]


def validate_bdc_data(data: dict) -> Tuple[bool, str]:
    client_nom = (data.get("client_nom") or "").strip()
    devis_reference = (data.get("devis_annee_mois") or "").strip()
    fourniture_ht = (data.get("fourniture_ht") or "").strip()

    if not client_nom:
        return False, "Client manquant dans le devis."
    lowered = client_nom.lower()
    if any(token in lowered for token in BANNED_CLIENT_TOKENS):
        return False, f"Client invalide détecté: {client_nom}."
    if "srx" not in devis_reference.lower():
        return False, "Référence devis invalide (SRX manquant)."
    if not fourniture_ht:
        return False, "Montant fourniture HT manquant."
    return True, ""
