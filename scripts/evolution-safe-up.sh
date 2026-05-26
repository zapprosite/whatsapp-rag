#!/usr/bin/env bash
set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$PROJECT_ROOT"

.venv/bin/python scripts/evolution-preflight.py --env-file .env
docker compose up -d evolution-api
