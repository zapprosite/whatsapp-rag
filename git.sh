#!/usr/bin/env bash
# git.sh — atalhos compatíveis; o fluxo real é sync.sh (Gitea -> GitHub).
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SYNC="$ROOT/sync.sh"
BRANCH_FEATURE="${BRANCH_FEATURE:-agent/refinar-respostas-texto}"

usage() {
  cat <<'EOF'
Uso: ./git.sh <comando> [mensagem]

Comandos:
  save "msg"  — gera CLAUDE.md, commita, push no Gitea e espelha no GitHub
  push        — espelha origin/branch -> github/branch
  sync "msg"  — alias de save
  status      — arquivos modificados + últimos commits
  merge       — merge feature -> main e publica via sync.sh
  log         — histórico visual
  diff        — resumo do diff

Regra:
  origin = Gitea primário
  github = espelho GitHub
EOF
}

require_sync() {
  [ -x "$SYNC" ] || {
    echo "Erro: $SYNC não existe ou não está executável" >&2
    exit 1
  }
}

cmd="${1:-help}"
msg="${2:-}"

case "$cmd" in
  save|sync)
    if [ -z "$msg" ]; then
      echo "Uso: ./git.sh $cmd \"mensagem do commit\"" >&2
      exit 2
    fi
    require_sync
    "$SYNC" --message "$msg"
    ;;

  push)
    require_sync
    "$SYNC" --mirror-only
    ;;

  status)
    git status --short
    git log --oneline -5
    ;;

  merge)
    require_sync
    current=$(git branch --show-current)
    echo "→ Mergeando $BRANCH_FEATURE -> main"
    git checkout main
    git pull origin main
    git merge --no-ff "$BRANCH_FEATURE" -m "merge: $BRANCH_FEATURE -> main"
    "$SYNC" --message "merge: $BRANCH_FEATURE -> main"
    git checkout "$current"
    echo "✓ Merge concluído. Voltou para $current"
    ;;

  log)
    git log --oneline --graph --all -15
    ;;

  diff)
    git diff --stat
    ;;

  help|-h|--help)
    usage
    ;;

  *)
    usage
    exit 2
    ;;
esac
