#!/usr/bin/env bash
set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ENV_FILE="${WHATSAPP_RAG_ENV_FILE:-$PROJECT_ROOT/.env}"
EXAMPLE_FILE="${WHATSAPP_RAG_EXAMPLE_FILE:-$PROJECT_ROOT/.env.example}"

unlock() {
    if [ -f "$ENV_FILE" ]; then
        chattr -i "$ENV_FILE" 2>/dev/null || true
    fi
}

lock() {
    if [ -f "$ENV_FILE" ]; then
        chmod 600 "$ENV_FILE" 2>/dev/null || true
        chattr +i "$ENV_FILE" 2>/dev/null || true
    fi
}

sync_example() {
    if [ -f "$ENV_FILE" ]; then
        awk -F= '
        /^[ \t]*$/ { print; next }
        /^#[ \t]*[A-Za-z0-9_]+=/ {
            sub(/=.*/, "={SECRET}");
            print; next
        }
        /^#/ { print; next }
        NF>0 {
            sub(/=.*/, "={SECRET}");
            print
        }' "$ENV_FILE" > "$EXAMPLE_FILE"
    else
        touch "$EXAMPLE_FILE"
    fi
}

case "${1:-}" in
    edit)
        unlock
        "${EDITOR:-nano}" "$ENV_FILE"
        sync_example
        lock
        ;;
    sync)
        unlock
        sync_example
        lock
        ;;
    unlock)
        unlock
        ;;
    lock)
        lock
        ;;
    *)
        echo "Uso: scripts/env-vault.sh [edit|sync|unlock|lock]" >&2
        exit 1
        ;;
esac
