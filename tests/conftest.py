import os
import pytest

# Carrega .env manualmente para garantir feature flags ativas na coleta do pytest
env_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), ".env")
if os.path.exists(env_path):
    with open(env_path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                key, val = line.split("=", 1)
                os.environ.setdefault(key.strip(), val.strip())

def pytest_ignore_collect(path, config):
    if str(os.getenv("MINIMAL_MVP_ENABLED", "0")).strip() == "1":
        allowed_substrings = {
            "test_minimal_mvp_core",
            "test_mvp_attendance",
            "test_response_catalog_mvp",
            "test_validate_env",
            "test_hvacr_loop_scenarios",
            "test_short_answer_fields",
            "test_audio_stt_quantity",
            "test_brazilian_variations",
            "test_high_value_routing",
            "test_response_loop_detection",
            "conftest",
            # Phase 2.7 — monitoring integration tests
            "test_runtime_shadow_mode",
            "test_evolution_status_webhook",
            "test_monitoring_integration",
            # Phase 2.8 — assisted inbox / review tests
            "test_review_models_mvp",
            "test_review_queue_mvp",
            "test_review_policy_mvp",
            "test_review_actions_mvp",
            "test_review_api_mvp",
            # Phase 2.9 — assisted pilot report
            "test_assisted_pilot_report",
            # Phase 2.10 — V2 PT-BR negative abbreviation handling
            "test_understand_message_ptbr_variants",
        }
        name = os.path.basename(str(path))
        # If it's a test file and not in our allowed MVP list, ignore it during collection
        if name.startswith("test_") and not any(sub in name for sub in allowed_substrings):
            return True
    return False

def pytest_collection_modifyitems(config, items):
    if str(os.getenv("MINIMAL_MVP_ENABLED", "0")).strip() == "1":
        allowed_substrings = {
            "test_minimal_mvp_core",
            "test_mvp_attendance",
            "test_response_catalog_mvp",
            "test_validate_env",
            "test_hvacr_loop_scenarios",
            "test_short_answer_fields",
            "test_audio_stt_quantity",
            "test_brazilian_variations",
            "test_high_value_routing",
            "test_response_loop_detection",
            # Phase 2.7 — monitoring integration tests
            "test_runtime_shadow_mode",
            "test_evolution_status_webhook",
            "test_monitoring_integration",
            # Phase 2.8 — assisted inbox / review tests
            "test_review_models_mvp",
            "test_review_queue_mvp",
            "test_review_policy_mvp",
            "test_review_actions_mvp",
            "test_review_api_mvp",
            # Phase 2.9 — assisted pilot report
            "test_assisted_pilot_report",
            # Phase 2.10 — V2 PT-BR negative abbreviation handling
            "test_understand_message_ptbr_variants",
        }
        for item in items:
            module_name = item.module.__name__
            if not any(sub in module_name for sub in allowed_substrings):
                item.add_marker(pytest.mark.skip(reason="Legacy tests skipped when MINIMAL_MVP_ENABLED=1"))
