#!/usr/bin/env bash
# bot.sh — liga e desliga a IA do Will em tempo real
API="http://localhost:8000"

case "${1:-status}" in
  on)
    curl -s -X POST "$API/bot/on" -L -o /dev/null
    echo "🟢 Bot ATIVADO — Will responde normalmente"
    ;;
  off)
    curl -s -X POST "$API/bot/off" -L -o /dev/null
    echo "🔴 Bot PAUSADO — mensagens ignoradas pela IA"
    ;;
  status)
    STATUS=$(curl -s "$API/bot/status" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d['status'])" 2>/dev/null)
    if [ "$STATUS" = "ativo" ]; then
      echo "🟢 Bot ATIVO"
    else
      echo "🔴 Bot PAUSADO"
    fi
    ;;
  *)
    echo "Uso: ./bot.sh [on|off|status]"
    ;;
esac
