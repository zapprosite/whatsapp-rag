#!/usr/bin/env bash
# sync.sh — gera CLAUDE.md a partir de .context/docs/*.md (substitui dotcontext CLI)
set -e

DOCS_DIR="$(dirname "$0")/.context/docs"
OUT="$(dirname "$0")/CLAUDE.md"
NOW=$(date -u +"%Y-%m-%dT%H:%M:%SZ")

if [ ! -d "$DOCS_DIR" ]; then
  echo "Erro: diretório $DOCS_DIR não encontrado"
  exit 1
fi

{
  echo "> Auto-generated from .context/docs on $NOW"
  echo ""

  for f in "$DOCS_DIR"/*.md; do
    [ -f "$f" ] || continue

    # Extrai metadados do frontmatter
    source=$(awk '/^source:/{print $2; exit}' "$f")
    type=$(awk '/^type:/{print $2; exit}' "$f")
    name=$(basename "$f" .md)

    echo "## $name"
    echo ""

    if [ -n "$source" ] || [ -n "$type" ]; then
      echo "---"
      [ -n "$source" ] && echo "source: $source"
      [ -n "$type" ]   && echo "type: $type"
      echo "---"
      echo ""
    fi

    # Conteúdo sem o bloco frontmatter (entre os primeiros ---)
    awk 'BEGIN{fm=0} /^---/{fm++; next} fm==2 || fm==0{print}' "$f"
    echo ""
    echo "---"
    echo ""
  done
} > "$OUT"

echo "✓ CLAUDE.md gerado a partir de $(ls "$DOCS_DIR"/*.md | wc -l | tr -d ' ') docs"
