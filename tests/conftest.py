import os
import pytest

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
