from __future__ import annotations

import os
import json
import logging
import httpx
from typing import Any

from langchain_core.messages import HumanMessage, AIMessage, BaseMessage

logger = logging.getLogger(__name__)

# ──────────────────────────────────────────────────────────────────────────────
# System prompt — voz do Will (Refrimix, São Vicente/SP)
# Injeta persona forte antes de qualquer geração para ancorar pt-BR e estilo
# ──────────────────────────────────────────────────────────────────────────────

WILL_SYSTEM_PROMPT = """Você é o Will, dono da Refrimix Tecnologia em São Vicente/SP.
Atende leads no WhatsApp como um atendente humano — conduz o onboarding de forma natural, coleta informações progressivamente, nunca repete o que já foi dito.

REGRAS ABSOLUTAS:
- Responda SEMPRE em português brasileiro coloquial. NUNCA em outro idioma.
- PROIBIDO usar caracteres chineses, japoneses, coreanos, árabes, cirílicos ou hebraicos.
- Escreva como quem está no WhatsApp: frases curtas, sem firula, sem listas com bullet points.
- Não use "prezado cliente", "conforme solicitado" ou linguagem de e-mail corporativo.
- Use "a gente" em vez de "nós". Use "pra", "pro", "tá", "tô" quando natural.
- NUNCA repita informação que já foi dada no histórico da conversa.
- Leia o histórico ANTES de responder — proibido fazer perguntas que já foram respondidas.
- Cada mensagem deve avançar a conversa: coletar mais dados ou propor próximo passo.

FLUXO DE ONBOARDING (siga esta ordem naturalmente):
1. Primeira mensagem → cumprimente e pergunte o que precisam (ex: "Oi! Sou o Will da Refrimix. Como posso te ajudar?")
2. Identificado o serviço → aprofunde o problema (marca, modelo, endereço geral)
3. Problema claro → proponha visita técnica gratuita e peça endereço completo
4. Endereço recebido → confirme e sugira janela de horário

EXEMPLOS DE TOM CORRETO:
Lead: "Oi"
Will: "Oi! Sou o Will da Refrimix. Trabalhamos com instalação, manutenção e PMOC de ar condicionado na Baixada Santista. Como posso te ajudar?"

Lead: "O ar tá fazendo barulho"
Will: "Barulho quase sempre é suporte do compressor com folga. Qual a marca e onde fica o aparelho?"

Lead: [depois de já informar a marca] "É um Springer Midea"
Will: "Ok. E o barulho é mais de vibração, batida ou chiado? Isso me ajuda a já ir preparado."

Lead: "Preciso de PMOC"
Will: "Pra qual tipo de estabelecimento e quantos equipamentos? Com isso já monto o orçamento."

Serviços da Refrimix: instalação, manutenção corretiva, PMOC, consultoria, higienização, projeto central.
Região de atendimento: Baixada Santista (São Vicente, Santos, Praia Grande, Guarujá e região).

# EXEMPLOS_VALIDADOS_START
# Exemplos validados pelo Will — adicionados via refinar.py:

Lead: "Oi"
Will: "Ei! Sou o Will da Refrimix — a gente cuida do seu ar aqui na Baixada. O que tá precisando?"
# EXEMPLOS_VALIDADOS_END
"""


# ──────────────────────────────────────────────────────────────────────────────
# LLM Helpers
# ──────────────────────────────────────────────────────────────────────────────

import re as _re

def _strip_thinking_tags(text: str) -> str:
    """Remove blocos <think>...</think> de modelos de raciocínio (MiniMax M2.x, DeepSeek-R1, etc)."""
    text = _re.sub(r"<think>.*?</think>", "", text, flags=_re.DOTALL)
    return text.strip()


async def _call_minimax(messages: list[dict[str, str]], max_retries: int = 2) -> str:
    api_key = os.getenv("MINIMAX_API_KEY", "")
    base_url = os.getenv("MINIMAX_BASE_URL", "https://api.minimax.io/v1")
    model = os.getenv("MINIMAX_MODEL", "MiniMax-M2.7")

    if not api_key:
        raise RuntimeError("MINIMAX_API_KEY não configurado")

    last_error: Exception | None = None
    for attempt in range(max_retries):
        try:
            async with httpx.AsyncClient(timeout=90.0) as client:
                resp = await client.post(
                    f"{base_url}/chat/completions",
                    headers={
                        "Authorization": f"Bearer {api_key}",
                        "Content-Type": "application/json",
                    },
                    json={"model": model, "messages": messages, "max_tokens": 400},
                )
                resp.raise_for_status()
                data = resp.json()
                if "error" in data:
                    raise RuntimeError(f"MiniMax error: {data['error']}")
                if not data.get("choices"):
                    raise RuntimeError(f"MiniMax sem choices: {data}")
                raw = data["choices"][0]["message"]["content"]
                return _strip_thinking_tags(raw)
        except Exception as exc:
            last_error = exc
            if attempt < max_retries - 1:
                import asyncio
                await asyncio.sleep(2 ** attempt)
    raise RuntimeError(f"MiniMax falhou após {max_retries} tentativas: {last_error}")


async def _call_groq(messages: list[dict[str, str]], max_retries: int = 2, model_override: str | None = None) -> str:
    api_key = os.getenv("GROQ_API_KEY", "")
    base_url = os.getenv("GROQ_BASE_URL", "https://api.groq.com/openai/v1")
    model = model_override or os.getenv("GROQ_FALLBACK_MODEL", os.getenv("GROQ_MODEL", "llama-3.1-8b-instant"))

    if not api_key:
        raise RuntimeError("GROQ_API_KEY não configurado")

    last_error: Exception | None = None
    for attempt in range(max_retries):
        try:
            async with httpx.AsyncClient(timeout=60.0) as client:
                resp = await client.post(
                    f"{base_url}/chat/completions",
                    headers={
                        "Authorization": f"Bearer {api_key}",
                        "Content-Type": "application/json",
                    },
                    json={"model": model, "messages": messages, "max_tokens": 512},
                )
                resp.raise_for_status()
                data = resp.json()
                if "error" in data:
                    raise RuntimeError(f"Groq error: {data['error']}")
                if not data.get("choices"):
                    raise RuntimeError(f"Groq sem choices: {data}")
                return data["choices"][0]["message"]["content"]
        except Exception as exc:
            last_error = exc
            if attempt < max_retries - 1:
                import asyncio
                await asyncio.sleep(2 ** attempt)
    raise RuntimeError(f"Groq falhou após {max_retries} tentativas: {last_error}")


async def llm_chat(messages: list[dict[str, str]], max_retries: int = 2) -> str:
    """MiniMax principal, Groq como fallback automático."""
    minimax_key = os.getenv("MINIMAX_API_KEY", "")
    if minimax_key:
        try:
            return await _call_minimax(messages, max_retries)
        except Exception as e:
            logger.warning(f"MiniMax falhou, usando Groq: {e}")

    return await _call_groq(messages, max_retries)


async def groq_repair(prompt: str) -> str:
    """Groq dedicado para repair de language guard — sempre Llama 70B."""
    return await _call_groq(
        [
            {"role": "system", "content": "Você é um tradutor/reescritor para português brasileiro."},
            {"role": "user", "content": prompt},
        ],
        max_retries=1,
    )


# ──────────────────────────────────────────────────────────────────────────────
# Redis Helper
# ──────────────────────────────────────────────────────────────────────────────

async def redis_get(key: str) -> str | None:
    import redis.asyncio
    redis_url = os.getenv("REDIS_URL", "redis://localhost:6379")
    client = redis.asyncio.from_url(redis_url, decode_responses=True)
    try:
        return await client.get(key)
    finally:
        await client.aclose()


async def redis_set(key: str, value: str, ex: int | None = None) -> None:
    import redis.asyncio
    redis_url = os.getenv("REDIS_URL", "redis://localhost:6379")
    client = redis.asyncio.from_url(redis_url, decode_responses=True)
    try:
        await client.set(key, value, ex=ex)
    finally:
        await client.aclose()


# ──────────────────────────────────────────────────────────────────────────────
# Qdrant Helper
# ──────────────────────────────────────────────────────────────────────────────

def qdrant_search(query: str, service_name: str | None, top_k: int = 5) -> list[dict[str, Any]]:
    from qdrant_client import QdrantClient
    from fastembed import TextEmbedding

    qdrant_url = os.getenv("QDRANT_URL", "http://localhost:6333")
    collection = os.getenv("QDRANT_COLLECTION", "whatsapp_rag")
    client = QdrantClient(url=qdrant_url)

    try:
        model = TextEmbedding(
            model="sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2",
            max_length=256,
        )
        query_embedding = next(model.embed([query]))
    except Exception:
        return []

    from qdrant_client.models import Filter, FieldCondition, MatchValue

    filter_conditions = None
    if service_name:
        filter_conditions = Filter(
            must=[FieldCondition(key="service_name", match=MatchValue(value=service_name))]
        )

    results = client.query_points(
        collection_name=collection,
        query=query_embedding.tolist(),
        limit=top_k,
        query_filter=filter_conditions,
        with_payload=True,
        with_vectors=False,
    )
    return [{"id": r.id, "score": r.score, "payload": r.payload} for r in results.points]


# ──────────────────────────────────────────────────────────────────────────────
# Prisma Helper
# ──────────────────────────────────────────────────────────────────────────────

async def prisma_save_interaction(data: dict[str, Any]) -> None:
    from prisma import Prisma
    prisma = Prisma()
    await prisma.connect()
    try:
        await prisma.interaction.create(data={
            "phone": data.get("phone", "unknown"),
            "message": data.get("user_message", ""),
            "intent": data.get("intent"),
            "service": data.get("service"),
            "response": data.get("ai_message", ""),
            "is_human": data.get("is_human", False),
        })
    finally:
        await prisma.disconnect()


# ──────────────────────────────────────────────────────────────────────────────
# LangGraph Nodes
# ──────────────────────────────────────────────────────────────────────────────

# Mapa de outcomes por serviço — drive comercial
_OUTCOME_MAP: dict[str, str] = {
    "instalacao":      "analise_tecnica",
    "manutencao":      "analise_tecnica",
    "pmoc":            "analise_tecnica",
    "consultoria":     "reuniao_projeto",
    "hygienizacao":    "higienizacao_preventiva",
    "projeto-central": "reuniao_projeto",
}


async def classify_service(state: dict[str, Any]) -> dict[str, Any]:
    """Classifica intent do lead entre 6 serviços Refrimix + outcome comercial."""
    messages = state.get("messages", [])
    if not messages:
        return {"intent": None, "service": None, "outcome": None}

    last_message = messages[-1]
    user_text = last_message.content if hasattr(last_message, "content") else str(last_message)
    text_lower = user_text.lower()

    # Triggers para escalar humano imediatamente
    HUMAN_TRIGGERS = [
        "atendente humano", "falar com pessoa", "falar com atendente", "pessoa real",
        "ninguém responde", "não retornaram", "cancelamento",
        "reembolso", "refund", "devolução", "liguei várias vezes",
    ]
    if any(t in text_lower for t in HUMAN_TRIGGERS):
        return {"intent": "human", "service": None, "outcome": "escalar_humano", "messages": messages}

    # Saudações e mensagens curtas sem serviço → onboarding (não escalar humano)
    GREETING_WORDS = [
        "oi", "olá", "ola", "bom dia", "boa tarde", "boa noite",
        "e aí", "eai", "e ai", "tudo bem", "tudo bom", "como vai",
        "alguém", "alguem", "tem alguém", "quero informação", "quero informacao",
    ]
    if any(g in text_lower for g in GREETING_WORDS) and len(text_lower.split()) <= 8:
        return {"intent": "onboarding", "service": None, "outcome": "onboarding", "messages": messages}

    # Scoring por keywords
    SCORE_MAP: dict[tuple[str, int], str] = {
        ("vocês instalam", 6): "instalacao",
        ("instalação de", 3): "instalacao",
        ("instalar", 1): "instalacao",
        ("instalação", 1): "instalacao",
        ("split", 2): "instalacao",
        ("equipamento que eu já comprei", 5): "instalacao",
        ("não esquenta", 5): "manutencao",
        ("não aquece", 5): "manutencao",
        ("barulho de vibração", 5): "manutencao",
        ("barulho", 3): "manutencao",
        ("vazamento", 4): "manutencao",
        ("não liga", 4): "manutencao",
        ("queimou", 3): "manutencao",
        ("corretiva", 3): "manutencao",
        ("gela demais", 3): "manutencao",
        ("manutenção", 1): "manutencao",
        ("consertar", 1): "manutencao",
        ("defeito", 1): "manutencao",
        ("pmoc", 5): "pmoc",
        ("laudo pmoc", 5): "pmoc",
        ("manutenção preventiva", 2): "pmoc",
        ("alvará do bombeiros", 4): "pmoc",
        ("higienização", 5): "hygienizacao",
        ("higienizacao", 5): "hygienizacao",
        ("ozônio", 4): "hygienizacao",
        ("ácaros", 4): "hygienizacao",
        ("fungos", 3): "hygienizacao",
        ("sanitização", 3): "hygienizacao",
        ("limpeza do ar", 3): "hygienizacao",
        ("cheiro", 1): "hygienizacao",
        ("projeto de climatização", 4): "consultoria",
        ("projeto de ar", 4): "consultoria",
        ("consultoria", 3): "consultoria",
        ("assessoria", 3): "consultoria",
        ("btu", 3): "consultoria",
        ("dimensionamento", 3): "consultoria",
        ("obra nova", 4): "consultoria",
        ("eficiência energética", 4): "consultoria",
        ("eficiencia energetica", 4): "consultoria",
        ("o que é melhor", 3): "consultoria",
        ("qual capacidade", 3): "consultoria",
        ("melhor para", 2): "consultoria",
        ("projeto central", 5): "projeto-central",
        ("central de climatização", 6): "projeto-central",
        ("multi split", 4): "projeto-central",
        ("multisplit", 4): "projeto-central",
        ("cassete", 2): "projeto-central",
        ("galpão", 3): "projeto-central",
        ("restaurante", 3): "projeto-central",
        ("para climatização", 2): "projeto-central",
        ("sistema central", 5): "projeto-central",
        ("controle individual", 4): "projeto-central",
        ("carga térmica", 4): "projeto-central",
        ("carga termica", 4): "projeto-central",
        ("6 ambientes", 4): "projeto-central",
        ("vários ambientes", 4): "projeto-central",
    }

    scores: dict[str, int] = {}
    for (keyword, weight), svc in SCORE_MAP.items():
        if keyword in text_lower:
            scores[svc] = scores.get(svc, 0) + weight

    intent = max(scores, key=lambda k: scores[k]) if scores else None
    sorted_scores = sorted(scores.values(), reverse=True) if scores else []
    top_score = sorted_scores[0] if sorted_scores else 0
    runner_up = sorted_scores[1] if len(sorted_scores) > 1 else 0

    # LLM override: sempre consulta (para zero-score ou ambiguidade) — usa 70b para mais precisão
    CLASSIFY_MODEL = os.getenv("GROQ_CLASSIFY_MODEL", "llama-3.3-70b-versatile")
    try:
        prompt = (
            f"Classifique a mensagem do cliente entre: "
            f"instalacao, consultoria, manutencao, pmoc, projeto-central, hygienizacao, human\n"
            f"'instalacao' = instalar aparelho novo\n"
            f"'manutencao' = consertar/reparar aparelho existente\n"
            f"'pmoc' = plano preventivo obrigatório/laudo técnico\n"
            f"'consultoria' = dúvida técnica, assessoria, qual equipamento escolher, projeto de obra\n"
            f"'projeto-central' = sistema central, multisplit, vários ambientes, carga térmica\n"
            f"'hygienizacao' = limpeza, higienização, cheiro, ácaros\n"
            f"'human' = pede atendente, reclamação, cancelamento ou completamente fora dos serviços\n"
            f"Mensagem: \"{user_text}\"\n"
            f"Responda apenas o nome da categoria, sem explicação."
        )
        resp = await _call_groq([{"role": "user", "content": prompt}], model_override=CLASSIFY_MODEL)
        intent_llm = resp.strip().lower().replace(" ", "-")
        VALID = {"instalacao", "consultoria", "manutencao", "pmoc", "projeto-central", "hygienizacao", "human"}
        if intent_llm in VALID:
            if not scores:
                # Sem keyword match — confia no LLM
                intent = intent_llm
            else:
                strong_keyword = top_score >= 4 and (runner_up == 0 or top_score > runner_up * 2)
                if not strong_keyword:
                    intent = intent_llm
    except Exception as e:
        logger.warning(f"LLM classify falhou, mantendo keyword: {e}")

    # Se intent ainda None (sem keywords e LLM falhou) → escala humano
    if intent is None:
        return {"intent": "human", "service": None, "outcome": "duvida", "messages": messages}

    service = None if intent == "human" else intent
    outcome = _OUTCOME_MAP.get(intent, "duvida") if intent != "human" else "escalar_humano"

    return {"intent": intent, "service": service, "outcome": outcome, "messages": messages}


async def retrieve_knowledge(state: dict[str, Any]) -> dict[str, Any]:
    """Busca contexto RAG no Qdrant com FastEmbed."""
    messages = state.get("messages", [])
    service = state.get("service")

    if not messages:
        return {"rag_context": [], "messages": messages}

    last_message = messages[-1]
    user_text = last_message.content if hasattr(last_message, "content") else str(last_message)

    try:
        rag_context = qdrant_search(user_text, service_name=service, top_k=3)
    except Exception as e:
        logger.warning(f"Qdrant search falhou: {e}")
        rag_context = []

    return {"rag_context": rag_context, "service": service, "messages": messages}


async def generate_response(state: dict[str, Any]) -> dict[str, Any]:
    """Gera resposta na voz do Will usando RAG + MiniMax (Groq fallback)."""
    messages = state.get("messages", [])
    rag_context = state.get("rag_context", [])
    service = state.get("service")
    intent = state.get("intent")
    outcome = state.get("outcome", "duvida")
    customer_data = state.get("customer_data", {})

    if not messages:
        return {"messages": messages}

    last_message = messages[-1]
    user_text = last_message.content if hasattr(last_message, "content") else str(last_message)

    context_str = "\n---\n".join(
        ctx["payload"].get("text", "")
        for ctx in rag_context
        if ctx.get("payload", {}).get("text")
    ) or ""

    # CTA por outcome — guia o Will a conduzir o lead pro próximo passo certo
    outcome_cta = {
        "onboarding":              "Primeira mensagem. Cumprimente, se apresente como Will da Refrimix e pergunte o que precisam. Máximo 2 linhas.",
        "analise_tecnica":         "Finalize sugerindo agendar visita técnica gratuita e pedindo o endereço.",
        "higienizacao_preventiva": "Finalize propondo agendar a higienização e perguntando quantos aparelhos são.",
        "reuniao_projeto":         "Finalize propondo marcar uma reunião técnica sem compromisso.",
        "duvida":                  "Responda a dúvida e pergunte se pode ajudar com mais alguma coisa.",
        "escalar_humano":          "Informe que um especialista vai entrar em contato em breve.",
    }.get(outcome, "Avance a conversa com uma pergunta que qualifique o lead.")

    # ── Monta multi-turn com histórico de conversa ────────────────────────────
    # system + histórico alternado (user/assistant) + última mensagem com contexto RAG
    llm_messages: list[dict[str, str]] = [
        {"role": "system", "content": WILL_SYSTEM_PROMPT},
    ]

    # Adiciona histórico (todas as mensagens exceto a última — que vira user_prompt abaixo)
    for msg in messages[:-1]:
        if isinstance(msg, HumanMessage):
            llm_messages.append({"role": "user", "content": msg.content})
        elif isinstance(msg, AIMessage):
            llm_messages.append({"role": "assistant", "content": msg.content})

    # Última mensagem do lead enriquecida com contexto RAG e CTA
    user_prompt = (
        f"Serviço identificado: {service or 'não classificado'}\n"
        f"Contexto da Refrimix:\n{context_str or 'Use seu conhecimento sobre climatização HVAC.'}\n\n"
        f"Mensagem do lead: {user_text}\n\n"
        f"Instruções: {outcome_cta}\n"
        f"IMPORTANTE: leia o histórico acima antes de responder — não repita perguntas já feitas."
    )
    llm_messages.append({"role": "user", "content": user_prompt})

    try:
        # Groq para intents simples (onboarding, atendimento, manutenção, instalação, higienização)
        # MiniMax só para intents que exigem raciocínio técnico profundo (pmoc, consultoria, projeto-central)
        MINIMAX_INTENTS = {"pmoc", "consultoria", "projeto-central"}
        if intent not in MINIMAX_INTENTS:
            response = await _call_groq(llm_messages)
        else:
            response = await llm_chat(llm_messages)
    except Exception as e:
        logger.warning(f"LLM falhou em generate_response: {e}")
        # Fallback de template por outcome
        response = {
            "analise_tecnica": (
                "Pode deixar que a gente resolve! "
                "Me manda o endereço e os detalhes do equipamento que eu já marco a visita técnica — é gratuita."
            ),
            "higienizacao_preventiva": (
                "Ótimo! A higienização é fundamental pra qualidade do ar. "
                "Me fala quantos aparelhos são e o endereço que eu já orçamento."
            ),
            "reuniao_projeto": (
                "Pra esse tipo de projeto, melhor a gente sentar e conversar com a planta em mãos. "
                "Posso marcar uma reunião técnica sem compromisso — qual a melhor data pra você?"
            ),
        }.get(outcome or "", "Me manda mais detalhes que eu te ajudo!")

    ai_message = AIMessage(content=response)
    return {"messages": messages + [ai_message], "rag_context": rag_context, "service": service, "outcome": outcome}


async def language_guard_check(state: dict[str, Any]) -> dict[str, Any]:
    """Valida e corrige resposta do LLM — garante pt-BR sem drift CJK/árabe."""
    messages = state.get("messages", [])
    if not messages:
        return {"messages": messages}

    last_message = messages[-1]
    if not hasattr(last_message, "content"):
        return {"messages": messages}

    ai_response = last_message.content
    rag_context = state.get("rag_context", [])
    service = state.get("service", "não classificado")
    outcome = state.get("outcome", "duvida")

    context_str = "\n".join(
        ctx["payload"].get("text", "")
        for ctx in rag_context
        if ctx.get("payload", {}).get("text")
    ) or "Sem contexto."

    user_text = next(
        (m.content for m in messages if isinstance(m, HumanMessage)),
        "",
    )

    original_prompt = (
        f"Serviço: {service}\n"
        f"Contexto: {context_str}\n"
        f"Mensagem do lead: {user_text}\n"
        f"Responda em português brasileiro coloquial como o Will da Refrimix."
    )

    from agent_graph.guards.language_guard import LanguageGuard

    guard = LanguageGuard(expected_lang="pt-BR", majority_threshold=0.50, max_retries=2)
    intent = state.get("intent")
    MINIMAX_INTENTS = {"pmoc", "consultoria", "projeto-central"}

    async def retry_llm(prompt: str) -> str:
        llm_caller = llm_chat if intent in MINIMAX_INTENTS else _call_groq
        return await llm_caller([
            {"role": "system", "content": WILL_SYSTEM_PROMPT},
            {"role": "user", "content": prompt},
        ])

    fixed_response = await guard.validate_and_fix(
        ai_response,
        retry_llm,
        original_prompt,
        groq_repair_callable=groq_repair,
    )

    return {"messages": messages[:-1] + [AIMessage(content=fixed_response)]}


async def format_whatsapp(state: dict[str, Any]) -> dict[str, Any]:
    """
    Formata resposta para WhatsApp: remove markdown pesado, quebra textos longos,
    e retorna o AIMessage atualizado nos messages.
    """
    messages = state.get("messages", [])
    if not messages:
        return {"messages": messages}

    last_message = messages[-1]
    if not hasattr(last_message, "content"):
        return {"messages": messages}

    raw = last_message.content

    # Remove markdown que não renderiza bem no WhatsApp
    formatted = raw
    formatted = formatted.replace("**", "*")   # bold MD → WhatsApp bold
    formatted = formatted.replace("__", "_")    # italic
    # Remove headers markdown
    import re
    formatted = re.sub(r"^#{1,6}\s+", "", formatted, flags=re.MULTILINE)
    # Normaliza múltiplas linhas em branco
    formatted = re.sub(r"\n{3,}", "\n\n", formatted)
    formatted = formatted.strip()

    # Se muito longo (>1500 chars), trunca com gancho
    if len(formatted) > 1500:
        formatted = formatted[:1450].rsplit("\n", 1)[0] + (
            "\n\nPosso te passar mais detalhes. Qual a sua dúvida principal?"
        )

    return {"messages": messages[:-1] + [AIMessage(content=formatted)]}


async def save_interaction(state: dict[str, Any]) -> dict[str, Any]:
    """Persiste interação no PostgreSQL via Prisma."""
    messages = state.get("messages", [])
    intent = state.get("intent")
    service = state.get("service")
    outcome = state.get("outcome")
    customer_data = state.get("customer_data", {})

    user_message = next((m.content for m in messages if isinstance(m, HumanMessage)), None)
    ai_message = next((m.content for m in reversed(messages) if isinstance(m, AIMessage)), None)

    try:
        await prisma_save_interaction({
            "phone": customer_data.get("phone", "unknown"),
            "user_message": user_message or "",
            "intent": intent,
            "service": service,
            "ai_message": ai_message or "",
            "is_human": state.get("is_human", False),
        })
    except Exception as e:
        logger.error(f"Falha ao salvar interação: {e}")

    return {"messages": messages}


async def route_human(state: dict[str, Any]) -> dict[str, Any]:
    """Escalada para humano — skipa RAG e responde com mensagem de passagem."""
    messages = state.get("messages", [])
    handoff = AIMessage(
        content=(
            "Entendido! Vou te passar pra um dos nossos especialistas agora. "
            "Aguarda um instante que alguém entra em contato contigo em breve. 🙂"
        )
    )
    return {
        "messages": messages + [handoff],
        "is_human": True,
    }


# ──────────────────────────────────────────────────────────────────────────────
# Tarefa 3 — preprocess_input (STT + Vision)
# ──────────────────────────────────────────────────────────────────────────────

async def preprocess_input(state: dict[str, Any]) -> dict[str, Any]:
    """
    Pré-processa input multimodal antes de classify_service:
    - audioMessage → transcreve com Groq Whisper → substitui texto
    - imageMessage → analisa com Vision LLM → prepend descrição ao texto
    - conversation → passa direto
    """
    message_type = state.get("message_type", "conversation")
    media_url = state.get("media_url", "")
    instance = state.get("instance", "")
    messages = state.get("messages", [])

    if message_type == "audioMessage" and media_url:
        try:
            from agent_graph.services.stt import transcribe_audio
            transcript = await transcribe_audio(media_url, instance or None)
            logger.info(f"STT transcript: {transcript[:80]!r}")
            # Substitui última HumanMessage pelo texto transcrito
            new_messages = list(messages)
            if new_messages and isinstance(new_messages[-1], HumanMessage):
                new_messages[-1] = HumanMessage(content=transcript)
            else:
                new_messages.append(HumanMessage(content=transcript))
            return {"messages": new_messages, "message_type": message_type}
        except Exception as e:
            logger.error(f"STT falhou: {e}")
            # Mantém o estado sem alterar mensagens

    elif message_type == "imageMessage" and media_url:
        try:
            from agent_graph.services.vision import analyze_image
            # Caption já pode estar como última HumanMessage
            caption = ""
            if messages and isinstance(messages[-1], HumanMessage):
                caption = messages[-1].content or ""
            description = await analyze_image(media_url, caption, instance or None)
            logger.info(f"Vision description: {description[:80]!r}")
            # Prepend descrição ao texto do usuário
            combined = f"[Imagem: {description}]"
            if caption:
                combined = f"[Imagem: {description}]\n{caption}"
            new_messages = list(messages)
            if new_messages and isinstance(new_messages[-1], HumanMessage):
                new_messages[-1] = HumanMessage(content=combined)
            else:
                new_messages.append(HumanMessage(content=combined))
            return {"messages": new_messages, "message_type": message_type}
        except Exception as e:
            logger.error(f"Vision falhou: {e}")

    return {"messages": messages, "message_type": message_type}


# ──────────────────────────────────────────────────────────────────────────────
# Tarefa 5 — decide_response_modality + tts_voice_clone
# ──────────────────────────────────────────────────────────────────────────────

async def decide_response_modality(state: dict[str, Any]) -> dict[str, Any]:
    """
    Decide se a resposta vai em áudio ou texto, com base em:
    - Tipo da mensagem inbound (espelha áudio)
    - Intent (pmoc/consultoria → sempre texto)
    - Conteúdo (saudações → áudio)
    """
    from agent_graph.services.tts import should_respond_with_audio

    message_type = state.get("message_type", "conversation")
    intent = state.get("intent")
    outcome = state.get("outcome")
    messages = state.get("messages", [])

    user_text = next(
        (m.content for m in messages if isinstance(m, HumanMessage)),
        "",
    )

    use_audio = should_respond_with_audio(message_type, intent, outcome, user_text)
    modality = "audio" if use_audio else "text"
    logger.info(f"Response modality: {modality} (message_type={message_type}, intent={intent})")

    return {"response_modality": modality}


async def tts_voice_clone(state: dict[str, Any]) -> dict[str, Any]:
    """
    Se modality == 'audio', sintetiza resposta com Coqui XTTS (voz do Will).
    Armazena audio_bytes no state para o worker enviar via Evolution API.
    """
    if state.get("response_modality") != "audio":
        return {}

    from agent_graph.services.tts import synthesize, choose_voice_style

    messages = state.get("messages", [])
    intent = state.get("intent")
    outcome = state.get("outcome")

    ai_text = next(
        (m.content for m in reversed(messages) if isinstance(m, AIMessage)),
        "",
    )

    if not ai_text:
        return {"response_modality": "text"}

    voice_style = choose_voice_style(intent, outcome)
    try:
        audio_bytes = await synthesize(ai_text, voice_style)
        if audio_bytes:
            logger.info(f"TTS OK: {len(audio_bytes)} bytes (style={voice_style})")
            return {"audio_bytes": audio_bytes}
        # XTTS indisponível — degrada para texto silenciosamente
        logger.warning("XTTS indisponível, degradando para texto")
        return {"response_modality": "text"}
    except Exception as e:
        logger.error(f"TTS falhou: {e}")
        return {"response_modality": "text"}


# ──────────────────────────────────────────────────────────────────────────────
# Tarefa 6 — dispatch_appointment_alert
# ──────────────────────────────────────────────────────────────────────────────

# Keywords que indicam intenção de agendar (extraídos da fala do lead)
_ADDRESS_PATTERNS: tuple[str, ...] = (
    "rua ", "av ", "avenida ", "bairro ", "cep ", "praia grande",
    "santos", "são vicente", "guarujá", "cubatão", "mongaguá",
    "itanhaém", "peruíbe",
)

_WINDOW_PATTERNS: tuple[str, ...] = (
    "manhã", "tarde", "noite", "segunda", "terça", "quarta",
    "quinta", "sexta", "sábado", "domingo", "amanhã", "hoje",
    "próxima semana", "semana que vem",
)


def _extract_appointment_data(messages: list, customer_data: dict, service: str | None) -> dict | None:
    """
    Extrai dados de agendamento das mensagens do lead.
    Retorna dict com {address, window} se detectar, ou None.
    """
    full_text = " ".join(
        m.content.lower() for m in messages if isinstance(m, HumanMessage) and m.content
    )

    address = next((p for p in _ADDRESS_PATTERNS if p in full_text), None)
    window = next((p for p in _WINDOW_PATTERNS if p in full_text), None)

    # Só dispara alerta se tiver pelo menos endereço OU janela
    if not address and not window:
        return None

    return {
        "phone": customer_data.get("phone", ""),
        "name": customer_data.get("name"),
        "service": service,
        "address": address,
        "window": window,
    }


async def dispatch_appointment_alert(state: dict[str, Any]) -> dict[str, Any]:
    """
    Detecta intenção de agendamento nas mensagens e, se encontrar
    endereço ou janela de horário, envia alerta WhatsApp para o dono.
    """
    outcome = state.get("outcome", "")
    service = state.get("service")
    messages = state.get("messages", [])
    customer_data = state.get("customer_data", {})

    # Só verifica outcomes que levam a visita/reunião
    if outcome not in ("analise_tecnica", "higienizacao_preventiva", "reuniao_projeto"):
        return {}

    lead_data = _extract_appointment_data(messages, customer_data, service)
    if not lead_data:
        return {}

    from agent_graph.services.alerts import send_appointment_alert, prisma_upsert_lead

    try:
        await prisma_upsert_lead(lead_data)
    except Exception as e:
        logger.error(f"Lead upsert falhou: {e}")

    try:
        await send_appointment_alert(lead_data)
    except Exception as e:
        logger.error(f"Alert dispatch falhou: {e}")

    return {}
