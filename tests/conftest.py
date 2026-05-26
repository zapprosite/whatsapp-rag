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
            "conftest",
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
        }
        for item in items:
            module_name = item.module.__name__
            if not any(sub in module_name for sub in allowed_substrings):
                item.add_marker(pytest.mark.skip(reason="Legacy tests skipped when MINIMAL_MVP_ENABLED=1"))
