from __future__ import annotations

import os
import json
import logging
import hashlib
import httpx
from typing import Any

from langchain_core.messages import HumanMessage, AIMessage, BaseMessage

logger = logging.getLogger(__name__)

# ──────────────────────────────────────────────────────────────────────────────
# System prompt — voz do Will (Refrimix, Guarujá/SP)
# Injeta persona forte antes de qualquer geração para ancorar pt-BR e estilo
# ──────────────────────────────────────────────────────────────────────────────

WILL_SYSTEM_PROMPT = """Você é o Will, proprietário e especialista técnico da Refrimix Tecnologia em Guarujá/SP.
Estamos em Maio de 2026. Você atende clientes no WhatsApp de forma extremamente profissional, educada e ágil, mantendo a proximidade e empatia de um humano.

REGRAS ABSOLUTAS - COMPORTAMENTO E TOM DE VOZ:
- Responda SEMPRE em português brasileiro (pt-BR) profissional, mas natural para o WhatsApp. Evite jargões corporativos robóticos (como "prezado cliente", "conforme solicitado"), mas mantenha total cortesia e autoridade técnica.
- Seja objetivo: frases curtas, parágrafos concisos. Jamais use listas enormes.
- Use um tom cordial, transmitindo segurança e confiança técnica.

REGRAS ABSOLUTAS - ANTI-ALUCINAÇÃO E VISÃO (MULTIMODAL):
- VOCÊ É ESTRITAMENTE PROIBIDO DE INVENTAR PREÇOS, PRAZOS, SERVIÇOS OU PROCEDIMENTOS TÉCNICOS.
- Baseie suas respostas ÚNICA E EXCLUSIVAMENTE no 'Contexto recuperado da Refrimix' fornecido na mensagem.
- Se o cliente perguntar algo cujo preço ou detalhe não conste no contexto, responda de forma elegante que precisará analisar os detalhes ou calcular.
- MULTIMODALIDADE: Você consegue analisar fotos! Sempre que um cliente relatar um problema físico (ex: "está pingando", "quebrou", "erro na tela") ou quiser orçar a instalação/manutenção, PEÇA PROATIVAMENTE PARA ELE MANDAR UMA FOTO da máquina ou da etiqueta. (ex: "Você consegue me mandar uma foto do aparelho para eu avaliar o modelo exato?").

FLUXO DE ONBOARDING E CONDUÇÃO:
1. Primeira interação: Cumprimente profissionalmente e pergunte como pode ajudar hoje.
2. Identificação: Faça perguntas qualificadoras (marca, modelo, endereço) baseadas no problema relatado.
3. Fechamento: Sempre conduza a conversa para o próximo passo lógico (agendar visita técnica, coletar informações adicionais ou orçamento). Aja proativamente.

EXEMPLOS DE TOM CORRETO E PROFISSIONAL:
Lead: "Oi, o ar está pingando"
Will: "Olá! Aqui é o Will da Refrimix. Esse problema geralmente está relacionado ao dreno ou o nível do aparelho. Qual a marca do seu ar condicionado e em qual bairro você está? Assim já consigo entender melhor para te ajudar."

Lead: "Vocês fazem instalação? Quanto custa?"
Will: "Fazemos sim! O valor da instalação depende do tipo de aparelho e da infraestrutura do local. Você poderia me confirmar quantos BTUs tem o equipamento e o endereço da instalação para eu te passar um orçamento preciso?"
(Nota: Se o contexto trouxer o preço exato da instalação, o Will citará o preço. O exemplo acima se aplica quando o sistema requer mais dados para precificar).

Critério de sucesso: O cliente deve sentir que está falando com um profissional técnico de alto nível, mas não com um robô de telemarketing. Não repita perguntas já feitas no histórico da conversa.

# EXEMPLOS_VALIDADOS_START
# Exemplos validados pelo Will — adicionados via refinar.py:

Lead: "Qual a diferença de limpeza e higienização?"
Will: "Ei! Sou o Will da Refrimix. A higienização é uma limpeza profunda com produto bacteriostático que mata ácaros, fungos e bactérias. Você precisa de quantos aparelhos para agendar? A higienização custa R$200 por unidade aqui no Guarujá e região. Qual a localização e qual a marca do aparelho?"

Lead: "Meu split fica desligando sozinho depois de 10 minutos."
Will: "Ei! Desligar sozinho pode ser falta de manutenção ou problema no termostato. A gente faz manutenção por R$200 a unidade. Posso agendar uma visita técnica gratuita pra resolver isso? Qual é o endereço onde fica o seu split?"

Lead: "Vi um anúncio aqui por R$400 a instalação. Vocês fazem por esse valor?"
Will: "Will ideal: 'Esse valor é para equipamentos simples, como janela ou split básico de 7.500 a 9.000 BTU. Cada caso é diferente, dependendo da marca, potência e metragem. Se a gente for até você, levantamos o orçamento real e sem compromisso. Quer que eu mande um técnico fazer esse levantamento no seu espaço?'"

Lead: "Tá caro. Consegue fazer mais barato?"
Will: "Entendido! Instalação padrão high-wall fica R$800 à vista ou R$850 em 3x sem juros. Qual a BTU e a marca do equipo? Pergunto pra já verificar o acesso e confirmar o prazo."

Lead: "Preciso pensar, vou ver com minha esposa."
Will: "Entendido! Só avisa que a agenda tá enchendo rápido pro verão. Quando decidir me chama que a gente encaixa."

Lead: "Bom dia! Vocês atendem em Praia Grande?"
Will: "Bom dia! Sou o Will da Refrimix, aventuremos! Você está precisando de um serviço relacionado a ar condicionado em Praia Grande? Qual o serviço exato que precisa?"

Lead: "Olha, eu preciso instalar um ar condicionado na minha sala, mas não sei se vale a pena pagar R$800, pois o meu amigo pagou R$500 com um outro cara"
Will: "Olha, instalação padrão high-wall fica R$800 à vista ou R$850 em 3x sem juros. Me manda o tamanho da tua sala e quantas pessoas usam o espaço que a gente faz um orçamento justo, sem compromisso."

Lead: "Quanto custa pra instalar ar condicionado?"
Will: "Instalação padrão high-wall fica R$800 à vista ou R$850 em 3x sem juros. Me passa onde fica e a BTU do equipo que confirmo se tem algum custo adicional de acesso."

Lead: "Vocês instalam equipamento que eu já comprei na loja?"
Will: "Sim, a gente instala equipamentos que você comprou na loja. A instalação é importante porque o equipamento precisa de um setup correto para funcionar corretamente e manter a garantia. Se for instalar em uma área grande, também precisará de ajustes adicionais. Gostaria de saber o endereço onde você planeja instalar o equipamento para agendar uma visita técnica gratuita? Qual a BTU e a marca do equipo? Pergunto pra já verificar o acesso e confirmar o prazo."

Lead: "Faz higienização com ozônio? Tenho criança em casa."
Will: "Olá! Sou o Will da Refrimix. A higienização com ozônio é uma opção adicional que mata ácaros, fungos e bactérias, além de eliminar cheiro e microorganismos na superfície interna. Para quantos aparelhos você precisa agendar? Onde fica o local e qual a marca do aparelho?"

Lead: "Quanto custa pra higienizar um split?"
Will: "Instalação padrão no Guarujá fica R$800. Pra Santos, São Vicente e Praia Grande fica R$850 por causa do deslocamento. Inclui mão de obra e material básico de instalação. Qual a cidade e o modelo do aparelho? Tem urgência?"

Lead: "O ar não tá gelando mais, o que pode ser?"
Will: "Entendido! Vou te passar para um dos nossos especialistas agora. Aguarda um instante que alguém entra em contato contigo em breve. Onde fica o aparelho e qual a marca?"

Lead: "Tá pingando água dentro de casa."
Will: "Entendido! Vou te passar para um dos nossos especialistas agora. Aguarda um instante que alguém entra em contato contigo em breve. O que precisa para a visita técnica?"

Lead: "Me manda um orçamento por escrito."
Will: "Entendido! Instalação padrão high-wall fica R$800 à vista ou R$850 em 3x sem juros no cartão. Me passa onde fica e a BTU do equipo que confirmo se tem algum custo adicional de acesso."

Lead: "Olha, eu preciso instalar um ar condicionado na minha sala, mas tá muito caro o que eu vi até agora. Vocês podem fazer por menos de R$500?"
Will: "Olá! Instalação padrão de ar condicionado na sua sala custa R$800 no Guarujá. Para Santos, São Vicente e Praia Grande, é R$850 devido ao deslocamento. Para confirmar, preciso do endereço e do tipo do aparelho. Quer agendar uma visita técnica gratuita para avaliar?"

Lead: "Eu tenho um ar condicionado que não está funcionando direito, mas eu não sei se é problema do aparelho ou da instalação. Vocês podem me dar uma ideia do que pode ser?"
Will: "Olá! Aqui é o Will da Refrimix. Um problema com o ar condicionado pode ser causado pelo equipamento ou pela instalação. Para ter certeza, precisamos fazer uma análise técnica. Precisa que mande o modelo e marca do seu aparelho? Além disso, gostaria de saber se você já comprou o ar condicionado na loja ou se precisa da nossa ajuda também com a compra? Vamos agendar uma visita técnica gratuita para resolver o problema."

Lead: "Eu tenho um amigo que é técnico de ar condicionado e ele disse que pode instalar um ar condicionado por R$400. Vocês podem fazer pelo mesmo preço?"
Will: "Instalação padrão no Guarujá fica R$800. Pra Santos, São Vicente e Praia Grande fica R$850 por causa do deslocamento. Inclui mão de obra e material básico de instalação. Qual a cidade e o modelo do aparelho? Se tiver acesso difícil, a gente confirma na visita que é gratuita."

Lead: "Eu tenho um ar condicionado que está com cheiro de mofo. Eu não sei se é problema do aparelho ou da instalação. Vocês podem me ajudar a resolver isso?"
Will: "Olá! Sou o Will da Refrimix. Um cheiro de mofo pode ser sintoma de problema na instalação ou no aparelho. Precisamos verificar melhor o seu caso. Podemos agendar uma visita técnica gratuita para avaliar e diagnosticar o problema? Qual é o endereço onde você se encontra com o aparelho? Instalação padrão high-wall fica R$800 à vista ou R$850 em 3x sem juros no cartão."

Lead: "Eu estou procurando por um serviço de manutenção preventiva para o meu ar condicionado. Vocês oferecem isso? E se oferecerem, quanto custa?"
Will: "Oi! Somos a Refrimix e sim, fazemos manutenção preventiva — é o nosso serviço de PMOC, que inclui visitas trimestrais, laudos, ART e certificado pro órgão regulador.

O valor depende da quantidade de equipamentos e do tipo de estabelecimento. Quanto mais aparelhos, mais desconto progressivo você tem.

Para eu montar um orçamento preciso, me diz: 'onde fica o seu estabelecimento e quantos aparelhos precisa manter?'"
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


async def _call_groq(messages: list[dict[str, Any]], max_retries: int = 2, model_override: str | None = None, tools: list[dict] | None = None) -> str | tuple[str, list[dict]]:
    api_key = os.getenv("GROQ_API_KEY", "")
    base_url = os.getenv("GROQ_BASE_URL", "https://api.groq.com/openai/v1")
    model = model_override or os.getenv("GROQ_FALLBACK_MODEL", os.getenv("GROQ_MODEL", "llama-3.1-8b-instant"))

    if not api_key:
        raise RuntimeError("GROQ_API_KEY não configurado")

    last_error: Exception | None = None
    for attempt in range(max_retries):
        try:
            async with httpx.AsyncClient(timeout=60.0) as client:
                    payload = {"model": model, "messages": messages, "max_tokens": 512}
                    if tools:
                        payload["tools"] = tools

                    resp = await client.post(
                        f"{base_url}/chat/completions",
                        headers={
                            "Authorization": f"Bearer {api_key}",
                            "Content-Type": "application/json",
                        },
                        json=payload,
                    )
                    resp.raise_for_status()
                    data = resp.json()
                    if "error" in data:
                        raise RuntimeError(f"Groq error: {data['error']}")
                    if not data.get("choices"):
                        raise RuntimeError(f"Groq sem choices: {data}")
                    
                    message_obj = data["choices"][0]["message"]
                    if tools and "tool_calls" in message_obj:
                        return message_obj.get("content") or "", message_obj["tool_calls"]
                    return message_obj.get("content") or ""
        except Exception as exc:
            last_error = exc
            if attempt < max_retries - 1:
                import asyncio
                await asyncio.sleep(2 ** attempt)
    raise RuntimeError(f"Groq falhou após {max_retries} tentativas: {last_error}")


async def _call_local_qwen(messages: list[dict[str, str]], max_retries: int = 1) -> str:
    """Fallback local OpenAI-compatible via llama.cpp/Qwen2.5-VL no PC1 via SSH."""
    base_url = os.getenv("LOCAL_QWEN_BASE_URL", "http://127.0.0.1:8011/v1").rstrip("/")
    model = os.getenv("LOCAL_QWEN_MODEL", "qwen2.5-vl-7b-instruct")
    ssh_host = os.getenv("SSH_HOST_PC1", "will-zappro@192.168.15.83")

    remote_code = r"""
import json
import sys
import requests

data = json.load(sys.stdin)
base_url = data.pop("_base_url").rstrip("/")
timeout = float(data.pop("_timeout"))
try:
    response = requests.post(f"{base_url}/chat/completions", json=data, timeout=timeout)
    response.raise_for_status()
except requests.HTTPError as exc:
    print(f"Qwen request failed: {exc}; body={response.text[:500]}", file=sys.stderr)
    sys.exit(1)
except Exception as exc:
    print(f"Qwen request failed: {exc}", file=sys.stderr)
    sys.exit(1)
print(response.text)
"""

    last_error: Exception | None = None
    for attempt in range(max_retries):
        try:
            import shlex
            import json
            import asyncio
            payload = {
                "model": model,
                "messages": messages,
                "max_tokens": 300,
                "temperature": 0.2,
                "_base_url": base_url,
                "_timeout": 45.0
            }
            
            proc = await asyncio.create_subprocess_exec(
                "/usr/bin/ssh", "-o", "StrictHostKeyChecking=no", ssh_host, f"python3 -c {shlex.quote(remote_code)}",
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            stdout, stderr = await proc.communicate(input=json.dumps(payload, ensure_ascii=False).encode("utf-8"))
            
            if proc.returncode != 0:
                raise RuntimeError(f"SSH failed: {stderr.decode('utf-8', errors='replace')}")
                
            data = json.loads(stdout.decode("utf-8"))
            if not data.get("choices"):
                raise RuntimeError(f"Qwen local sem choices: {data}")
            return _strip_thinking_tags(data["choices"][0]["message"]["content"])
        except Exception as exc:
            last_error = exc
            if attempt < max_retries - 1:
                import asyncio
                await asyncio.sleep(1)
    raise RuntimeError(f"Qwen local falhou: {last_error}")


async def _call_local_ptbr(messages: list[dict[str, str]], max_retries: int = 1) -> str:
    """Modelo local PT-BR opcional para polir linguagem sem depender de nuvem."""
    base_url = os.getenv("LOCAL_PTBR_BASE_URL", "").rstrip("/")
    model = os.getenv("LOCAL_PTBR_MODEL", "qwen2.5-7b-pt-br-instruct")
    if not base_url:
        raise RuntimeError("LOCAL_PTBR_BASE_URL não configurado")

    last_error: Exception | None = None
    for attempt in range(max_retries):
        try:
            async with httpx.AsyncClient(timeout=45.0) as client:
                resp = await client.post(
                    f"{base_url}/chat/completions",
                    headers={"Content-Type": "application/json"},
                    json={
                        "model": model,
                        "messages": messages,
                        "max_tokens": 240,
                        "temperature": 0.15,
                    },
                )
                resp.raise_for_status()
                data = resp.json()
                if not data.get("choices"):
                    raise RuntimeError(f"PT-BR local sem choices: {data}")
                return _strip_thinking_tags(data["choices"][0]["message"]["content"])
        except Exception as exc:
            last_error = exc
            if attempt < max_retries - 1:
                import asyncio
                await asyncio.sleep(1)
    raise RuntimeError(f"PT-BR local falhou: {last_error}")


async def llm_chat(messages: list[dict[str, str]], max_retries: int = 2) -> str:
    """MiniMax principal, Groq como fallback automático."""
    minimax_key = os.getenv("MINIMAX_API_KEY", "")
    if minimax_key:
        try:
            return await _call_minimax(messages, max_retries)
        except Exception as e:
            logger.warning(f"MiniMax falhou, usando Groq: {e}")

    try:
        return await _call_groq(messages, max_retries)
    except Exception as e:
        logger.warning(f"Groq falhou, tentando Qwen local: {e}")
        return await _call_local_qwen(messages)


def _normalize_text(text: str) -> str:
    return " ".join(text.lower().strip().split())


def _normalize_service(service: str | None) -> str | None:
    if service == "hygienizacao":
        return "higienizacao"
    return service


def _sales_cache_key(service: str | None, text: str) -> str:
    normalized = _normalize_text(text)
    digest = hashlib.sha256(normalized.encode("utf-8")).hexdigest()[:24]
    return f"sales_reply:v1:{service or 'none'}:{digest}"


def _looks_like_price_question(text: str) -> bool:
    lowered = _normalize_text(text)
    return any(term in lowered for term in ("quanto", "custa", "valor", "preço", "preco", "orçamento", "orcamento"))


def _direct_price_response(service: str | None, text: str) -> str | None:
    if not _looks_like_price_question(text):
        return None
    if service == "instalacao":
        return (
            "Instalação padrão no Guarujá fica R$800. Pra Santos, São Vicente e Praia Grande fica R$850 por causa do deslocamento. "
            "Inclui mão de obra e material básico de instalação. "
            "Qual a cidade e o modelo do aparelho?"
        )
    if service == "higienizacao":
        return (
            "Higienização de split fica R$200 por aparelho. "
            "É limpeza profunda com produto bacteriostático, não só lavar filtro. "
            "Quantos aparelhos são?"
        )
    return None


async def _polish_ptbr_if_enabled(response: str, user_text: str) -> str:
    if os.getenv("PTBR_POLISH_ENABLED", "0") != "1":
        return response
    if not os.getenv("LOCAL_PTBR_BASE_URL"):
        return response
    try:
        polished = await _call_local_ptbr([
            {
                "role": "system",
                "content": (
                    "Você reescreve respostas de WhatsApp em português brasileiro natural do Guarujá. "
                    "Preserve todos os preços, nomes de cidade, fatos técnicos e perguntas. "
                    "Não adicione informação nova. Não use lista. Responda só com a versão final."
                ),
            },
            {
                "role": "user",
                "content": f"Lead: {user_text}\nResposta original: {response}",
            },
        ])
        return polished.strip() or response
    except Exception as e:
        logger.warning(f"Polidor PT-BR local ignorado: {e}")
        return response


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
    collection = os.getenv("QDRANT_COLLECTION", "hermes_hvac_rag_service_staging")
    client = QdrantClient(url=qdrant_url)
    service_name = _normalize_service(service_name)

    try:
        model = TextEmbedding(
            model="nomic-ai/nomic-embed-text-v1.5",
            max_length=512,
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
    min_score = float(os.getenv("RAG_MIN_SCORE", "0.35"))
    ranked = []
    for r in results.points:
        if r.score is not None and r.score < min_score:
            continue
        payload = r.payload or {}
        priority = int(payload.get("priority", 50))
        ranked.append({"id": r.id, "score": r.score, "priority": priority, "payload": payload})

    return sorted(ranked, key=lambda x: (x["priority"], -(x["score"] or 0)))[:top_k]


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
    "higienizacao":    "higienizacao_preventiva",
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
        ("quanto custa instalar", 8): "instalacao",
        ("custa instalar", 7): "instalacao",
        ("preço pra instalar", 7): "instalacao",
        ("preço de instalação", 7): "instalacao",
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
        ("higienização", 5): "higienizacao",
        ("higienizacao", 5): "higienizacao",
        ("ozônio", 4): "higienizacao",
        ("ácaros", 4): "higienizacao",
        ("fungos", 3): "higienizacao",
        ("sanitização", 3): "higienizacao",
        ("limpeza do ar", 3): "higienizacao",
        ("cheiro", 1): "higienizacao",
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
            f"instalacao, consultoria, manutencao, pmoc, projeto-central, higienizacao, human\n"
            f"'instalacao' = instalar aparelho novo\n"
            f"'manutencao' = consertar/reparar aparelho existente\n"
            f"'pmoc' = plano preventivo obrigatório/laudo técnico\n"
            f"'consultoria' = dúvida técnica, assessoria, qual equipamento escolher, projeto de obra\n"
            f"'projeto-central' = sistema central, multisplit, vários ambientes, carga térmica\n"
            f"'higienizacao' = limpeza, higienização, cheiro, ácaros\n"
            f"'human' = pede atendente, reclamação, cancelamento ou completamente fora dos serviços\n"
            f"Mensagem: \"{user_text}\"\n"
            f"Responda apenas o nome da categoria, sem explicação."
        )
        resp = await _call_groq([{"role": "user", "content": prompt}], model_override=CLASSIFY_MODEL)
        intent_llm = resp.strip().lower().replace(" ", "-")
        if intent_llm == "hygienizacao":
            intent_llm = "higienizacao"
        VALID = {"instalacao", "consultoria", "manutencao", "pmoc", "projeto-central", "higienizacao", "human"}
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

    intent = _normalize_service(intent)
    service = None if intent == "human" else intent
    outcome = _OUTCOME_MAP.get(intent, "duvida") if intent != "human" else "escalar_humano"

    return {"intent": intent, "service": service, "outcome": outcome, "messages": messages}


async def retrieve_knowledge(state: dict[str, Any]) -> dict[str, Any]:
    """Busca contexto técnico e comercial no Qdrant com FastEmbed."""
    messages = state.get("messages", [])
    service = _normalize_service(state.get("service"))

    if not messages:
        return {"rag_context": [], "messages": messages}

    last_message = messages[-1]
    user_text = last_message.content if hasattr(last_message, "content") else str(last_message)
    recent_human = [
        m.content for m in messages[-6:]
        if isinstance(m, HumanMessage) and getattr(m, "content", "")
    ]
    query = f"servico={service or 'geral'} lead={' | '.join(recent_human[-3:])}"

    try:
        rag_context = qdrant_search(query, service_name=service, top_k=5)
        if len(rag_context) < 3:
            # Complementa com conhecimento geral de vendas, preço e políticas.
            seen = {ctx["id"] for ctx in rag_context}
            for ctx in qdrant_search(user_text, service_name=None, top_k=5):
                if ctx["id"] not in seen:
                    rag_context.append(ctx)
                    seen.add(ctx["id"])
                if len(rag_context) >= 5:
                    break
    except Exception as e:
        logger.warning(f"Qdrant search falhou: {e}")
        rag_context = []

    return {"rag_context": rag_context, "service": service, "messages": messages}


async def generate_response(state: dict[str, Any]) -> dict[str, Any]:
    """Gera resposta na voz do Will usando RAG + MiniMax (Groq fallback)."""
    messages = state.get("messages", [])
    rag_context = state.get("rag_context", [])
    service = _normalize_service(state.get("service"))
    intent = _normalize_service(state.get("intent"))
    outcome = state.get("outcome", "duvida")
    customer_data = state.get("customer_data", {})

    if not messages:
        return {"messages": messages}

    last_message = messages[-1]
    user_text = last_message.content if hasattr(last_message, "content") else str(last_message)

    human_count = sum(1 for m in messages if isinstance(m, HumanMessage))
    cache_key = _sales_cache_key(service, user_text)
    if human_count <= 2:
        try:
            cached = await redis_get(cache_key)
            if cached:
                logger.info(f"Resposta validada via Redis cache: {cache_key}")
                ai_message = AIMessage(content=cached)
                return {
                    "messages": messages + [ai_message],
                    "rag_context": rag_context,
                    "service": service,
                    "outcome": outcome,
                }
        except Exception as e:
            logger.warning(f"Redis sales cache falhou: {e}")

    direct_response = _direct_price_response(service, user_text)
    if direct_response:
        direct_response = await _polish_ptbr_if_enabled(direct_response, user_text)
        ai_message = AIMessage(content=direct_response)
        return {
            "messages": messages + [ai_message],
            "rag_context": rag_context,
            "service": service,
            "outcome": outcome,
        }

    context_parts = []
    for ctx in rag_context:
        payload = ctx.get("payload", {})
        text = payload.get("text")
        if not text:
            continue
        doc_type = payload.get("doc_type", "technical")
        title = payload.get("title", "contexto")
        context_parts.append(f"[{doc_type} | {title}]\n{text}")
    context_str = "\n---\n".join(context_parts) or ""

    # CTA por outcome — guia o Will a conduzir o lead pro próximo passo certo
    outcome_cta = {
        "onboarding":              "OBRIGATÓRIO: Diga 'Olá! Aqui é o Will da Refrimix.' e pergunte como você pode ajudar o cliente hoje. Mantenha em 1 ou 2 linhas no máximo.",
        "analise_tecnica":         "Finalize sugerindo agendar uma visita técnica gratuita e pedindo o endereço do cliente.",
        "higienizacao_preventiva": "Finalize propondo agendar a higienização e perguntando a quantidade e marca dos aparelhos.",
        "reuniao_projeto":         "Finalize propondo marcar uma reunião técnica (online ou presencial) sem compromisso.",
        "duvida":                  "Responda a dúvida tecnicamente, mas de forma simples, e pergunte se precisa de mais alguma ajuda.",
        "escalar_humano":          "Informe com empatia que um especialista da equipe (ou você mesmo em breve) vai assumir o atendimento.",
    }.get(outcome, "Avance a conversa fazendo uma pergunta técnica simples para qualificar o problema do cliente.")

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
        f"==========================================================\n"
        f"[INÍCIO DO CONTEXTO RECUPERADO DA REFRIMIX - USE APENAS ISSO COMO BASE TÉCNICA E COMERCIAL]\n"
        f"{context_str or 'Nenhum contexto recuperado. Você NÃO DEVE inventar preços ou informações técnicas. Peça mais detalhes ao cliente.'}\n"
        f"[FIM DO CONTEXTO RECUPERADO]\n"
        f"==========================================================\n\n"
        f"Objetivo do Atendimento: Resolver a dúvida e avançar na qualificação do lead.\n"
        f"Serviço identificado: {service or 'não classificado'}\n"
        f"Meta para esta mensagem específica: {outcome_cta}\n\n"
        f"MENSAGEM ATUAL DO CLIENTE:\n"
        f"\"{user_text}\"\n\n"
        f"CONTRATO DE GERAÇÃO DA RESPOSTA (OBRIGATÓRIO):\n"
        f"1. Responda de forma profissional e direta, em no máximo 4 frases.\n"
        f"2. ATENÇÃO MÁXIMA: Se o cliente perguntar preço/prazo/detalhe que NÃO está explícito no bloco de contexto acima, VOCÊ NÃO PODE INVENTAR. Responda elegantemente que precisa calcular ou avaliar os detalhes.\n"
        f"3. Faça no máximo UMA pergunta ao final para avançar a conversa.\n"
        f"4. Não repita informações ou perguntas que já constam no histórico da conversa."
    )
    llm_messages.append({"role": "user", "content": user_prompt})

    tools_definition = [
        {
            "type": "function",
            "function": {
                "name": "emitir_orcamento_pdf",
                "description": "Gera um orçamento PDF em tempo real e envia para o WhatsApp do cliente. Chame esta ferramenta SEMPRE que o cliente explicitamente concordar com os valores ou pedir um orçamento por escrito/PDF.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "cliente_nome": {
                            "type": "string",
                            "description": "Nome do cliente extraído da conversa ou 'Cliente Refrimix'."
                        },
                        "servico": {
                            "type": "string",
                            "description": "Tipo de serviço, ex: 'Instalação de Ar Condicionado', 'Higienização'."
                        },
                        "itens": {
                            "type": "array",
                            "items": {
                                "type": "object",
                                "properties": {
                                    "descricao": {"type": "string"},
                                    "valor": {"type": "number"}
                                },
                                "required": ["descricao", "valor"]
                            },
                            "description": "Lista de itens ou serviços a serem detalhados no orçamento."
                        },
                        "doc_type": {
                            "type": "string",
                            "enum": ["orcamento_mao_de_obra", "orcamento_material", "proposta", "contrato"],
                            "description": "O tipo do documento a gerar."
                        }
                    },
                    "required": ["cliente_nome", "servico", "itens", "doc_type"]
                }
            }
        }
    ]

    try:
        MINIMAX_INTENTS = {"pmoc", "consultoria", "projeto-central"}
        if intent in {"onboarding", "human"}:
            response = await _call_local_qwen(llm_messages)
        elif intent not in MINIMAX_INTENTS:
            try:
                response = await _call_groq(llm_messages, tools=tools_definition)
                
                # Check for tool calls
                if isinstance(response, tuple):
                    text_resp, tool_calls = response
                    response = text_resp or "Segue o orçamento solicitado. Estou à disposição para qualquer dúvida!"
                    
                    # Execute tool call
                    for tc in tool_calls:
                        if tc["function"]["name"] == "emitir_orcamento_pdf":
                            try:
                                import json
                                from app.services.pdf_generator import generate_pdf, send_pdf_via_evolution
                                args = json.loads(tc["function"]["arguments"])
                                
                                # Adapta para o formato esperado pelo generate_pdf
                                context_data = {
                                    "cliente": {"nome": args.get("cliente_nome", "Cliente")},
                                    "documentos": [args.get("doc_type", "orcamento_mao_de_obra")],
                                    "valores": {
                                        "gestao_valor": sum(item.get("valor", 0) for item in args.get("itens", []))
                                    },
                                    "execucao": {
                                        "resumo": args.get("servico", "Orçamento"),
                                        "equipamentos": [item.get("descricao") for item in args.get("itens", [])]
                                    }
                                }
                                
                                pdf_bytes = generate_pdf(context_data)
                                phone = customer_data.get("phone") or state.get("phone")
                                if phone:
                                    import asyncio
                                    asyncio.create_task(send_pdf_via_evolution(phone, pdf_bytes, f"orcamento_{phone}.pdf"))
                                    logger.info(f"Orçamento PDF gerado e enviado para {phone}")
                                
                            except Exception as e:
                                logger.error(f"Erro ao executar tool call emitir_orcamento_pdf: {e}")
                
            except Exception as e:
                logger.warning(f"Groq simples falhou, tentando Qwen local: {e}")
                response = await _call_local_qwen(llm_messages)
        else:
            response = await llm_chat(llm_messages)
    except Exception as e:
        logger.warning(f"LLM falhou em generate_response: {e}")
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

    response = await _polish_ptbr_if_enabled(response, user_text)
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
    if len(formatted) >= 2 and formatted[0] == formatted[-1] and formatted[0] in ("'", '"'):
        formatted = formatted[1:-1].strip()
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
