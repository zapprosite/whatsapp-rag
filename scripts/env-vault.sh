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
        python3 - "$ENV_FILE" "$EXAMPLE_FILE" <<'PY'
from __future__ import annotations

import re
import sys
from pathlib import Path

env_file = Path(sys.argv[1])
example_file = Path(sys.argv[2])
assignment = re.compile(r"^([A-Za-z_][A-Za-z0-9_]*)=.*$")


def key_from_line(line: str) -> str | None:
    stripped = line.strip()
    if stripped.startswith("#"):
        stripped = stripped[1:].strip()
    match = assignment.match(stripped)
    return match.group(1) if match else None


out: list[str] = []
seen: set[str] = set()
for raw_line in env_file.read_text(encoding="utf-8").splitlines():
    key = key_from_line(raw_line)
    if key:
        prefix = "# " if raw_line.strip().startswith("#") else ""
        out.append(f"{prefix}{key}={{SECRET}}")
        seen.add(key)
    else:
        out.append(raw_line)

if example_file.exists():
    preserved: list[str] = []
    for raw_line in example_file.read_text(encoding="utf-8").splitlines():
        key = key_from_line(raw_line)
        if key and key not in seen:
            preserved.append(raw_line)
            seen.add(key)
    if preserved:
        if out and out[-1].strip():
            out.append("")
        out.append("# --- Placeholders preservados do contrato mascarado ---")
        out.extend(preserved)

example_file.write_text("\n".join(out).rstrip() + "\n", encoding="utf-8")
PY
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
