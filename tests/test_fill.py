from services.bdc_filler import BdcFiller, CHECKBOX_ON


def test_build_field_values_pose_vendue():
    filler = BdcFiller()
    data = {
        "bdc_devis_annee_mois": "SRX2511AFF037501",
        "bdc_ref_affaire": "AFF-42",
        "bdc_client_nom": "Client ABC",
        "bdc_client_adresse": "12 rue Exemple\n75001 PARIS",
        "bdc_client_cp": "75001",
        "bdc_client_ville": "PARIS",
        "pose_vendue": True,
        "bdc_chk_avec_contre_marches": True,
        "bdc_structure_checkboxes": {"bdc_chk_limon": True},
    }

    values = filler.build_field_values(data)
    assert values["bdc_devis_annee_mois"] == "SRX2511AFF037501"
    assert values["bdc_ref_affaire"] == "AFF-42"
    assert values["bdc_chk_livraison_poseur"] == CHECKBOX_ON
    assert values["bdc_chk_autoliquidation"] == CHECKBOX_ON
    assert "bdc_chk_livraison_client" not in values
    assert values["bdc_chk_avec-contre-marches"] == CHECKBOX_ON
    assert values["bdc_chk_limon"] == CHECKBOX_ON
    assert "bdc_livraison_bloc" in values


def test_build_field_values_pose_non_vendue():
    filler = BdcFiller()
    data = {
        "bdc_devis_annee_mois": "SRX2511AFF037501",
        "bdc_ref_affaire": "AFF-42",
        "bdc_client_nom": "Client ABC",
        "bdc_client_adresse": "12 rue Exemple\n75001 PARIS",
        "pose_vendue": False,
    }

    values = filler.build_field_values(data)
    assert values["bdc_chk_livraison_client"] == CHECKBOX_ON
    assert "bdc_chk_livraison_poseur" not in values
    assert "bdc_chk_autoliquidation" not in values or values["bdc_chk_autoliquidation"] == CHECKBOX_ON
