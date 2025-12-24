"""
Sanitize module: prevents RIAUX company information from being injected into client fields.

This module contains patterns and logic to detect and filter out RIAUX-specific information
such as addresses, phone numbers, registration details, etc. that should never appear in
client fields of the BDC (bon de commande).
"""

import re

# RIAUX company identifiers and addresses that should NEVER appear in client fields
RIAUX_FORBIDDEN_PATTERNS = [
    # Address patterns
    r"VAUGARNY",
    r"35560",
    r"BAZOUGES[\s-]LA[\s-]PEROUSE",
    r"BAZOUGES[\s-]LA[\s-]PÉROUSE",
    # Phone patterns (RIAUX specific)
    r"02[\s\.]?99[\s\.]?98[\s\.]?04[\s\.]?50",
    # Company registration
    r"RCS[\s:].*RENNES",
    r"SIRET[\s:]*\d+",
    r"NAF[\s:]*\d+",
    r"TVA[\s:]*FR\d+",
    # Company name patterns
    r"GROUPE[\s-]?RIAUX",
    r"RIAUX[\s-]?SAS",
    r"S\.?A\.?S\.?\s+RIAUX",
]

# Common terms that could be RIAUX-related context (case insensitive)
RIAUX_CONTEXT_KEYWORDS = [
    "riaux",
    "fournisseur",
    "fabricant",
    "vendeur",
]


def is_riaux_contaminated(text: str) -> bool:
    """
    Check if text contains RIAUX-specific information that should not appear in client fields.
    
    Args:
        text: Text to check for RIAUX contamination
        
    Returns:
        True if text contains forbidden RIAUX patterns, False otherwise
    """
    if not text or not isinstance(text, str):
        return False
    
    text_upper = text.upper()
    
    # Check forbidden patterns
    for pattern in RIAUX_FORBIDDEN_PATTERNS:
        if re.search(pattern, text_upper):
            return True
    
    return False


def sanitize_client_field(value: str, field_name: str = "") -> str:
    """
    Sanitize a client field value to ensure it doesn't contain RIAUX information.
    
    Args:
        value: The value to sanitize
        field_name: Optional field name for logging/debugging
        
    Returns:
        Empty string if contaminated, original value otherwise
    """
    if not value or not isinstance(value, str):
        return value or ""
    
    if is_riaux_contaminated(value):
        # Return empty string if contaminated - safer than trying to clean
        return ""
    
    return value


def sanitize_client_data(data: dict) -> dict:
    """
    Sanitize all client-related fields in parsed data to prevent RIAUX contamination.
    
    Args:
        data: Dictionary containing parsed devis data
        
    Returns:
        Dictionary with sanitized client fields
    """
    # Fields that must never contain RIAUX information
    client_fields = [
        "client_nom",
        "client_contact",
        "client_adresse1",
        "client_adresse2",
        "client_cp",
        "client_ville",
        "client_tel",
        "client_email",
    ]
    
    sanitized = data.copy()
    
    for field in client_fields:
        if field in sanitized:
            original = sanitized[field]
            sanitized[field] = sanitize_client_field(original, field)
            # Log if sanitization occurred
            if original and not sanitized[field]:
                # Field was cleared due to contamination
                pass
    
    return sanitized


def validate_client_extraction(data: dict) -> list[str]:
    """
    Validate that client data extraction doesn't contain RIAUX information.
    
    Args:
        data: Dictionary containing parsed devis data
        
    Returns:
        List of validation warnings/errors
    """
    warnings = []
    
    client_fields = {
        "client_nom": "Nom client",
        "client_adresse1": "Adresse client ligne 1",
        "client_adresse2": "Adresse client ligne 2",
        "client_cp": "Code postal client",
        "client_ville": "Ville client",
        "client_tel": "Téléphone client",
        "client_email": "Email client",
    }
    
    for field, label in client_fields.items():
        value = data.get(field, "")
        if value and is_riaux_contaminated(value):
            warnings.append(
                f"{label}: contient des informations RIAUX interdites: {value!r}"
            )
    
    return warnings
