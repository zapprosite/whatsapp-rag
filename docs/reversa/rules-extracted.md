# RULES EXTRACTED — qua 27 mai 2026 05:00:59 -03
## Prices in code
./.venv/lib/python3.12/site-packages/pip/_internal/cli/base_command.py:                    return ERROR
./.venv/lib/python3.12/site-packages/pip/_internal/cli/base_command.py:                    return PREVIOUS_BUILD_DIR_ERROR
./.venv/lib/python3.12/site-packages/pip/_internal/cli/base_command.py:                    return ERROR
./.venv/lib/python3.12/site-packages/pip/_internal/cli/base_command.py:                    return ERROR
./.venv/lib/python3.12/site-packages/pip/_internal/cli/base_command.py:                    return ERROR
./.venv/lib/python3.12/site-packages/pip/_internal/cli/base_command.py:                    return ERROR
./.venv/lib/python3.12/site-packages/pip/_internal/cli/base_command.py:                    return UNKNOWN_ERROR
./.venv/lib/python3.12/site-packages/pip/_internal/cli/parser.py:from pip._internal.cli.status_codes import UNKNOWN_ERROR
./.venv/lib/python3.12/site-packages/pip/_internal/commands/cache.py:            return ERROR
./.venv/lib/python3.12/site-packages/pip/_internal/commands/cache.py:            return ERROR
./.venv/lib/python3.12/site-packages/pip/_internal/commands/cache.py:            return ERROR
./.venv/lib/python3.12/site-packages/pip/_internal/commands/check.py:            return ERROR
./.venv/lib/python3.12/site-packages/pip/_internal/commands/configuration.py:            return ERROR
./.venv/lib/python3.12/site-packages/pip/_internal/commands/configuration.py:            return ERROR
./.venv/lib/python3.12/site-packages/pip/_internal/commands/configuration.py:            return ERROR
./.venv/lib/python3.12/site-packages/pip/_internal/commands/configuration.py:                return kinds.USER
./.venv/lib/python3.12/site-packages/pip/_internal/commands/hash.py:            return ERROR
./.venv/lib/python3.12/site-packages/pip/_internal/commands/index.py:            return ERROR
./.venv/lib/python3.12/site-packages/pip/_internal/commands/index.py:            return ERROR
./.venv/lib/python3.12/site-packages/pip/_internal/commands/install.py:            return ERROR
./.venv/lib/python3.12/site-packages/pip/_internal/commands/show.py:            return ERROR
./.venv/lib/python3.12/site-packages/pip/_internal/commands/show.py:            return ERROR
./.venv/lib/python3.12/site-packages/pip/_internal/configuration.py:OVERRIDE_ORDER = kinds.GLOBAL, kinds.USER, kinds.SITE, kinds.ENV, kinds.ENV_VAR
./.venv/lib/python3.12/site-packages/pip/_internal/configuration.py:            variant: [] for variant in OVERRIDE_ORDER
./.venv/lib/python3.12/site-packages/pip/_internal/configuration.py:            variant: {} for variant in OVERRIDE_ORDER
./.venv/lib/python3.12/site-packages/pip/_internal/configuration.py:        things in the same order as OVERRIDE_ORDER
./.venv/lib/python3.12/site-packages/pip/_internal/resolution/resolvelib/candidates.py:        return REQUIRES_PYTHON_IDENTIFIER
./.venv/lib/python3.12/site-packages/pip/_internal/resolution/resolvelib/candidates.py:        return REQUIRES_PYTHON_IDENTIFIER
./.venv/lib/python3.12/site-packages/pip/_internal/resolution/resolvelib/provider.py:from .candidates import REQUIRES_PYTHON_IDENTIFIER
./.venv/lib/python3.12/site-packages/pip/_internal/resolution/resolvelib/provider.py:        requires_python = identifier == REQUIRES_PYTHON_IDENTIFIER

## Intent mapping
refrimix_core/domain/natural_microcopy.py:FAST_LANE_INTENTS = frozenset({
refrimix_core/domain/model_router.py:from refrimix_core.domain.natural_microcopy import FAST_LANE_INTENTS
refrimix_core/domain/model_router.py:    intent: str
refrimix_core/domain/model_router.py:def route(text: str, intent_hint: str | None = None) -> RoutingDecision:
refrimix_core/domain/model_router.py:        intent_hint: intent já classificada (opcional)
refrimix_core/domain/model_router.py:    # Se intent é conhecida e é fast lane pura
refrimix_core/domain/model_router.py:    if intent_hint in FAST_LANE_INTENTS and is_fast_lane_only(folded):
refrimix_core/domain/model_router.py:            intent=intent_hint,
refrimix_core/domain/model_router.py:            intent=intent_hint or "unknown",
refrimix_core/domain/model_router.py:            intent=intent_hint or "greeting_short",
refrimix_core/domain/model_router.py:        intent=intent_hint or "unknown",
refrimix_core/tools/google_drive_tool.py:        f"**Intent:** {lead_summary.get('intent', 'N/A')}\n",
refrimix_core/tools/google_integration_smoke.py:        "intent": "higienizacao_rinite",
refrimix_core/tools/google_integration_smoke.py:        "intent": fake_lead["intent"],
refrimix_core/runtime/whatsapp_orchestrator.py:        "[%s] Routing: lane=%s intent=%s reason=%s",
