#!/usr/bin/env python3
"""
refinar_llm.py — Loop de refinamento automático com LLM superior como juiz.

Um LLM mais capaz avalia cada resposta do Will contra o playbook de vendas,
dá nota de 0-10, gera a versão ideal e aplica a correção automaticamente.

Uso:
  python3 refinar_llm.py                  # 1 ciclo, cenários do playbook
  python3 refinar_llm.py --auto           # loop contínuo até score médio >= 8.0
  python3 refinar_llm.py --cena "msg"     # avalia uma mensagem específica
  python3 refinar_llm.py --gera           # só gera cenários, não aplica
  python3 refinar_llm.py --ciclos 3       # N ciclos de refinamento
"""
from __future__ import annotations
import os, sys, re, json, time, argparse, textwrap, subprocess
from pathlib import Path

try:
    import httpx
except ImportError:
    subprocess.run([sys.executable, "-m", "pip", "install", "httpx", "-q"])
    import httpx

# ── Config ────────────────────────────────────────────────────────────────────
BASE_URL     = "http://localhost:8000"
PLAYBOOK     = Path(__file__).parent / ".context/docs/playbook_vendas.md"
NODES_FILE   = Path(__file__).parent / "agent_graph/nodes/nodes.py"
LOG_FILE     = Path(__file__).parent / ".context/refinamento_log.jsonl"
SCORE_META   = 8.0   # meta de score médio para convergência
MARKER_START = "# EXEMPLOS_VALIDADOS_START"
MARKER_END   = "# EXEMPLOS_VALIDADOS_END"

# LLM juiz — usa o mais forte disponível
# Prioridade: Anthropic Opus → Groq 70b → MiniMax M2.7
JUDGE_MODEL_GROQ      = "llama-3.3-70b-versatile"
JUDGE_MODEL_ANTHROPIC = "claude-opus-4-7"

# ── ANSI ──────────────────────────────────────────────────────────────────────
R="\033[0m"; B="\033[1m"; DIM="\033[2m"
GR="\033[92m"; YL="\033[93m"; RD="\033[91m"; CY="\033[96m"; MG="\033[95m"

def c(col, t): return f"{col}{t}{R}"


# ── Playbook ──────────────────────────────────────────────────────────────────

def load_playbook() -> str:
    if not PLAYBOOK.exists():
        return ""
    return PLAYBOOK.read_text()


# ── Bot local ─────────────────────────────────────────────────────────────────

def call_will(message: str) -> dict:
    try:
        r = httpx.post(f"{BASE_URL}/test/chat",
                       params={"message": message}, timeout=90)
        r.raise_for_status()
        return r.json()
    except Exception as e:
        return {"error": str(e), "response": "", "intent": "?"}


# ── LLM Juiz ──────────────────────────────────────────────────────────────────

def _call_judge_anthropic(messages: list[dict], system: str) -> str:
    api_key = os.getenv("ANTHROPIC_API_KEY", "")
    if not api_key:
        raise RuntimeError("ANTHROPIC_API_KEY não configurado")
    r = httpx.post(
        "https://api.anthropic.com/v1/messages",
        headers={"x-api-key": api_key, "anthropic-version": "2023-06-01",
                 "Content-Type": "application/json"},
        json={"model": JUDGE_MODEL_ANTHROPIC, "max_tokens": 1024,
              "system": system, "messages": messages},
        timeout=120,
    )
    r.raise_for_status()
    return r.json()["content"][0]["text"]


def _call_judge_groq(messages: list[dict], system: str) -> str:
    api_key = os.getenv("GROQ_API_KEY", "")
    if not api_key:
        raise RuntimeError("GROQ_API_KEY não configurado")
    payload_msgs = [{"role": "system", "content": system}] + messages
    r = httpx.post(
        "https://api.groq.com/openai/v1/chat/completions",
        headers={"Authorization": f"Bearer {api_key}",
                 "Content-Type": "application/json"},
        json={"model": JUDGE_MODEL_GROQ, "messages": payload_msgs,
              "max_tokens": 1024, "temperature": 0.3},
        timeout=60,
    )
    r.raise_for_status()
    return r.json()["choices"][0]["message"]["content"]


def call_judge(messages: list[dict], system: str) -> str:
    """Tenta Anthropic Opus primeiro, cai no Groq 70b."""
    if os.getenv("ANTHROPIC_API_KEY"):
        try:
            return _call_judge_anthropic(messages, system)
        except Exception as e:
            print(c(YL, f"  Anthropic falhou ({e}), usando Groq 70b"))
    return _call_judge_groq(messages, system)


# ── Sistema do juiz ───────────────────────────────────────────────────────────

def build_judge_system(playbook: str) -> str:
    return f"""Você é um especialista em vendas B2C de serviços de climatização no Brasil,
com foco na Baixada Santista (São Vicente, Santos, Praia Grande, Guarujá).

Você avalia respostas de um atendente virtual chamado Will da Refrimix Tecnologia.

PLAYBOOK DE REFERÊNCIA:
{playbook}

Sua função: avaliar objetivamente se a resposta do Will converte leads em clientes,
soa humana e segue o playbook de vendas. Seja rigoroso — uma resposta genérica
não merece nota 8, mesmo se for educada.

CRITÉRIOS DE AVALIAÇÃO (peso igual):
1. CONVERSÃO: avança a venda? propõe próximo passo concreto?
2. TOM: soa como WhatsApp humano informal? usa "a gente", "pra", "tá"?
3. QUALIFICAÇÃO: fez pergunta qualificadora certa (localização/equipo/urgência)?
4. PREÇO: citou preço quando relevante? sem rodeios?
5. CONCISÃO: resposta curta e direta? sem listas, sem formalidade?

Responda SEMPRE em JSON válido:
{{
  "score": 0-10,
  "falhas": ["falha 1", "falha 2"],
  "ideal": "a resposta exata que o Will deveria ter enviado",
  "nivel": 1,
  "regra": "se nivel==1: regra ou exemplo a adicionar ao prompt"
}}

nivel: 1=WILL_SYSTEM_PROMPT, 2=RAG Qdrant, 3=SCORE_MAP keywords"""


# ── Cenários ──────────────────────────────────────────────────────────────────

CENARIOS_BASE = [
    # Instalação
    ("Quanto custa pra instalar ar condicionado?", "instalacao"),
    ("Quero instalar um split de 12000 BTU na sala. Fico em Santos.", "instalacao"),
    ("Vocês instalam equipamento que eu já comprei na loja?", "instalacao"),
    ("Faz instalação em apartamento no 5° andar?", "instalacao"),
    ("Tenho 3 quartos pra instalar, como funciona?", "instalacao"),
    # Higienização
    ("Meu ar tá com cheiro ruim quando liga.", "hygienizacao"),
    ("Qual a diferença de limpeza e higienização?", "hygienizacao"),
    ("Faz higienização com ozônio? Tenho criança em casa.", "hygienizacao"),
    ("Quanto custa pra higienizar um split?", "hygienizacao"),
    # Manutenção
    ("O ar não tá gelando mais, o que pode ser?", "manutencao"),
    ("Meu split fica desligando sozinho depois de 10 minutos.", "manutencao"),
    ("Tá pingando água dentro de casa.", "manutencao"),
    # Objeções
    ("Vi um anúncio aqui por R$400 a instalação. Vocês fazem por esse valor?", "instalacao"),
    ("Tá caro. Consegue fazer mais barato?", "instalacao"),
    ("Me manda um orçamento por escrito.", "instalacao"),
    ("Preciso pensar, vou ver com minha esposa.", "instalacao"),
    # Qualificação
    ("Oi, quero informação sobre ar condicionado.", "onboarding"),
    ("Bom dia! Vocês atendem em Praia Grande?", "onboarding"),
    ("Tenho uma empresa com 8 aparelhos, preciso de manutenção.", "manutencao"),
]


def gerar_cenarios_com_llm(playbook: str, n: int = 10) -> list[tuple[str, str]]:
    """Gera cenários novos e difíceis usando o LLM juiz."""
    system = f"""Você é um gerador de cenários de teste para um bot de vendas HVAC.

PLAYBOOK:
{playbook}

Gere {n} mensagens DIFÍCEIS que um lead real mandaria no WhatsApp — situações
que um bot genérico erraria: objeções de preço, comparação com concorrente,
perguntas ambíguas, múltiplas dúvidas na mesma mensagem, linguagem informal
extrema, leads que parecem curiosos mas são compradores reais.

Responda APENAS em JSON:
[
  {{"msg": "mensagem do lead", "servico": "instalacao|hygienizacao|manutencao|pmoc|onboarding"}},
  ...
]"""
    try:
        raw = call_judge([{"role": "user", "content": "Gera os cenários."}], system)
        data = json.loads(re.search(r'\[.*\]', raw, re.DOTALL).group())
        return [(d["msg"], d["servico"]) for d in data if "msg" in d]
    except Exception as e:
        print(c(YL, f"  Geração de cenários falhou ({e}), usando base"))
        return []


# ── Aplicar melhoria ──────────────────────────────────────────────────────────

def aplicar_melhoria(lead_msg: str, ideal: str, nivel: int, regra: str):
    """Aplica a melhoria no nível certo do código."""
    content = NODES_FILE.read_text()

    if nivel == 1:
        # Adiciona exemplo validado ou regra ao WILL_SYSTEM_PROMPT
        if MARKER_START not in content:
            print(c(YL, "  Marcador não encontrado, pulando."))
            return

        # Exemplo concreto Lead/Will
        exemplo = f'\nLead: "{lead_msg}"\nWill: "{ideal}"\n'
        # Evita duplicata
        if f'Lead: "{lead_msg}"' in content:
            # Substitui o exemplo existente com o melhor
            content = re.sub(
                rf'Lead: "{re.escape(lead_msg)}"\nWill: ".*?"',
                f'Lead: "{lead_msg}"\nWill: "{ideal}"',
                content, flags=re.DOTALL
            )
        else:
            content = content.replace(MARKER_END, exemplo + MARKER_END)

        NODES_FILE.write_text(content)
        print(c(GR, f"  ✓ Exemplo adicionado ao WILL_SYSTEM_PROMPT (nível 1)"))

    elif nivel == 3 and regra:
        # Regra nova no SCORE_MAP (formato: "keyword:peso:servico")
        parts = regra.split(":")
        if len(parts) == 3:
            kw, peso, svc = parts[0].strip(), parts[1].strip(), parts[2].strip()
            anchor = '        ("manutenção", 1): "manutencao",'
            entry  = f'        ("{kw}", {peso}): "{svc}",'
            if f'"{kw}"' not in content:
                content = content.replace(anchor, anchor + "\n" + entry)
                NODES_FILE.write_text(content)
                print(c(GR, f"  ✓ Keyword '{kw}' adicionada ao SCORE_MAP (nível 3)"))


# ── Log de resultados ─────────────────────────────────────────────────────────

def salvar_log(ciclo: int, msg: str, servico: str, will_resp: str,
               score: float, falhas: list, ideal: str):
    entry = {
        "ts": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "ciclo": ciclo,
        "lead": msg,
        "servico": servico,
        "will": will_resp,
        "score": score,
        "falhas": falhas,
        "ideal": ideal,
    }
    with open(LOG_FILE, "a") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")


# ── Ciclo de refinamento ──────────────────────────────────────────────────────

def avaliar_cenario(lead_msg: str, servico: str, playbook: str,
                    ciclo: int, aplicar: bool = True) -> float:
    """Avalia um cenário, imprime resultado e aplica melhoria se necessário."""

    # 1. Will responde
    print(c(DIM, f"  ▶ Lead: {lead_msg[:70]}"))
    data = call_will(lead_msg)
    will_resp = data.get("response") or data.get("error") or ""
    intent    = data.get("intent", "?")

    if not will_resp:
        print(c(RD, "  ✗ Will sem resposta"))
        return 0.0

    # 2. Juiz avalia
    system = build_judge_system(playbook)
    prompt = f"""Avalie a resposta do Will para este cenário:

Lead enviou: "{lead_msg}"
Serviço esperado: {servico}
Intent classificado: {intent}
Will respondeu: "{will_resp}"

Retorne o JSON de avaliação."""

    try:
        raw = call_judge([{"role": "user", "content": prompt}], system)
        # Extrai JSON do texto (o LLM pode adicionar texto antes/depois)
        match = re.search(r'\{.*\}', raw, re.DOTALL)
        if not match:
            raise ValueError("JSON não encontrado na resposta")
        resultado = json.loads(match.group())
    except Exception as e:
        print(c(RD, f"  ✗ Juiz falhou: {e}"))
        return 0.0

    score  = float(resultado.get("score", 0))
    falhas = resultado.get("falhas", [])
    ideal  = resultado.get("ideal", "")
    nivel  = int(resultado.get("nivel", 1))
    regra  = resultado.get("regra", "")

    # 3. Exibe resultado
    cor_score = GR if score >= 8 else (YL if score >= 6 else RD)
    print(f"  {c(B,'Will:')} {will_resp[:100]}")
    print(f"  {c(B,'Score:')} {c(cor_score, str(score))}/10", end="")
    if falhas:
        print(f"  {c(DIM,'Falhas:')} {' | '.join(falhas[:2])}")
    else:
        print()
    if ideal and score < SCORE_META:
        print(f"  {c(CY,'Ideal:')} {ideal[:120]}")

    # 4. Aplica melhoria se score abaixo da meta
    if score < SCORE_META and ideal and aplicar:
        aplicar_melhoria(lead_msg, ideal, nivel, regra)

    salvar_log(ciclo, lead_msg, servico, will_resp, score, falhas, ideal)
    print()
    return score


def rodar_ciclo(cenarios: list[tuple[str, str]], playbook: str,
                ciclo: int, aplicar: bool = True) -> float:
    """Roda um ciclo completo e retorna score médio."""
    scores = []
    for msg, svc in cenarios:
        s = avaliar_cenario(msg, svc, playbook, ciclo, aplicar)
        scores.append(s)
        time.sleep(0.5)   # evita rate limit

    media = sum(scores) / len(scores) if scores else 0.0
    print(f"\n{c(B,'─'*60)}")
    print(f"  Ciclo {ciclo} — Score médio: {c(MG, f'{media:.1f}/10')} "
          f"({sum(1 for s in scores if s >= SCORE_META)}/{len(scores)} acima de {SCORE_META})")
    print(f"{c(B,'─'*60)}\n")
    return media


def rebuild_container():
    print(c(YL, "  ⟳ Aplicando melhorias no container..."))
    r1 = subprocess.run(
        ["docker", "compose", "build", "fastapi-rag"],
        cwd=Path(__file__).parent, capture_output=True, text=True
    )
    if r1.returncode != 0:
        print(c(RD, f"  ✗ Build falhou:\n{r1.stderr[-400:]}"))
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
    time.sleep(5)
    try:
        r = httpx.get(f"{BASE_URL}/health", timeout=15)
        if r.status_code == 200:
            print(c(GR, "  ✓ Container atualizado e online"))
            return True
    except Exception:
        pass
    print(c(RD, "  ✗ Container não respondeu"))
    return False


def git_salvar(ciclo: int, score: float):
    subprocess.run(
        ["bash", "git.sh", "save",
         f"refina[llm]: ciclo {ciclo}, score médio {score:.1f}/10"],
        cwd=Path(__file__).parent, capture_output=True
    )


# ── CLI ───────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Loop de refinamento com LLM juiz")
    parser.add_argument("--auto",   action="store_true",
                        help=f"Loop até score médio >= {SCORE_META}")
    parser.add_argument("--cena",   metavar="MSG",
                        help="Avalia uma mensagem específica")
    parser.add_argument("--gera",   action="store_true",
                        help="Gera cenários com LLM e imprime, sem aplicar")
    parser.add_argument("--ciclos", type=int, default=1,
                        help="Número de ciclos (padrão: 1)")
    parser.add_argument("--sem-rebuild", action="store_true",
                        help="Não rebuilda o container após as melhorias")
    args = parser.parse_args()

    print(f"\n{c(B+MG,'╔══════════════════════════════════════════════════╗')}")
    print(f"{c(B+MG,'║  Refinamento Automático — LLM Juiz + Will Bot    ║')}")
    print(f"{c(B+MG,'╚══════════════════════════════════════════════════╝')}\n")

    playbook = load_playbook()
    if not playbook:
        print(c(RD, "✗ Playbook não encontrado em .context/docs/playbook_vendas.md"))
        sys.exit(1)

    # Verifica disponibilidade do juiz
    juiz = "Claude Opus" if os.getenv("ANTHROPIC_API_KEY") else "Groq 70b-versatile"
    print(f"  {c(CY,'Juiz:')} {juiz}")
    print(f"  {c(CY,'Meta:')} score médio >= {SCORE_META}/10\n")

    # ── Modo: cenário único ───────────────────────────────────────────────────
    if args.cena:
        print(f"{c(B,'─'*60)}")
        avaliar_cenario(args.cena, "?", playbook, ciclo=0, aplicar=not args.sem_rebuild)
        return

    # ── Modo: só gera cenários ────────────────────────────────────────────────
    if args.gera:
        print(c(YL, "Gerando cenários difíceis com LLM...\n"))
        novos = gerar_cenarios_com_llm(playbook, n=15)
        for msg, svc in novos:
            print(f"  [{svc}] {msg}")
        return

    # ── Define cenários ───────────────────────────────────────────────────────
    cenarios = list(CENARIOS_BASE)
    print(c(YL, "Gerando cenários adicionais com LLM..."))
    extras = gerar_cenarios_com_llm(playbook, n=8)
    if extras:
        cenarios.extend(extras)
        print(c(GR, f"  +{len(extras)} cenários gerados\n"))
    print(f"  Total de cenários: {c(B, str(len(cenarios)))}\n")

    # ── Loop de refinamento ───────────────────────────────────────────────────
    max_ciclos = 99 if args.auto else args.ciclos
    melhorias_total = 0

    for ciclo in range(1, max_ciclos + 1):
        print(f"\n{c(B+CY, f'══ CICLO {ciclo}/{max_ciclos} ══')}\n")

        score_antes = rodar_ciclo(cenarios, playbook, ciclo, aplicar=True)

        # Conta quantos exemplos foram adicionados
        content = NODES_FILE.read_text()
        melhorias = content.count('Lead: "') - 4  # subtrai os exemplos originais
        melhorias_novo = max(0, melhorias - melhorias_total)
        melhorias_total = max(0, melhorias)

        if melhorias_novo > 0 and not args.sem_rebuild:
            print(f"\n  {melhorias_novo} melhoria(s) aplicada(s) — rebuilding...")
            if rebuild_container():
                # Valida após rebuild
                print(f"\n{c(B+CY, '══ VALIDAÇÃO PÓS-REBUILD ══')}\n")
                score_depois = rodar_ciclo(cenarios[:10], playbook,
                                           ciclo * 100, aplicar=False)
                git_salvar(ciclo, score_depois)
                score_final = score_depois
            else:
                score_final = score_antes
        else:
            score_final = score_antes
            if melhorias_novo == 0:
                print(c(GR, "  Nenhuma melhoria necessária neste ciclo."))
            git_salvar(ciclo, score_final)

        # Convergência
        if args.auto and score_final >= SCORE_META:
            print(c(GR + B,
                f"\n✓ META ATINGIDA! Score {score_final:.1f}/10 >= {SCORE_META} "
                f"após {ciclo} ciclo(s)."))
            break
        elif not args.auto:
            break

    print(f"\n{c(DIM, f'Log salvo em: {LOG_FILE}')}\n")


if __name__ == "__main__":
    main()
