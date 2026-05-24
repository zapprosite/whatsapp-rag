#!/usr/bin/env bash
# git.sh — atalhos rápidos para o ciclo de versioning do whatsapp-rag
set -e

BRANCH_FEATURE="agent/refinar-respostas-texto"

cmd="${1:-help}"
msg="${2:-}"

case "$cmd" in

  save)
    # Commita tudo que mudou na feature branch
    if [ -z "$msg" ]; then
      echo "Uso: ./git.sh save \"mensagem do commit\""
      exit 1
    fi
    git add agent_graph/ app/ prisma/ qdrant/ requirements.txt \
            docker-compose.yml CLAUDE.md GUIDE_REFINAMENTO.md README.md \
            .gitignore .env.example prisma/.env.example 2>/dev/null || true
    git commit -m "$msg"
    git push
    echo "✓ Commit e push feitos na branch $(git branch --show-current)"
    ;;

  push)
    # Push simples da branch atual
    git push
    echo "✓ Push feito"
    ;;

  status)
    git status --short
    git log --oneline -5
    ;;

  merge)
    # Faz merge da feature branch para main e volta para feature
    CURRENT=$(git branch --show-current)
    echo "→ Mergeando $BRANCH_FEATURE → main"
    git checkout main
    git pull
    git merge --no-ff "$BRANCH_FEATURE" -m "merge: $BRANCH_FEATURE → main"
    git push
    git checkout "$CURRENT"
    echo "✓ Merge concluído. Voltou para $CURRENT"
    ;;

  log)
    git log --oneline --graph --all -15
    ;;

  diff)
    git diff --stat
    ;;

  *)
    echo "Uso: ./git.sh <comando> [mensagem]"
    echo ""
    echo "  save \"msg\"  — add + commit + push tudo na feature branch"
    echo "  push        — push da branch atual"
    echo "  merge       — merge feature → main (e volta pra feature)"
    echo "  status      — arquivos modificados + últimos commits"
    echo "  log         — histórico visual das branches"
    echo "  diff        — o que mudou (resumo)"
    ;;
esac
