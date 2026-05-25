from agent_graph.domain.lead_mind import classify_segment, default_lead_mind


def test_residential_common_installation_quarto_split_12000():
    mind = default_lead_mind()

    segment = classify_segment(mind, "Quero instalar um split 12000 no quarto. Quanto custa?")

    assert segment["id"] == "residential_common"
    assert segment["market"] == "residential"


def test_residential_high_end_cobertura_obra_forro_gesso():
    mind = default_lead_mind()

    segment = classify_segment(mind, "É uma cobertura em obra com arquiteto e forro de gesso.")

    assert segment["id"] == "residential_high_end"
    assert segment["tier"] == "high_end"


def test_commercial_common_loja_com_2_splits():
    mind = default_lead_mind()

    segment = classify_segment(mind, "Tenho uma loja com 2 aparelhos split para manutenção preventiva.")

    assert segment["id"] == "commercial_common"
    assert segment["market"] == "commercial"


def test_commercial_high_value_vrf_restaurante():
    mind = default_lead_mind()

    segment = classify_segment(mind, "Preciso avaliar VRF para restaurante com vários ambientes.")

    assert segment["id"] == "commercial_high_value"
    assert segment["tier"] == "high_value"
    assert segment["do_not_say_to_customer"] is True
