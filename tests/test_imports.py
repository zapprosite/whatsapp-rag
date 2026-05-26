# ============================================================
# test_imports.py — Verifica imports básicos do repo limpo
# ============================================================
import pytest


def test_refrimix_core_imports():
    """Verifica que refrimix_core carrega sem erros"""
    import refrimix_core
    from refrimix_core.domain.pipeline import pipeline
    from refrimix_core.domain.commercial_router import decide_commercial_path
    from refrimix_core.domain.response_catalog import get_response
    assert pipeline is not None
    assert decide_commercial_path is not None
    assert get_response is not None


def test_app_imports():
    """Verifica que app/ carrega sem erros"""
    from app.config.settings import settings
    from app.runtime import lifespan, get_redis
    assert settings is not None
    assert lifespan is not None
    assert get_redis is not None


def test_no_hardcoded_ips_in_settings():
    """Verifica que settings.py não tem IPs hardcoded"""
    from app.config import settings as settings_module
    import inspect
    source = inspect.getsource(settings_module.Settings)
    assert "192.168" not in source
    assert "100.66" not in source
    assert "100.87" not in source


def test_app_main_imports():
    """Verifica que app/main.py importa sem erros"""
    import app.main
    assert app.main.app is not None


def test_app_worker_has_mvp_path():
    """Verifica que worker.py tem caminho MINIMAL_MVP"""
    from app import worker
    assert hasattr(worker, "minimal_mvp_enabled")
    assert hasattr(worker, "process_mvp_message")