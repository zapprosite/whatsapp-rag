#!/usr/bin/env bash
# sync.sh — gera CLAUDE.md de forma determinística e espelha Gitea -> GitHub.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DOCS_DIR="$ROOT/.context/docs"
OUT="$ROOT/CLAUDE.md"
GITEA_REMOTE="${GITEA_REMOTE:-origin}"
GITHUB_REMOTE="${GITHUB_REMOTE:-github}"
COMMIT_MESSAGE="${COMMIT_MESSAGE:-sync: atualiza docs e espelho github}"
DO_GIT="${SYNC_GITHUB:-1}"
MIRROR_ONLY=0

usage() {
  cat <<'EOF'
Uso: ./sync.sh [--no-git] [--git] [--mirror-only] [--message "msg"]

Contrato:
  - .context/docs/*.md é a fonte canônica.
  - CLAUDE.md é sempre gerado; não edite CLAUDE.md manualmente.
  - O fluxo correto é Gitea (origin) -> GitHub (github).
  - Por padrão: gera, commita, push no Gitea e espelha o ref do Gitea no GitHub.

Opções:
  --no-git          só gera CLAUDE.md, sem commit/push
  --git             força commit/push/espelho
  --mirror-only     não gera nem commita; só espelha origin/BRANCH -> github/BRANCH
  --message "msg"   mensagem do commit automático

Variáveis:
  SYNC_GITHUB=0      equivalente a --no-git
  GITEA_REMOTE=...   remoto primário Gitea (padrão: origin)
  GITHUB_REMOTE=...  remoto espelho GitHub (padrão: github)
  COMMIT_MESSAGE=... mensagem do commit automático
EOF
}

fail() {
  echo "Erro: $*" >&2
  exit 1
}

parse_args() {
  while [ "$#" -gt 0 ]; do
    case "$1" in
      --no-git)
        DO_GIT=0
        shift
        ;;
      --git)
        DO_GIT=1
        shift
        ;;
      --mirror-only)
        DO_GIT=1
        MIRROR_ONLY=1
        shift
        ;;
      --message)
        COMMIT_MESSAGE="${2:-}"
        [ -n "$COMMIT_MESSAGE" ] || fail "--message precisa de texto"
        shift 2
        ;;
      -h|--help)
        usage
        exit 0
        ;;
      *)
        usage
        fail "argumento desconhecido: $1"
        ;;
    esac
  done
}

current_branch() {
  local branch
  branch="$(git branch --show-current)"
  [ -n "$branch" ] || fail "não consegui detectar a branch atual"
  printf '%s' "$branch"
}

require_git_repo() {
  cd "$ROOT"
  git rev-parse --is-inside-work-tree >/dev/null 2>&1 || fail "$ROOT não está dentro de um repositório git"
}

require_remote() {
  local remote="$1"
  local label="$2"
  git remote get-url "$remote" >/dev/null 2>&1 || fail "remoto $label '$remote' não existe"
}

generate_claude() {
  [ -d "$DOCS_DIR" ] || fail "diretório $DOCS_DIR não encontrado"

  DOCS_DIR="$DOCS_DIR" OUT="$OUT" python3 - <<'PY'
from __future__ import annotations

import hashlib
import os
from pathlib import Path

docs_dir = Path(os.environ["DOCS_DIR"])
out = Path(os.environ["OUT"])
files = sorted(docs_dir.glob("*.md"), key=lambda p: p.name)

if not files:
    raise SystemExit(f"Erro: nenhum .md encontrado em {docs_dir}")


def split_frontmatter(text: str) -> tuple[dict[str, str], str]:
    if not text.startswith("---\n"):
        return {}, text

    end = text.find("\n---\n", 4)
    if end == -1:
        return {}, text

    raw_meta = text[4:end]
    body = text[end + len("\n---\n") :]
    meta: dict[str, str] = {}
    for line in raw_meta.splitlines():
        if ":" not in line:
            continue
        key, value = line.split(":", 1)
        key = key.strip()
        value = value.strip()
        if key:
            meta[key] = value
    return meta, body.lstrip("\n")


sections: list[str] = []
fingerprint_source = hashlib.sha256()

for path in files:
    text = path.read_text(encoding="utf-8")
    fingerprint_source.update(path.name.encode("utf-8"))
    fingerprint_source.update(b"\0")
    fingerprint_source.update(text.encode("utf-8"))

    meta, body = split_frontmatter(text)
    title = path.stem
    section: list[str] = [f"## {title}", ""]

    if meta:
        section.append("---")
        for key in sorted(meta):
            section.append(f"{key}: {meta[key]}")
        section.extend(["---", ""])

    section.append(body.rstrip())
    section.extend(["", "---", ""])
    sections.append("\n".join(section))

fingerprint = fingerprint_source.hexdigest()[:16]
header = "\n".join(
    [
        "<!-- GENERATED FILE: do not edit manually. Source: .context/docs/*.md. Run ./sync.sh. -->",
        f"> Auto-generated from .context/docs | fingerprint: {fingerprint}",
        "",
    ]
)

tmp = out.with_suffix(out.suffix + ".tmp")
tmp.write_text(header + "\n".join(sections).rstrip() + "\n", encoding="utf-8")
tmp.replace(out)
print(f"✓ CLAUDE.md gerado de {len(files)} docs | fingerprint {fingerprint}")
PY
}

stage_operational_files() {
  git add \
    CLAUDE.md GUIDE_REFINAMENTO.md README.md AGENTS.md \
    .gitattributes .rules/ orcamento_teste.pdf \
    .context/docs/*.md docs/*.md docs/audits/*.md env.schema.md \
    sync.sh git.sh bot.sh refinar.py refinar_llm.py refinar_tts.py scripts/ \
    requirements.txt pytest.ini docker-compose.yml \
    agent_graph/ app/ qdrant/ prisma/ sre/ tests/ knowledge/ \
    .env.example prisma/.env.example 2>/dev/null || true
}

commit_if_needed() {
  stage_operational_files
  if git diff --cached --quiet; then
    echo "✓ Sem mudanças staged para commit"
    return
  fi
  git commit -m "$COMMIT_MESSAGE"
}

push_gitea() {
  local branch="$1"
  git push "$GITEA_REMOTE" "$branch"
  echo "✓ Gitea atualizado: $GITEA_REMOTE/$branch"
}

mirror_gitea_to_github() {
  local branch="$1"
  git fetch "$GITEA_REMOTE" "$branch" --quiet
  git push "$GITHUB_REMOTE" "refs/remotes/$GITEA_REMOTE/$branch:refs/heads/$branch"
  echo "✓ Espelho GitHub atualizado: $GITEA_REMOTE/$branch -> $GITHUB_REMOTE/$branch"
}

main() {
  parse_args "$@"
  require_git_repo
  require_remote "$GITEA_REMOTE" "Gitea"
  require_remote "$GITHUB_REMOTE" "GitHub"

  local branch
  branch="$(current_branch)"

  if [ "$MIRROR_ONLY" = "1" ]; then
    echo "↷ mirror-only: sem geração local; espelhando Gitea -> GitHub"
    mirror_gitea_to_github "$branch"
    return
  fi

  generate_claude

  if [ "$DO_GIT" != "1" ]; then
    echo "↷ Commit/push ignorado por SYNC_GITHUB=0/--no-git"
    return
  fi

  commit_if_needed
  push_gitea "$branch"
  mirror_gitea_to_github "$branch"
}

main "$@"
