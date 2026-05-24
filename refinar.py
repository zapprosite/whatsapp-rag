#!/usr/bin/env python3
"""
refinar.py — Ciclo de refinamento interativo do bot Will/Refrimix.

Uso:
  python3 refinar.py
  python3 refinar.py "O ar tá fazendo barulho"
"""
from __future__ import annotations
import os, sys, re, json, textwrap, subprocess
from pathlib import Path

try:
    import httpx
except ImportError:
    subprocess.run([sys.executable, "-m", "pip", "install", "httpx", "-q"])
    import httpx

# ── Config ────────────────────────────────────────────────────────────────────
BASE_URL   = "http://localhost:8000"
NODES_FILE = Path(__file__).parent / "agent_graph/nodes/nodes.py"
SEED_FILE  = Path(__file__).parent / "qdrant/seed_hvac.py"

# Marcadores no WILL_SYSTEM_PROMPT para a seção de exemplos validados
MARKER_START = "# EXEMPLOS_VALIDADOS_START"
MARKER_END   = "# EXEMPLOS_VALIDADOS_END"

# ── ANSI colors ───────────────────────────────────────────────────────────────
R="\033[0m"; BOLD="\033[1m"; DIM="\033[2m"
CYAN="\033[96m"; GREEN="\033[92m"; YELLOW="\033[93m"; RED="\033[91m"; MAGENTA="\033[95m"

def c(color: str, text: str) -> str:
    return f"{color}{text}{R}"


# ── API helpers ───────────────────────────────────────────────────────────────

def call_bot(message: str) -> dict:
    try:
        r = httpx.post(f"{BASE_URL}/test/chat", params={"message": message}, timeout=90)
        r.raise_for_status()
        return r.json()
    except Exception as e:
        return {"error": str(e)}


def call_refine(message: str, n: int = 3) -> list[dict]:
    results = []
    for _ in range(n):
        results.append(call_bot(message))
    return results


def health_ok() -> bool:
    try:
        r = httpx.get(f"{BASE_URL}/health", timeout=5)
        return r.status_code == 200
    except Exception:
        return False


# ── Display ───────────────────────────────────────────────────────────────────

def show_response(data: dict, message: str, label: str = "Will"):
    intent  = data.get("intent", "?")
    service = data.get("service", "?")
    rag     = data.get("rag_hits", 0)
    resp    = data.get("response") or data.get("error") or "(sem resposta)"

    color = GREEN if not data.get("error") else RED
    print(f"\n{BOLD}{'─'*62}{R}")
    print(f"  {c(DIM,'Msg:')} {message}")
    print(f"  {c(DIM,'Intent:')} {c(CYAN, intent)}  {c(DIM,'Service:')} {c(CYAN, service)}  {c(DIM,'RAG hits:')} {rag}")
    print(f"{BOLD}{'─'*62}{R}")
    for line in textwrap.wrap(resp, 60):
        print(f"  {c(color, line)}")
    print(f"{BOLD}{'─'*62}{R}\n")
    return resp, intent, service


# ── Patch helpers ─────────────────────────────────────────────────────────────

def ensure_exemplos_section():
    """Garante que o WILL_SYSTEM_PROMPT tem a seção de exemplos validados."""
    content = NODES_FILE.read_text()
    if MARKER_START in content:
        return  # já existe

    # Injeta antes do fechamento do triple-quote do prompt
    old = 'Região de atendimento: Baixada Santista (São Vicente, Santos, Praia Grande, Guarujá e região)."""'
    new = (
        'Região de atendimento: Baixada Santista (São Vicente, Santos, Praia Grande, Guarujá e região).\n\n'
        f'{MARKER_START}\n'
        '# Exemplos validados pelo Will — adicione aqui para ensinar o tom certo:\n'
        f'{MARKER_END}\n'
        '"""'
    )
    if old not in content:
        print(c(YELLOW, "  ⚠ Não encontrei o marcador no WILL_SYSTEM_PROMPT — editando manualmente pode ser necessário."))
        return
    NODES_FILE.write_text(content.replace(old, new))
    print(c(GREEN, "  ✓ Seção de exemplos criada no WILL_SYSTEM_PROMPT"))


def add_example_to_prompt(message: str, correct: str):
    """Adiciona Lead/Will exemplo ao WILL_SYSTEM_PROMPT."""
    ensure_exemplos_section()
    content = NODES_FILE.read_text()

    example = f'\nLead: "{message}"\nWill: "{correct}"\n'
    content = content.replace(
        MARKER_END,
        example + MARKER_END
    )
    NODES_FILE.write_text(content)
    print(c(GREEN, f"  ✓ Exemplo adicionado ao WILL_SYSTEM_PROMPT"))


def add_rule_to_prompt(rule: str):
    """Adiciona uma regra na seção REGRAS ABSOLUTAS do prompt."""
    content = NODES_FILE.read_text()
    marker = "- NUNCA repita informação que já foi dada no histórico da conversa."
    new_rule = f"- {rule.strip()}"
    if new_rule in content:
        print(c(YELLOW, "  ⚠ Regra já existe no prompt."))
        return
    content = content.replace(marker, marker + "\n" + new_rule)
    NODES_FILE.write_text(content)
    print(c(GREEN, f"  ✓ Regra adicionada ao WILL_SYSTEM_PROMPT"))


def add_keyword_to_scoremap(keyword: str, weight: int, service: str):
    """Adiciona keyword ao SCORE_MAP em classify_service."""
    content = NODES_FILE.read_text()
    anchor = f'        ("manutenção", 1): "manutencao",'
    entry  = f'        ("{keyword}", {weight}): "{service}",'
    if f'"{keyword}"' in content:
        print(c(YELLOW, f"  ⚠ Keyword '{keyword}' já existe no SCORE_MAP."))
        return
    content = content.replace(anchor, anchor + "\n" + entry)
    NODES_FILE.write_text(content)
    print(c(GREEN, f"  ✓ Keyword '{keyword}' (peso {weight}) → {service} adicionada ao SCORE_MAP"))


def add_qdrant_chunk(service: str, text: str, outcome: str = "analise_tecnica"):
    """Adiciona chunk de conhecimento ao seed_hvac.py."""
    content = SEED_FILE.read_text()
    marker = "# FIM_CHUNKS"
    chunk = (
        f'    {{\n'
        f'        "service_name": "{service}",\n'
        f'        "text": "{text}",\n'
        f'        "outcome": "{outcome}",\n'
        f'        "source": "refinamento_will",\n'
        f'    }},\n'
    )
    if marker not in content:
        # Adiciona antes do último colchete da lista CHUNKS
        content = re.sub(r'(\]\s*\nCHUNKS)', lambda m: chunk + m.group(0), content)
    else:
        content = content.replace(marker, chunk + marker)
    SEED_FILE.write_text(content)
    print(c(GREEN, f"  ✓ Chunk adicionado ao seed_hvac.py — rode 'python3 qdrant/seed_hvac.py' para indexar"))


# ── Container helpers ──────────────────────────────────────────────────────────

def rebuild_container():
    print(c(YELLOW, "\n  ⟳ Rebuilding container..."))
    r1 = subprocess.run(
        ["docker", "compose", "build", "fastapi-rag"],
        cwd=Path(__file__).parent,
        capture_output=True, text=True
    )
    if r1.returncode != 0:
        print(c(RED, f"  ✗ Build falhou:\n{r1.stderr[-500:]}"))
        return False

    subprocess.run(["docker", "rm", "-f", "whatsapp-rag-fastapi-rag-1"],
                   capture_output=True)
    env = Path(__file__).parent / ".env"
    subprocess.run([
        "docker", "run", "-d",
        "--name", "whatsapp-rag-fastapi-rag-1",
        "--network", "host",
        "--restart", "unless-stopped",
        "--env-file", str(env),
        "-e", "QDRANT_URL=http://127.0.0.1:6333",
        "-e", "QDRANT_COLLECTION=hermes_hvac_rag_service_staging",
        "whatsapp-rag-fastapi-rag:latest",
    ], capture_output=True)

    import time
    for i in range(15):
        time.sleep(2)
        if health_ok():
            print(c(GREEN, "  ✓ Container up!"))
            return True
        print(f"  aguardando... ({i*2}s)")
    print(c(RED, "  ✗ Container não respondeu em 30s"))
    return False


def git_save(message: str):
    cwd = Path(__file__).parent
    subprocess.run(["bash", "git.sh", "save", message], cwd=cwd)


# ── Menu de refinamento ───────────────────────────────────────────────────────

def menu_refinamento(message: str, resp: str, intent: str, service: str) -> bool:
    """Retorna True se houve mudança que precisa de rebuild."""
    print(f"{BOLD}O que ficou errado?{R}")
    print(f"  {c(CYAN,'1')} Tom/persona errado — Will falou de um jeito que não é seu")
    print(f"  {c(CYAN,'2')} Adicionar regra — algo que ele NUNCA deve fazer")
    print(f"  {c(CYAN,'3')} Intent errado — classificou o serviço errado")
    print(f"  {c(CYAN,'4')} Informação errada/faltando — dado técnico ou de preço")
    print(f"  {c(CYAN,'5')} Ver 3 variações da resposta (checar consistência)")
    print(f"  {c(CYAN,'0')} Voltar / pular")

    escolha = input(f"\n  {BOLD}>{R} ").strip()

    if escolha == "1":
        print(f"\n{c(BOLD,'O que o Will deveria ter dito?')} (escreva como você mesmo diria)")
        correto = input("  Will: ").strip()
        if correto:
            add_example_to_prompt(message, correto)
            return True

    elif escolha == "2":
        print(f"\n{c(BOLD,'Qual a regra a adicionar?')} (ex: NUNCA use 'prezado' ou 'atenciosamente')")
        regra = input("  Regra: ").strip()
        if regra:
            add_rule_to_prompt(regra)
            return True

    elif escolha == "3":
        print(f"\n  Intent atual: {c(CYAN, intent)} | Correto seria: ", end="")
        certo = input().strip()
        if certo:
            print(f"\n  Palavra-chave que identifica '{certo}' nessa mensagem: ", end="")
            kw = input().strip()
            if kw:
                print(f"  Peso (1=fraco, 3=médio, 5=forte): ", end="")
                try:
                    peso = int(input().strip())
                except ValueError:
                    peso = 3
                add_keyword_to_scoremap(kw, peso, certo)
                return True

    elif escolha == "4":
        print(f"\n  Serviço relacionado (instalacao/manutencao/pmoc/consultoria/higienizacao/projeto-central): ", end="")
        svc = input().strip() or service or "manutencao"
        print(f"\n  Escreva a informação correta (ex: 'Cobro R$150 a visita técnica. Se fechar, desconta.'): ")
        texto = input("  > ").strip()
        if texto:
            add_qdrant_chunk(svc, texto)
            print(c(YELLOW, "\n  ⟳ Re-indexando Qdrant..."))
            r = subprocess.run(
                [sys.executable, "qdrant/seed_hvac.py"],
                cwd=Path(__file__).parent,
                capture_output=True, text=True
            )
            if r.returncode == 0:
                print(c(GREEN, "  ✓ Qdrant re-indexado"))
            else:
                print(c(RED, f"  ✗ Seed falhou: {r.stderr[-300:]}"))
            return False  # Qdrant é consultado em runtime, não precisa rebuild

    elif escolha == "5":
        print(c(YELLOW, "\n  Rodando 3 variações...\n"))
        for i, d in enumerate(call_refine(message, 3), 1):
            resp_v, _, _ = show_response(d, message, label=f"Will #{i}")
        return False

    return False


# ── Main loop ─────────────────────────────────────────────────────────────────

def main():
    print(f"\n{BOLD}{MAGENTA}╔══════════════════════════════════════════╗{R}")
    print(f"{BOLD}{MAGENTA}║  Refinador de Respostas — Will/Refrimix  ║{R}")
    print(f"{BOLD}{MAGENTA}╚══════════════════════════════════════════╝{R}")

    if not health_ok():
        print(c(RED, "\n✗ API não está respondendo em http://localhost:8000"))
        print(c(DIM, "  Suba o container: docker compose up -d fastapi-rag"))
        sys.exit(1)

    print(c(GREEN, "  ✓ API online\n"))

    initial_msg = " ".join(sys.argv[1:]) if len(sys.argv) > 1 else None
    needs_rebuild = False

    while True:
        # ── Pega mensagem ─────────────────────────────────────────────────
        if initial_msg:
            message = initial_msg.strip()
            initial_msg = None
        else:
            print(f"\n{c(BOLD,'Mensagem do lead')} (ou {c(CYAN,'sair')} / {c(CYAN,'rebuild')} / {c(CYAN,'commit')}): ", end="")
            message = input().strip()

        if message.lower() in ("sair", "exit", "q"):
            if needs_rebuild:
                print(c(YELLOW, "\n  Tem mudanças não aplicadas. Fazer rebuild agora? [s/N] "), end="")
                if input().strip().lower() == "s":
                    if rebuild_container():
                        git_save("refina: ajustes de tom e keywords via refinar.py")
            break

        if message.lower() == "rebuild":
            if rebuild_container():
                needs_rebuild = False
                git_save("refina: ajustes de tom e keywords via refinar.py")
            continue

        if message.lower() == "commit":
            git_save("refina: ajustes de tom e keywords via refinar.py")
            continue

        if not message:
            continue

        # ── Chama o bot ───────────────────────────────────────────────────
        print(c(DIM, "  chamando Will..."))
        data = call_bot(message)
        resp, intent, service = show_response(data, message)

        # ── Aprova? ───────────────────────────────────────────────────────
        print(f"  {c(GREEN,'[s]')} Boa, próxima  "
              f"{c(YELLOW,'[r]')} Refinar  "
              f"{c(RED,'[n]')} Próxima sem salvar")
        escolha = input(f"  {BOLD}>{R} ").strip().lower()

        if escolha in ("s", ""):
            print(c(GREEN, "  ✓ Aprovado!\n"))

        elif escolha == "r":
            mudou = menu_refinamento(message, resp, intent, service)
            if mudou:
                needs_rebuild = True
                print(c(YELLOW, f"\n  Mudança salva. {c(BOLD,'Quando terminar de refinar, digite: rebuild')}"))
                print(c(DIM,    "  (ou continue testando outras mensagens antes do rebuild)"))

        # 'n' ou qualquer outra coisa → próxima sem ação

    print(c(DIM, "\nAté logo!\n"))


if __name__ == "__main__":
    main()
