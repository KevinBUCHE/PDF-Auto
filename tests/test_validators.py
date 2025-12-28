from services.validators import validate_bdc_data


def test_validator_rejects_banned_client():
    valid, message = validate_bdc_data(
        {"client_nom": "RIAUX Construction", "devis_annee_mois": "SRX123", "fourniture_ht": "10"}
    )
    assert not valid
    assert "Client invalide" in message


def test_validator_requires_srx_reference():
    valid, message = validate_bdc_data(
        {"client_nom": "Client", "devis_annee_mois": "ABC123", "fourniture_ht": "10"}
    )
    assert not valid
    assert "SRX" in message


def test_validator_passes_for_valid_data():
    valid, message = validate_bdc_data(
        {"client_nom": "Client", "devis_annee_mois": "SRX2401", "fourniture_ht": "10"}
    )
    assert valid
    assert message == ""
