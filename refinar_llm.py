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
from pydantic import BaseModel, Field
from openai import OpenAI

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

# LLM juiz — usa o que já existe no stack
# Prioridade: Groq 70b → Qwen2.5-VL local
JUDGE_MODEL_GROQ      = "llama-3.3-70b-versatile"
LOCAL_QWEN_BASE_URL   = os.getenv("LOCAL_QWEN_BASE_URL", "http://127.0.0.1:8010/v1").rstrip("/")
LOCAL_QWEN_MODEL      = os.getenv("LOCAL_QWEN_MODEL", "qwen2.5-vl-7b-instruct")

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

def call_will(message: str, media_type: str = "conversation", media_url: str = "") -> dict:
    try:
        r = httpx.post(f"{BASE_URL}/test/chat",
                       params={"message": message, "media_type": media_type, "media_url": media_url}, timeout=90)
        r.raise_for_status()
        return r.json()
    except Exception as e:
        return {"error": str(e), "response": "", "intent": "?"}


def normalize_service(service: str | None) -> str | None:
    if service == "hygienizacao":
        return "higienizacao"
    return service


def sales_cache_key(service: str | None, text: str) -> str:
    import hashlib
    normalized = " ".join(text.lower().strip().split())
    digest = hashlib.sha256(normalized.encode("utf-8")).hexdigest()[:24]
    return f"sales_reply:v1:{service or 'none'}:{digest}"


def cache_validated_reply(lead_msg: str, servico: str, response: str, score: float) -> None:
    if score < float(os.getenv("VALIDATED_REPLY_MIN_SCORE", "9.0")):
        return
    try:
        import redis
        redis_url = os.getenv("REDIS_URL", "redis://localhost:6379")
        ttl = int(os.getenv("SALES_CACHE_TTL_SECONDS", "2592000"))
        client = redis.Redis.from_url(redis_url, decode_responses=True)
        client.set(sales_cache_key(normalize_service(servico), lead_msg), response, ex=ttl)
        client.close()
        print(c(GR, "  ✓ Resposta 9+ cacheada no Redis"))
    except Exception as e:
        print(c(YL, f"  Redis cache ignorado ({e})"))


def upsert_validated_reply_qdrant(lead_msg: str, servico: str, ideal: str) -> None:
    """Insere resposta ideal no Qdrant como memória comercial recuperável."""
    try:
        import hashlib
        from fastembed import TextEmbedding
        from qdrant_client import QdrantClient
        from qdrant_client.http import models

        collection = os.getenv("QDRANT_COLLECTION", "hermes_hvac_rag_service_staging")
        qdrant_url = os.getenv("QDRANT_URL", "http://127.0.0.1:6333")
        text = f"Lead: {lead_msg}\nResposta validada do Will: {ideal}"
        vector = next(TextEmbedding(model="nomic-ai/nomic-embed-text-v1.5", max_length=512).embed([text]))
        digest = hashlib.sha256(f"{servico}:{lead_msg}".encode("utf-8")).hexdigest()
        point_id = f"{digest[:8]}-{digest[8:12]}-{digest[12:16]}-{digest[16:20]}-{digest[20:32]}"

        QdrantClient(url=qdrant_url).upsert(
            collection_name=collection,
            points=[
                models.PointStruct(
                    id=point_id,
                    vector=vector.tolist(),
                    payload={
                        "service_name": normalize_service(servico),
                        "outcome": "validated_reply",
                        "doc_type": "validated_reply",
                        "priority": 1,
                        "source": "refinar_llm.py",
                        "title": f"Resposta validada: {lead_msg[:60]}",
                        "text": text,
                    },
                )
            ],
        )
        print(c(GR, "  ✓ Resposta ideal adicionada ao Qdrant"))
    except Exception as e:
        print(c(YL, f"  Qdrant validated_reply ignorado ({e})"))


# ── LLM Juiz e Schema ────────────────────────────────────────────────────────

class ScoreAvaliacao(BaseModel):
    score: float = Field(description="Nota de 0.0 a 10.0")
    falhas: list[str] = Field(description="Lista de falhas encontradas na resposta (max 2)")
    ideal: str = Field(description="A resposta exata que o Will deveria ter enviado")
    nivel: int = Field(description="1=WILL_SYSTEM_PROMPT, 2=RAG Qdrant, 3=SCORE_MAP keywords")
    regra: str = Field(description="Se nivel==1: regra ou exemplo a adicionar ao prompt")

def call_judge(messages: list[dict], system: str) -> ScoreAvaliacao:
    """Usa OpenAI com Structured Outputs para garantir o retorno via Groq ou Qwen Local."""
    payload_msgs = [{"role": "system", "content": system}] + messages
    
    def _do_call(base_url, key, model):
        client = OpenAI(base_url=base_url, api_key=key)
        response = client.chat.completions.create(
            model=model,
            messages=payload_msgs,
            response_format={"type": "json_object"},
            temperature=0.2,
        )
        content = response.choices[0].message.content
        if content.startswith("```json"):
            content = content.replace("```json", "", 1).replace("```", "").strip()
        return ScoreAvaliacao.model_validate_json(content)

    try:
        return _do_call(LOCAL_QWEN_BASE_URL, "sk-local", LOCAL_QWEN_MODEL)
    except Exception as e:
        print(c(YL, f"  Erro no LLM Juiz (Qwen): {e}"))
        return ScoreAvaliacao(score=0.0, falhas=[str(e)], ideal="", nivel=1, regra="")

# ── Sistema do juiz ───────────────────────────────────────────────────────────

def build_judge_system(playbook: str) -> str:
    return f"""Você é um especialista em vendas B2C de serviços de climatização no Brasil,
com foco no Guarujá e atendimento regional para Santos, São Vicente e Praia Grande.

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
5. MULTIMODAL/VISÃO: Se o cliente relatou defeito físico, o Will pediu foto proativamente? Se o cliente enviou foto, o Will avaliou a imagem?
6. CONCISÃO PARA ÁUDIO: O texto é direto o suficiente para virar um áudio de TTS curto sem parecer que está lendo uma bula? Evita listas e formatações markdown?

Responda usando o schema JSON estruturado e garanta que o output seja um JSON válido."""


# ── Cenários ──────────────────────────────────────────────────────────────────

CENARIOS_BASE = [
    # Instalação
    ("Quanto custa pra instalar ar condicionado?", "instalacao"),
    ("Quero instalar um split de 12000 BTU na sala. Fico em Santos.", "instalacao"),
    ("Vocês instalam equipamento que eu já comprei na loja?", "instalacao"),
    ("Faz instalação em apartamento no 5° andar?", "instalacao"),
    ("Tenho 3 quartos pra instalar, como funciona?", "instalacao"),
    # Higienização
    ("Meu ar tá com cheiro ruim quando liga.", "higienizacao"),
    ("Qual a diferença de limpeza e higienização?", "higienizacao"),
    ("Faz higienização com ozônio? Tenho criança em casa.", "higienizacao"),
    ("Quanto custa pra higienizar um split?", "higienizacao"),
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


class CenarioDeTeste(BaseModel):
    msg: str = Field(description="Mensagem do lead, pode simular anexo tipo [IMG:url]")
    servico: str = Field(description="instalacao|higienizacao|manutencao|pmoc|onboarding")

class ListaCenarios(BaseModel):
    cenarios: list[CenarioDeTeste]

def gerar_cenarios_com_llm(playbook: str, n: int = 10) -> list[tuple[str, str]]:
    """Gera cenários novos e difíceis usando o LLM juiz."""
    system = f"""Você é um gerador de cenários de teste para um bot de vendas HVAC.
PLAYBOOK:
{playbook}

Gere {n} mensagens DIFÍCEIS que um lead real mandaria no WhatsApp — situações
que um bot genérico erraria: objeções de preço, comparação com concorrente,
perguntas ambíguas, envio de fotos (use [IMG:url] para simular a foto),
linguagem informal extrema.

Você deve responder com um JSON válido correspondente ao schema solicitado."""
    payload = [{"role": "system", "content": system}, {"role": "user", "content": "Gera os cenários."}]
    
    def _do_call(base_url, key, model):
        client = OpenAI(base_url=base_url, api_key=key)
        response = client.chat.completions.create(
            model=model,
            messages=payload,
            response_format={"type": "json_object"},
            temperature=0.7,
        )
        content = response.choices[0].message.content
        if content.startswith("```json"):
            content = content.replace("```json", "", 1).replace("```", "").strip()
        data = ListaCenarios.model_validate_json(content)
        return [(c.msg, normalize_service(c.servico) or "?") for c in data.cenarios]

    try:
        return _do_call(LOCAL_QWEN_BASE_URL, "sk-local", LOCAL_QWEN_MODEL)
    except Exception as e:
        print(c(YL, f"  Geração de cenários Qwen falhou ({e}), usando base"))
        return []


def carregar_cenarios_postgres(limit: int = 20) -> list[tuple[str, str]]:
    """Extrai conversas reais salvas como cenários de refinamento."""
    if not os.getenv("DATABASE_URL"):
        return []
    try:
        import asyncio
        from prisma import Prisma

        async def _load() -> list[tuple[str, str]]:
            db = Prisma()
            await db.connect()
            try:
                rows = await db.query_raw(
                    """
                    SELECT message, COALESCE(service, intent, 'onboarding') AS service
                    FROM interactions
                    WHERE message IS NOT NULL
                      AND length(message) BETWEEN 3 AND 500
                    ORDER BY created_at DESC
                    LIMIT $1
                    """,
                    limit,
                )
                result = []
                for row in rows:
                    msg = row.get("message")
                    service = normalize_service(row.get("service")) or "onboarding"
                    if msg:
                        result.append((msg, service))
                return result
            finally:
                await db.disconnect()

        return asyncio.run(_load())
    except Exception as e:
        print(c(YL, f"  PostgreSQL cenários ignorados ({e})"))
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
    
    media_type = "conversation"
    media_url = ""
    clean_msg = lead_msg
    
    if lead_msg.startswith("[IMG:"):
        import re as re_local
        m = re_local.match(r"\[IMG:(.+?)\]\s*(.*)", lead_msg)
        if m:
            media_type = "imageMessage"
            media_url = m.group(1).strip()
            clean_msg = m.group(2).strip()
    elif lead_msg.startswith("[AUDIO]"):
        media_type = "audioMessage"
        clean_msg = lead_msg.replace("[AUDIO]", "").strip()

    data = call_will(clean_msg, media_type, media_url)
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
        resultado = call_judge([{"role": "user", "content": prompt}], system)
    except Exception as e:
        print(c(RD, f"  ✗ Juiz falhou: {e}"))
        return 0.0

    score  = resultado.score
    falhas = resultado.falhas
    ideal  = resultado.ideal
    nivel  = resultado.nivel
    regra  = resultado.regra

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
    if score >= float(os.getenv("VALIDATED_REPLY_MIN_SCORE", "9.0")):
        cache_validated_reply(lead_msg, servico, will_resp, score)

    if score < SCORE_META and ideal and aplicar:
        upsert_validated_reply_qdrant(lead_msg, servico, ideal)
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
    juiz = "Groq 70b-versatile" if os.getenv("GROQ_API_KEY") else f"Qwen local ({LOCAL_QWEN_MODEL})"
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
    reais = carregar_cenarios_postgres(limit=20)
    if reais:
        cenarios = reais + cenarios
        print(c(GR, f"  +{len(reais)} cenários reais do PostgreSQL\n"))
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
