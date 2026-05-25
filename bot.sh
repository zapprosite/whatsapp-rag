#!/usr/bin/env bash
# bot.sh — liga e desliga a IA do Will em tempo real
set -euo pipefail

API="${BOT_API_URL:-http://localhost:8000}"

request_json() {
  local method="$1"
  local path="$2"
  local response

  if ! response="$(curl -fsS -X "$method" "$API$path" -L 2>/dev/null)"; then
    return 1
  fi

  printf '%s' "$response"
}

status_summary() {
  local response

  if ! response="$(request_json GET "/bot/status")"; then
    return 1
  fi

  printf '%s' "$response" | python3 -c '
import json
import sys

try:
    data = json.load(sys.stdin)
    status = data["status"]
    updated_at = data.get("updated_at") or "não registrada"
    updated_by = data.get("updated_by") or "não registrada"
    if "off_message_configured" in data:
        off_message = "configurada" if data.get("off_message_configured") else "não configurada"
    else:
        off_message = "não informada pela API"
    print("\t".join([status, updated_at, updated_by, off_message]))
except Exception:
    sys.exit(1)
'
}

print_status() {
  local summary status updated_at updated_by off_message
  if ! summary="$(status_summary)"; then
    echo "✗ Não consegui ler status válido em $API/bot/status" >&2
    exit 1
  fi

  IFS=$'\t' read -r status updated_at updated_by off_message <<< "$summary"

  if [ "$status" = "ativo" ]; then
    echo "🟢 Bot ATIVO — IA responde no WhatsApp"
  elif [ "$status" = "pausado" ]; then
    echo "🔴 Bot PAUSADO — IA não conduz atendimento"
  else
    echo "✗ Status desconhecido: $status" >&2
    exit 1
  fi

  echo "   alteração: $updated_at | origem: $updated_by | ausência: $off_message"
}

case "${1:-status}" in
  on)
    if ! request_json POST "/bot/on" >/dev/null; then
      echo "✗ API do bot não respondeu em $API" >&2
      exit 1
    fi
    print_status
    ;;
  off)
    if ! request_json POST "/bot/off" >/dev/null; then
      echo "✗ API do bot não respondeu em $API" >&2
      exit 1
    fi
    print_status
    ;;
  toggle)
    if ! request_json POST "/bot/toggle" >/dev/null; then
      echo "✗ API do bot não respondeu em $API" >&2
      exit 1
    fi
    print_status
    ;;
  status)
    print_status
    ;;
  *)
    echo "Uso: ./bot.sh [on|off|toggle|status]"
    exit 2
    ;;
esac
