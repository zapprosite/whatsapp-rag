#!/usr/bin/env python3
"""
scripts/refine_hvacr_conversation_loop.py

Harness de simulação de atendimento HVAC-R para detectar e corrigir loops.

Uso:
  python scripts/refine_hvacr_conversation_loop.py --iterations 100
  python scripts/refine_hvacr_conversation_loop.py --scenario higienizacao
  python scripts/refine_hvacr_conversation_loop.py --scenario all --randomize
  python scripts/refine_hvacr_conversation_loop.py --save-failures
  python scripts/refine_hvacr_conversation_loop.py --no-llm
  python scripts/refine_hvacr_conversation_loop.py --iterations 100 --auto-suggest
  python scripts/refine_hvacr_conversation_loop.py --write-suggestions
"""
from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import os
import random
import sys
from copy import deepcopy
from datetime import datetime
from pathlib import Path
from typing import Any

# Garante que o root do projeto está no sys.path
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

os.environ.setdefault("MINIMAL_MVP_ENABLED", "1")
os.environ.setdefault("TTS_ENABLED", "0")
os.environ.setdefault("RAG_ENABLED", "0")

from agent_graph.nodes.nodes import _lead_state_copy
from app import mvp_attendance

# ---------------------------------------------------------------------------
# Frases proibidas
# ---------------------------------------------------------------------------
FORBIDDEN_PHRASES = [
    "qual é o próximo detalhe que você já consegue me informar",
    "continuando sua instalação, pra eu te orientar certinho",
    "vou adiantar pelo que já tenho",
    "quando puder, me manda as fotos",
    "não consigo agendar sem foto",
    "isso é instalação, manutenção",
]

# ---------------------------------------------------------------------------
# Preços permitidos
# ---------------------------------------------------------------------------
ALLOWED_PRICES = {"R$850", "R$200", "R$50"}

# ---------------------------------------------------------------------------
# Cenários fixos
# ---------------------------------------------------------------------------
SCENARIOS: dict[str, dict[str, Any]] = {
    "onboarding_basico": {
        "turns": ["bom dia", "quais serviços oferecem?", "não entendi"],
        "checks": ["no_ask_service_loop"],
    },
    "higienizacao_feliz": {
        "turns": ["bom dia", "preciso fazer uma higienização no meu ar", "William Rodrigues", "1", "tarde"],
        "checks": ["no_repeat_qty", "saves_qty_1", "no_same_response"],
    },
    "higienizacao_variacao_limpeza": {
        "turns": ["bom dia", "limpeza no ar", "Ana", "2", "manhã"],
        "checks": ["no_repeat_qty", "no_same_response"],
    },
    "higienizacao_variacao_geral": {
        "turns": ["bom dia", "dar uma geral no ar", "Joao", "1", "tarde"],
        "checks": ["no_repeat_qty"],
    },
    "quantidade_word_um": {
        "turns": ["bom dia", "higienização", "Maria", "um", "tarde"],
        "checks": ["no_repeat_qty", "saves_qty_1"],
    },
    "quantidade_word_dois": {
        "turns": ["bom dia", "higienização", "Pedro", "dois", "manhã"],
        "checks": ["no_repeat_qty"],
    },
    "instalacao_simples": {
        "turns": ["bom dia", "quero instalar um split", "Carlos", "12000", "tenho ponto elétrico", "tarde"],
        "checks": ["no_same_response"],
    },
    "instalacao_sem_foto": {
        "turns": ["bom dia", "instalação", "Lucia", "não tenho foto agora"],
        "checks": ["has_visit_50", "no_photo_loop"],
    },
    "instalacao_sem_infra": {
        "turns": ["bom dia", "instalação", "Roberto", "não tenho infraestrutura pronta"],
        "checks": ["has_visit_50"],
    },
    "manutencao_nao_gela": {
        "turns": ["bom dia", "meu ar não gela", "Fernando", "tarde"],
        "checks": ["has_visit_50", "no_same_response"],
    },
    "risco_eletrico": {
        "turns": ["bom dia", "disjuntor cai", "cheiro de queimado"],
        "checks": ["has_visit_50"],
    },
    "alto_valor_vrf": {
        "turns": ["bom dia", "preciso de VRF para loja", "Empresa XYZ"],
        "checks": ["no_r850", "has_project"],
    },
    "alto_valor_cassete": {
        "turns": ["bom dia", "quero um cassete", "Diego"],
        "checks": ["no_r850", "has_project"],
    },
    "alto_valor_piso_teto": {
        "turns": ["bom dia", "piso teto para sala de reunião", "Gerente"],
        "checks": ["no_r850", "has_project"],
    },
    "perguntas_abertas": {
        "turns": ["bom dia", "como funciona?", "quais serviços oferecem?", "qual valor?"],
        "checks": ["no_same_response"],
    },
    "cliente_confuso": {
        "turns": ["bom dia", "não entendi", "como assim?", "explica melhor"],
        "checks": ["no_same_response"],
    },
    "sotaque_istalacao": {
        "turns": ["bom dia", "istalação", "Will", "tarde"],
        "checks": [],
    },
    "sotaque_limpesa": {
        "turns": ["bom dia", "limpesa no ar", "Will", "1"],
        "checks": [],
    },
    "sotaque_manutencao": {
        "turns": ["bom dia", "manutençao", "Will", "tarde"],
        "checks": ["has_visit_50"],
    },
}


def _hash(text: str) -> str:
    return hashlib.md5(text.encode()).hexdigest()


def _mock_repo_stateful(lead_state=None):
    """Retorna fakes de repositório em memória."""
    store = {
        "lead_state": deepcopy(lead_state or _lead_state_copy()),
        "event_count": 0,
        "events": [],
        "pipeline_stage": "new",
        "service_type": (lead_state or {}).get("tipo_servico") if lead_state else None,
    }

    async def fake_load(phone, name=None):
        return {
            "id": "lead-1",
            "phone": phone,
            "name": store["lead_state"].get("nome"),
            "service_type": store["service_type"],
            "pipeline_stage": store["pipeline_stage"],
            "city_bairro": store["lead_state"].get("cidade_bairro"),
            "lead_state": deepcopy(store["lead_state"]),
            "event_count": store["event_count"],
            "available_columns": set(),
        }

    async def fake_update(phone, lead_state, *, pipeline_stage, service_type, city_bairro=None):
        store["lead_state"] = lead_state
        store["pipeline_stage"] = pipeline_stage
        store["service_type"] = service_type

    async def fake_event(phone, role, message, extracted_data=None):
        store["events"].append({"role": role, "message": message})
        store["event_count"] += 1

    return fake_load, fake_update, fake_event, store


async def _run_scenario(name: str, scenario: dict[str, Any], *, no_llm: bool = False) -> dict[str, Any]:
    turns = scenario["turns"]
    checks = scenario.get("checks", [])

    fake_load, fake_update, fake_event, store = _mock_repo_stateful()

    # Monkey-patch the repo functions
    original_load = mvp_attendance.load_or_create_lead
    original_update = mvp_attendance.update_lead_state
    original_event = mvp_attendance.create_lead_event
    mvp_attendance.load_or_create_lead = fake_load
    mvp_attendance.update_lead_state = fake_update
    mvp_attendance.create_lead_event = fake_event

    turn_logs = []
    history = []
    responses = []
    hashes = []
    failures = []

    try:
        for i, msg in enumerate(turns):
            msg_type = "audioMessage" if msg.startswith("[AUDIO]") else "conversation"
            text = msg.replace("[AUDIO]", "").strip() if msg.startswith("[AUDIO]") else msg

            result = await mvp_attendance.process_mvp_message(
                phone="5513000000000",
                message_text=text,
                instance="default",
                history=history,
            )
            history = result["messages"]
            response = str(result["messages"][-1].content)
            h = _hash(response)
            responses.append(response)
            hashes.append(h)

            lead_state_snap = deepcopy(store["lead_state"])
            log_entry = {
                "turno": i + 1,
                "mensagem_cliente": text,
                "message_type": msg_type,
                "lead_state_resumido": {
                    "tipo_servico": lead_state_snap.get("tipo_servico"),
                    "nome": lead_state_snap.get("nome"),
                    "last_asked_field": lead_state_snap.get("last_asked_field"),
                    "quantidade_aparelhos": lead_state_snap.get("higienizacao", {}).get("quantidade_aparelhos"),
                    "pipeline_stage": lead_state_snap.get("pipeline_stage"),
                },
                "response": response,
                "response_hash": h,
                "possible_loop": len(hashes) > 1 and hashes[-1] == hashes[-2],
                "warnings": [],
            }

            # Verifica frases proibidas
            for phrase in FORBIDDEN_PHRASES:
                if phrase.lower() in response.lower():
                    log_entry["warnings"].append(f"FRASE_PROIBIDA: {phrase}")
                    failures.append({
                        "failure_type": "forbidden_phrase",
                        "phrase": phrase,
                        "turno": i + 1,
                        "response": response,
                    })

            # Loop de resposta
            if log_entry["possible_loop"] and i > 0:
                log_entry["warnings"].append("LOOP_DETECTADO: resposta idêntica consecutiva")
                failures.append({
                    "failure_type": "response_loop",
                    "turno": i + 1,
                    "response": response,
                })

            turn_logs.append(log_entry)

        # --- Avaliação dos checks ---
        last = responses[-1] if responses else ""

        if "no_ask_service_loop" in checks:
            # Depois de perguntar lista de serviços, não pode repetir ask_basic_service
            for i in range(1, len(responses)):
                if "instalação, manutenção, higienização ou conserto?" in responses[i]:
                    failures.append({"failure_type": "ask_service_loop", "turno": i + 1})

        if "no_repeat_qty" in checks:
            # Depois de quantidade respondida, não pedir de novo
            qty_answered = False
            for i, (msg, resp) in enumerate(zip(turns, responses)):
                if qty_answered and "Quantos aparelhos são?" in resp:
                    failures.append({"failure_type": "repeated_qty_question", "turno": i + 1})
                if msg in {"1", "um", "uma", "2", "dois", "3", "três"} or msg.startswith("[AUDIO]"):
                    qty_answered = True

        if "saves_qty_1" in checks:
            qty = store["lead_state"].get("higienizacao", {}).get("quantidade_aparelhos")
            if qty != 1:
                failures.append({"failure_type": "qty_not_saved", "expected": 1, "got": qty})

        if "has_visit_50" in checks:
            if "R$50" not in last and "visita" not in last.lower():
                failures.append({"failure_type": "missing_visit_50", "response": last})

        if "no_r850" in checks:
            if "R$850" in last:
                failures.append({"failure_type": "wrong_price_r850_for_project", "response": last})

        if "has_project" in checks:
            if "visita" not in last.lower() and "projeto" not in last.lower() and "R$50" not in last:
                failures.append({"failure_type": "missing_project_route", "response": last})

        if "no_photo_loop" in checks:
            if "não consigo agendar sem foto" in last.lower() or "me manda as fotos" in last.lower():
                failures.append({"failure_type": "photo_block", "response": last})

        if "no_same_response" in checks:
            for i in range(1, len(responses)):
                if responses[i] == responses[i - 1]:
                    failures.append({"failure_type": "identical_consecutive_responses", "turno": i + 1})

        passed = len(failures) == 0
        return {
            "scenario": name,
            "turns": turn_logs,
            "failures": failures,
            "passed": passed,
            "lead_state": deepcopy(store["lead_state"]),
        }
    finally:
        mvp_attendance.load_or_create_lead = original_load
        mvp_attendance.update_lead_state = original_update
        mvp_attendance.create_lead_event = original_event


def _suggest_fix(failure: dict) -> dict:
    ft = failure.get("failure_type", "")
    suggestions = {
        "qty_not_saved": {
            "failure": "quantity_not_applied",
            "file": "agent_graph/nodes/reduce_lead_state.py",
            "suggested_change": "Verificar se last_asked_field='quantidade_aparelhos' está sendo persistido no lead_state antes do turno de resposta curta.",
            "test_to_add": "tests/test_short_answer_fields.py::test_quantity_word_um",
        },
        "repeated_qty_question": {
            "failure": "repeated_qty_question",
            "file": "agent_graph/nodes/plan_next_action.py",
            "suggested_change": "Garantir que qty != None implica em offer_hygienization_schedule e não offer_fixed_hygienization.",
            "test_to_add": "tests/test_response_loop_detection.py::test_no_repeat_quantos_after_answer",
        },
        "response_loop": {
            "failure": "response_loop",
            "file": "agent_graph/nodes/plan_next_action.py",
            "suggested_change": "Adicionar lógica de detecção de loop: se last_assistant == current_response e mensagem é diferente, forçar fallback_recover_context.",
            "test_to_add": "tests/test_response_loop_detection.py::test_no_same_response_loop",
        },
        "forbidden_phrase": {
            "failure": f"forbidden_phrase: {failure.get('phrase', '')}",
            "file": "agent_graph/domain/response_catalog.py",
            "suggested_change": "Remover ou substituir a frase proibida no catálogo de respostas.",
            "test_to_add": "tests/test_response_loop_detection.py::test_no_forbidden_phrases_higienizacao",
        },
        "missing_visit_50": {
            "failure": "missing_visit_50",
            "file": "agent_graph/nodes/plan_next_action.py",
            "suggested_change": "Verificar se roteamento para technical_visit_50 está correto para o serviço.",
            "test_to_add": "tests/test_hvacr_loop_scenarios.py::test_maintenance_default_visit",
        },
        "wrong_price_r850_for_project": {
            "failure": "wrong_price_r850_for_project",
            "file": "agent_graph/domain/commercial_router.py",
            "suggested_change": "Garantir que keywords de alto valor (VRF, cassete, etc.) são capturadas por _PROJECT_KEYWORDS antes de verificar instalação simples.",
            "test_to_add": "tests/test_high_value_routing.py::test_high_value_routes_to_project_quote",
        },
    }
    return suggestions.get(ft, {
        "failure": ft,
        "file": "agent_graph/",
        "suggested_change": f"Investigar failure_type='{ft}' manualmente.",
        "test_to_add": "tests/",
    })


async def main():
    parser = argparse.ArgumentParser(description="Harness de simulação HVAC-R")
    parser.add_argument("--scenario", default="all", help="Cenário para rodar (all ou nome específico)")
    parser.add_argument("--iterations", type=int, default=1, help="Número de iterações por cenário")
    parser.add_argument("--randomize", action="store_true", help="Randomizar ordem dos cenários")
    parser.add_argument("--save-failures", action="store_true", help="Salvar falhas em JSON")
    parser.add_argument("--auto-suggest", action="store_true", help="Sugerir patches para falhas detectadas")
    parser.add_argument("--write-suggestions", action="store_true", help="Salvar sugestões em JSONL")
    parser.add_argument("--no-llm", action="store_true", help="Modo sem LLM (apenas pipeline determinístico)")
    args = parser.parse_args()

    if args.scenario == "all":
        selected = list(SCENARIOS.items())
    elif args.scenario in SCENARIOS:
        selected = [(args.scenario, SCENARIOS[args.scenario])]
    else:
        print(f"❌ Cenário '{args.scenario}' não encontrado. Disponíveis: {', '.join(SCENARIOS.keys())}")
        sys.exit(1)

    if args.randomize:
        random.shuffle(selected)

    timestamp = datetime.now().strftime("%Y%m%d-%H%M")
    all_results = []
    all_suggestions = []
    total_pass = 0
    total_fail = 0

    for iteration in range(args.iterations):
        if args.iterations > 1:
            print(f"\n{'='*60}")
            print(f"ITERAÇÃO {iteration + 1}/{args.iterations}")
            print(f"{'='*60}")

        for scenario_name, scenario_def in selected:
            result = await _run_scenario(scenario_name, scenario_def, no_llm=args.no_llm)
            all_results.append(result)

            status = "✅ PASSOU" if result["passed"] else "❌ FALHOU"
            print(f"\n{'─'*50}")
            print(f"Cenário: {scenario_name} | {status}")
            print(f"{'─'*50}")

            for tlog in result["turns"]:
                print(f"  [Turno {tlog['turno']}] Cliente: \"{tlog['mensagem_cliente']}\"")
                lead_snap = tlog["lead_state_resumido"]
                print(f"    tipo_servico={lead_snap['tipo_servico']} | nome={lead_snap['nome']} | last_asked={lead_snap['last_asked_field']}")
                print(f"    qty_aparelhos={lead_snap['quantidade_aparelhos']} | stage={lead_snap['pipeline_stage']}")
                print(f"    → Bot: {tlog['response'][:120]}{'...' if len(tlog['response']) > 120 else ''}")
                print(f"    hash={tlog['response_hash']} | loop={tlog['possible_loop']}")
                if tlog["warnings"]:
                    for w in tlog["warnings"]:
                        print(f"    ⚠️  {w}")

            if result["failures"]:
                print(f"\n  Falhas detectadas ({len(result['failures'])}):")
                for f in result["failures"]:
                    print(f"    - {json.dumps(f, ensure_ascii=False)}")
                total_fail += 1

                if args.auto_suggest or args.write_suggestions:
                    for f in result["failures"]:
                        suggestion = _suggest_fix(f)
                        suggestion["scenario"] = scenario_name
                        all_suggestions.append(suggestion)
                        if args.auto_suggest:
                            print(f"\n  💡 Sugestão de patch:")
                            print(f"    {json.dumps(suggestion, ensure_ascii=False, indent=4)}")
            else:
                total_pass += 1

    # --- Resumo final ---
    print(f"\n{'='*60}")
    print(f"RESUMO: {total_pass} passou | {total_fail} falhou")
    print(f"{'='*60}")

    # --- Salvar falhas ---
    if args.save_failures:
        failures_dir = ROOT / "artifacts" / "refinement_failures" / timestamp
        failures_dir.mkdir(parents=True, exist_ok=True)
        failed_results = [r for r in all_results if not r["passed"]]
        for r in failed_results:
            fname = failures_dir / f"{r['scenario']}.json"
            with open(fname, "w", encoding="utf-8") as f:
                json.dump({
                    "scenario": r["scenario"],
                    "turns": r["turns"],
                    "failures": r["failures"],
                    "lead_state": r["lead_state"],
                    "failure_reason": r["failures"][0]["failure_type"] if r["failures"] else "unknown",
                    "suggested_fix": _suggest_fix(r["failures"][0]) if r["failures"] else {},
                }, f, ensure_ascii=False, indent=2)
            print(f"  💾 Falha salva: {fname}")

    # --- Salvar sugestões ---
    if args.write_suggestions and all_suggestions:
        sugg_dir = ROOT / "artifacts" / "refinement_suggestions" / timestamp
        sugg_dir.mkdir(parents=True, exist_ok=True)
        fname = sugg_dir / "suggestions.jsonl"
        with open(fname, "w", encoding="utf-8") as f:
            for s in all_suggestions:
                f.write(json.dumps(s, ensure_ascii=False) + "\n")
        print(f"\n  📝 Sugestões salvas: {fname}")

    sys.exit(0 if total_fail == 0 else 1)


if __name__ == "__main__":
    asyncio.run(main())
