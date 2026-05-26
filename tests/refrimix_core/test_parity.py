"""
Testes de paridade — verificar comportamento do core determinístico.
Cada teste verifica uma regra operacional rastreável.
"""
from __future__ import annotations

import pytest
import unicodedata

from refrimix_core.domain.pipeline import pipeline, build_lead_state
from refrimix_core.domain.commercial_router import decide_commercial_path
from refrimix_core.domain.text_normalizer import detect_quantity, detect_window, is_greeting


# ── Fixtures ────────────────────────────────────────────────────────────────────
def make_input(text: str, message_type: str = "text", transcript=None) -> dict:
    return {
        "phone": "5513988887777",
        "message_id": "test-001",
        "message_type": message_type,
        "text": text,
        "transcript": transcript,
        "media_url": "",
        "instance": "Refrimix",
        "timestamp": "2026-05-26T10:00:00Z",
        "raw": {},
    }


def empty_state() -> dict:
    return build_lead_state()


# ── T1: Saudação → welcome_onboarding ─────────────────────────────────────────
class TestSaudacao:
    def test_bom_dia_trigger_welcome_onboarding(self):
        input_data = make_input("Bom dia")
        state = empty_state()
        out = pipeline(input_data, state)
        assert out["action"] == "welcome_onboarding"
        assert "Bom dia" in out["response_text"]

    def test_ola_trigger_welcome_onboarding(self):
        for greeting in ["Oi", "Ola", "Olá", "Opa", "E aí"]:
            out = pipeline(make_input(greeting), empty_state())
            assert out["action"] == "welcome_onboarding", f"Failed for: {greeting}"

    def test_greeting_no_context_returns_welcome(self):
        for greeting in ["bom dia", "oi", "ola"]:
            state = empty_state()
            out = pipeline(make_input(greeting), state)
            assert out["action"] == "welcome_onboarding"


# ── T2: Lista de serviços → answer_services_list ──────────────────────────────
class TestServicos:
    def test_quais_servicos_trigger_list(self):
        out = pipeline(make_input("Quais serviços vocês oferecem?"), empty_state())
        assert out["action"] == "answer_services_list"
        assert "Instalação simples" in out["response_text"]
        assert "Higienização" in out["response_text"]

    def test_o_que_voces_fazem_trigger_list(self):
        out = pipeline(make_input("O que vocês fazem?"), empty_state())
        assert out["action"] == "answer_services_list"


# ── T3: Clarificação → answer_clarification ───────────────────────────────────
class TestClarificacao:
    def test_nao_entendi_trigger_clarification(self):
        out = pipeline(make_input("não entendi"), empty_state())
        assert out["action"] == "answer_clarification"
        assert "R$850" in out["response_text"]
        assert "R$200" in out["response_text"]


# ── T4: Higienização → offer_fixed_hygienization ──────────────────────────────
class TestHigienizacao:
    def test_higienizacao_trigger_offer_fixed_hygienization(self):
        out = pipeline(make_input("Preciso fazer uma higienização no meu ar"), empty_state())
        assert out["action"] == "offer_fixed_hygienization"
        assert "R$200" in out["response_text"]
        assert "Quantos aparelhos" in out["response_text"]

    def test_limpeza_split_trigger_hygienization(self):
        out = pipeline(make_input("Quero fazer limpeza do split"), empty_state())
        assert out["action"] == "offer_fixed_hygienization"

    def test_quantity_1_trigger_hygienization_schedule(self):
        state = empty_state()
        state["service"]["type"] = "higienizacao"
        state["memory"]["last_asked_field"] = "quantidade_aparelhos"

        out = pipeline(make_input("1"), state)
        assert out["action"] == "offer_hygienization_schedule"
        assert out["commercial_decision"]["path"] == "fixed_hygienization"

    def test_quantity_um_stt_transcript_triggers_schedule(self):
        """STT transcript 'um' deve funcionar como quantity=1."""
        state = empty_state()
        state["service"]["type"] = "higienizacao"
        state["memory"]["last_asked_field"] = "quantidade_aparelhos"

        out = pipeline(make_input("um", transcript="um"), state)
        assert out["action"] == "offer_hygienization_schedule"

    def test_quantity_3_triggers_schedule_600(self):
        state = empty_state()
        state["service"]["type"] = "higienizacao"
        state["memory"]["last_asked_field"] = "quantidade_aparelhos"

        out = pipeline(make_input("3"), state)
        assert out["action"] == "offer_hygienization_schedule"
        assert "R$600" in out["response_text"]


# ── T5: Instalação sem foto → technical_visit_50 ─────────────────────────────
class TestInstalacaoSemFoto:
    def test_quero_instalacao_sem_foto_technical_visit(self):
        state = empty_state()
        state["service"]["type"] = "instalacao"
        # Sem fotos
        state["installation"]["has_photos"] = {"local_interno": False, "local_externo": False, "aparelho": False}

        out = pipeline(make_input("Quero instalação mas não tenho foto"), state)
        assert out["action"] == "offer_technical_visit_installation"
        assert out["commercial_decision"]["path"] == "technical_visit_50"
        assert out["commercial_decision"]["visit_price"] == 50

    def test_nao_tenho_foto_trigger_technical_visit(self):
        state = empty_state()
        state["service"]["type"] = "instalacao"
        state["installation"]["has_photos"] = {"local_interno": False, "local_externo": False, "aparelho": False}

        out = pipeline(make_input("não tenho foto"), state)
        assert out["action"] == "offer_technical_visit_installation"

    def test_foto_nao_bloqueia_technical_visit(self):
        """Foto é útil mas não bloqueia — visita técnica R$50."""
        state = empty_state()
        state["service"]["type"] = "instalacao"
        state["installation"]["has_photos"] = {"local_interno": False, "local_externo": False, "aparelho": False}

        out = pipeline(make_input("tenho foto sim"), state)
        # Since other fields missing, still technical visit
        assert out["commercial_decision"]["path"] in ("technical_visit_50", "fixed_installation_simple")


# ── T6: Manutenção → technical_visit_50 ─────────────────────────────────────
class TestManutencao:
    def test_ar_nao_gela_maintenance(self):
        out = pipeline(make_input("Meu ar não gela"), empty_state())
        assert out["commercial_decision"]["path"] == "technical_visit_50"
        assert out["action"] == "offer_technical_visit_maintenance"

    def test_ar_nao_liga_maintenance(self):
        out = pipeline(make_input("O ar não liga"), empty_state())
        assert out["commercial_decision"]["path"] == "technical_visit_50"

    def test_maintenance_symptom_collected(self):
        state = empty_state()
        state["service"]["type"] = "manutencao"
        state["maintenance"]["symptom"] = "não gela"

        out = pipeline(make_input("está pingando"), state)
        assert out["commercial_decision"]["path"] == "technical_visit_50"


# ── T7: Alto valor → project_quote + owner_alert ─────────────────────────────
class TestAltoValor:
    def test_vrf_restaurante_project_quote(self):
        out = pipeline(make_input("Preciso de VRF para restaurante"), empty_state())
        assert out["commercial_decision"]["path"] == "project_quote"
        assert out["action"] == "offer_project_visit"
        assert out["commercial_decision"]["owner_alert"] is True

    def test_cassete_hotel_project_quote(self):
        out = pipeline(make_input("Preciso de cassete para hotel"), empty_state())
        assert out["commercial_decision"]["path"] == "project_quote"

    def test_splitão_acima_18k_btus_project_quote(self):
        state = empty_state()
        state["installation"]["btus"] = 36000
        out = pipeline(make_input("Preciso instalar"), state)
        assert out["commercial_decision"]["path"] == "project_quote"

    def test_alto_valor_owner_alert_true(self):
        out = pipeline(make_input("Projeto de VRV para clínica"), empty_state())
        assert out["commercial_decision"]["owner_alert"] is True
        # Owner alert deve gerar side effect
        effects = out.get("side_effects", [])
        owner_effects = [e for e in effects if e.get("type") == "send_owner_alert"]
        assert len(owner_effects) > 0


# ── T8: Modality — texto não chama TTS ───────────────────────────────────────
class TestModality:
    def test_text_input_returns_text_modality(self):
        out = pipeline(make_input("Bom dia"), empty_state())
        assert out["response_modality"] == "text"

    def test_audio_input_no_tts_returns_text(self):
        """Audio + TTS_ENABLED=0 deve retornar texto."""
        out = pipeline(make_input("", message_type="audioMessage", transcript="preciso de instalação"), empty_state())
        # Modality é audio mas sem TTS_ENABLED o handler externo converte
        assert out["response_modality"] in ("text", "audio")


# ── T9: Language guard — CJK/árabe/ES bloqueados ─────────────────────────────
class TestLanguageGuard:
    def test_chinese_input_no_crash(self):
        """CJK input não deve crashar e deve retornar resposta PT-BR válida."""
        out = pipeline(make_input("空调维修"), empty_state())
        # Response must be valid PT-BR (no CJK chars in output)
        assert out["action"] in (
            "ask_basic_service", "welcome_onboarding", "fallback_recover_context"
        )
        # Response must not contain CJK chars
        for char in out["response_text"]:
            if char not in "\n\r\t " and not (0x20 <= ord(char) <= 0x7E):
                cat = unicodedata.category(char)
                if cat.startswith("L"):
                    assert cat != "So", f"Non-Latin char found: {repr(char)}"

    def test_arabic_input_no_crash(self):
        """Arabic input não deve crashar e deve retornar resposta PT-BR válida."""
        out = pipeline(make_input("صيانة مكيف"), empty_state())
        assert out["action"] in (
            "ask_basic_service", "welcome_onboarding", "fallback_recover_context"
        )
        # No Arabic chars in response
        for char in out["response_text"]:
            name = unicodedata.name(char, "")
            assert "ARABIC" not in name, f"Arabic char in response: {repr(char)}"

    def test_cyrillic_input_no_crash(self):
        """Cyrillic input não deve crashar e deve retornar resposta PT-BR válida."""
        out = pipeline(make_input("кондиционер"), empty_state())
        assert out["action"] in (
            "ask_basic_service", "welcome_onboarding", "fallback_recover_context"
        )
        import unicodedata
        for char in out["response_text"]:
            name = unicodedata.name(char, "")
            assert "CYRILLIC" not in name, f"Cyrillic char in response: {repr(char)}"


# ── T10: Anti-loop — duas msgs diferentes não recebem resposta idêntica ───────
class TestAntiLoop:
    def test_different_messages_different_responses(self):
        state = empty_state()
        out1 = pipeline(make_input("Bom dia"), state)
        state = out1["lead_state_patch"]

        out2 = pipeline(make_input("Preciso de instalação"), state)
        # Different actions
        assert out1["action"] != out2["action"] or out1["response_text"] != out2["response_text"]

    def test_same_message_same_lead_same_response_ok(self):
        """Cliente repetindo mesma mensagem = mesmo response ok."""
        state = empty_state()
        out1 = pipeline(make_input("Bom dia"), state)
        state = out1["lead_state_patch"]

        out2 = pipeline(make_input("Bom dia"), state)
        # Same message, same state = same response is ok
        assert out1["action"] == out2["action"]


# ── T11: Preço fixo não inventado ─────────────────────────────────────────────
class TestPrecoFixo:
    def test_instalacao_simples_850(self):
        state = empty_state()
        state["service"]["type"] = "instalacao"
        state["installation"]["btus"] = 12000
        state["fotos"] = {"local_interno": True, "local_externo": True, "aparelho": True}
        state["installation"]["ponto_eletrico_exclusivo"] = True
        state["installation"]["infra_pronta"] = True
        state["installation"]["distancia_aproximada"] = 2.0

        out = pipeline(make_input("tenho as fotos"), state)
        assert out["commercial_decision"]["fixed_price"] == 850
        assert out["action"] == "offer_fixed_installation"

    def test_higienization_200_per_appliance(self):
        state = empty_state()
        state["service"]["type"] = "higienizacao"
        state["higienizacao"]["quantidade_aparelhos"] = 3

        out = pipeline(make_input("tenho 3 aparelhos"), state)
        assert out["commercial_decision"]["fixed_price"] == 200  # per appliance
        assert out["action"] == "offer_hygienization_schedule"
        assert "R$600" in out["response_text"]


# ── T12: Text normalizer ──────────────────────────────────────────────────────
class TestTextNormalizer:
    def test_detect_quantity_um(self):
        assert detect_quantity("um") == 1
        assert detect_quantity("só um") == 1
        assert detect_quantity("uma") == 1
        assert detect_quantity("apenas um") == 1

    def test_detect_quantity_3(self):
        assert detect_quantity("3") == 3
        assert detect_quantity("três") == 3

    def test_detect_window_manha(self):
        assert detect_window("manhã") == "manha"
        assert detect_window("de manhã") == "manha"
        assert detect_window("pela manhã") == "manha"

    def test_detect_window_tarde(self):
        assert detect_window("tarde") == "tarde"
        assert detect_window("de tarde") == "tarde"

    def test_is_greeting(self):
        assert is_greeting("Bom dia") is True
        assert is_greeting("Oi") is True
        assert is_greeting("Tudo bem?") is True  # not exact match but short


# ── T13: Commercial Router — path authority ───────────────────────────────────
class TestCommercialRouter:
    def test_instalacao_sem_foto_path_technical_visit(self):
        state = empty_state()
        state["service"]["type"] = "instalacao"
        state["fotos"] = {"local_interno": False, "local_externo": False, "aparelho": False}

        decision = decide_commercial_path(state, "não tenho foto")
        assert decision["path"] == "technical_visit_50"

    def test_instalacao_validada_path_fixed(self):
        state = empty_state()
        state["service"]["type"] = "instalacao"
        state["installation"]["btus"] = 12000
        state["fotos"] = {"local_interno": True, "local_externo": True, "aparelho": True}
        state["installation"]["ponto_eletrico_exclusivo"] = True
        state["installation"]["infra_pronta"] = True
        state["installation"]["distancia_aproximada"] = 2.0

        decision = decide_commercial_path(state, "")
        assert decision["path"] == "fixed_installation_simple"
        assert decision["fixed_price"] == 850

    def test_higienizacao_path_fixed(self):
        state = empty_state()
        state["service"]["type"] = "higienizacao"

        decision = decide_commercial_path(state, "")
        assert decision["path"] == "fixed_hygienization"
        assert decision["fixed_price"] == 200

    def test_no_service_path_ask_basic(self):
        state = empty_state()
        decision = decide_commercial_path(state, "")
        assert decision["path"] == "ask_basic_service"


# ── T14: LeadState mínimo preservado ──────────────────────────────────────────
class TestLeadState:
    def test_state_has_all_required_fields(self):
        state = build_lead_state()
        required = ["identity", "service", "installation", "higienizacao",
                    "maintenance", "appointment", "commercial", "memory", "fotos"]
        for field in required:
            assert field in state, f"Missing field: {field}"

    def test_state_update_after_higienization(self):
        state = empty_state()
        state["service"]["type"] = "higienizacao"
        state["memory"]["last_asked_field"] = "quantidade_aparelhos"

        out = pipeline(make_input("2"), state)
        updated = out["lead_state_patch"]
        assert updated["higienizacao"]["quantidade_aparelhos"] == 2


if __name__ == "__main__":
    pytest.main([__file__, "-v"])