from agent_graph.services.playbook_loader import (
    get_high_value_signals,
    get_service_questions,
    get_tts_policy,
    load_all_playbooks,
    load_playbook,
)


def test_load_playbook_reads_versioned_yaml():
    data = load_playbook("lead_segments")

    assert "segments" in data
    assert "residential_common" in data["segments"]


def test_load_all_playbooks_has_expected_files():
    data = load_all_playbooks()

    assert "services" in data
    assert "tts_speech_policy" in data


def test_service_questions_follow_segment():
    questions = get_service_questions("instalacao", "commercial_high_value")

    assert questions[:3] == ["tipo_estabelecimento", "quantidade_ambientes", "planta"]


def test_tts_policy_by_goal():
    policy = get_tts_policy("safety_warning")

    assert policy["style"] == "urgent_safety"
    assert policy["no_lists"] is True


def test_high_value_signals_include_vrf():
    signals = get_high_value_signals()

    assert signals["hard_signals"]["vrf"] == "high_value_vrf"
