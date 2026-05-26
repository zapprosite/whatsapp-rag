from __future__ import annotations

import pytest

from agent_graph.nodes.nodes import (
    compute_fields_status,
    has_minimum_real_data_for_appointment,
    _important_missing_field_for_service,
    _human_service_label,
)


def _lead(extra: dict | None = None) -> dict:
    base = {
        "tipo_servico": "instalacao",
        "cidade_bairro": "Guarujá",
        "btus": None,
        "modelo_aparelho": None,
        "aparelho_ja_comprado": None,
        "fotos": {},
        "instalacao": {},
        "manutencao": {},
        "conserto": {},
        "eletrica": {},
        "appointment": {"preferred_window": None, "confirmed_window": False, "appointment_alert_sent": False},
        "appointment_ready": False,
    }
    if extra:
        for k, v in extra.items():
            if isinstance(v, dict) and isinstance(base.get(k), dict):
                base[k].update(v)
            else:
                base[k] = v
    return base


class TestComputeFieldsStatusFotos:
    def test_local_interno_adds_to_filled(self):
        lead = _lead({"fotos": {"local_interno": True}})
        do_not_ask, _, missing = compute_fields_status(lead)
        assert "foto_local_interno" in do_not_ask
        assert "foto_local_interno" not in missing

    def test_local_externo_in_missing_when_not_set(self):
        lead = _lead({"fotos": {"local_interno": True}})
        _, _, missing = compute_fields_status(lead)
        assert "foto_local_externo" in missing

    def test_both_fotos_clears_both_from_missing(self):
        lead = _lead({"fotos": {"local_interno": True, "local_externo": True}})
        do_not_ask, _, missing = compute_fields_status(lead)
        assert "foto_local_interno" not in missing
        assert "foto_local_externo" not in missing
        assert "foto_local_interno" in do_not_ask
        assert "foto_local_externo" in do_not_ask


class TestHasMinimumRealDataInstalacao:
    def test_only_internal_photo_not_enough(self):
        lead = _lead({"fotos": {"local_interno": True}})
        assert has_minimum_real_data_for_appointment(lead, "instalacao") is False

    def test_only_external_photo_not_enough(self):
        lead = _lead({"fotos": {"local_externo": True}})
        assert has_minimum_real_data_for_appointment(lead, "instalacao") is False

    def test_both_photos_but_no_equipment_not_enough(self):
        lead = _lead({"fotos": {"local_interno": True, "local_externo": True}})
        assert has_minimum_real_data_for_appointment(lead, "instalacao") is False

    def test_both_photos_plus_btus_ok(self):
        lead = _lead({"fotos": {"local_interno": True, "local_externo": True}, "btus": "12000"})
        assert has_minimum_real_data_for_appointment(lead, "instalacao") is True

    def test_both_photos_plus_aparelho_comprado_ok(self):
        lead = _lead({
            "fotos": {"local_interno": True, "local_externo": True},
            "aparelho_ja_comprado": True,
        })
        assert has_minimum_real_data_for_appointment(lead, "instalacao") is True

    def test_no_city_not_enough(self):
        lead = _lead({
            "cidade_bairro": None,
            "fotos": {"local_interno": True, "local_externo": True},
            "btus": "12000",
        })
        assert has_minimum_real_data_for_appointment(lead, "instalacao") is False

    def test_appointment_ready_resets_when_missing_external(self):
        """appointment_ready não deve ser True se local_externo está faltando."""
        lead = _lead({"fotos": {"local_interno": True}, "btus": "12000"})
        assert has_minimum_real_data_for_appointment(lead, "instalacao") is False


class TestImportantMissingFieldForService:
    def test_internal_before_external_in_priority(self):
        missing = ["foto_local_interno", "foto_local_externo", "btus"]
        result = _important_missing_field_for_service("instalacao", missing, [], {})
        assert result == "foto_local_interno"

    def test_after_interno_asks_externo(self):
        missing = ["foto_local_externo", "btus"]
        do_not_ask = ["foto_local_interno", "cidade_bairro"]
        result = _important_missing_field_for_service("instalacao", missing, do_not_ask, {})
        assert result == "foto_local_externo"

    def test_cidade_first_even_for_instalacao(self):
        missing = ["cidade_bairro", "foto_local_interno"]
        result = _important_missing_field_for_service("instalacao", missing, [], {})
        assert result == "cidade_bairro"


class TestHumanServiceLabel:
    def test_instalacao_without_accent(self):
        assert _human_service_label("instalacao") == "instalação"

    def test_manutencao_without_accent(self):
        assert _human_service_label("manutencao") == "manutenção"

    def test_higienizacao_without_accent(self):
        assert _human_service_label("higienizacao") == "higienização"

    def test_unknown_passthrough(self):
        assert _human_service_label("xyz") == "xyz"

    def test_none_returns_atendimento(self):
        assert _human_service_label(None) == "atendimento"
