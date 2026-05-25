from __future__ import annotations

import os
import base64
import logging
import httpx

logger = logging.getLogger(__name__)

_GROQ_VISION_MODEL = "llama-3.2-11b-vision-preview"
_GROQ_CHAT_URL = "https://api.groq.com/openai/v1/chat/completions"
_TIMEOUT = 8.0

_HVAC_VISION_PROMPT = (
    "Você é um técnico de refrigeração e climatização HVAC da Refrimix Tecnologia.\n"
    "Analise a imagem fornecida com atenção técnica absoluta. Identifique com precisão:\n"
    "1. Se for uma etiqueta/placa de identificação técnica do fabricante (etiqueta de ar condicionado, evaporadora, condensadora, compressor, etc.):\n"
    "   - Extraia a MARCA/FABRICANTE exata (ex: Midea, LG, Springer Carrier, Daikin, Elgin, Samsung, Gree, Fujitsu, Consul, Electrolux).\n"
    "   - Extraia o MODELO exato.\n"
    "   - Extraia a CAPACIDADE (BTUs ou kW).\n"
    "   - Extraia o NÚMERO DE SÉRIE se estiver visível.\n"
    "   - Extraia o gás refrigerante e tensão/voltagem.\n"
    "2. Se for um equipamento instalado ou com problema:\n"
    "   - Descreva o equipamento mostrado, marca e tipo (Split, Janela, Cassete, Piso-Teto).\n"
    "   - Descreva o problema, dano ou anomalia visível.\n"
    "   - Apresente possíveis causas técnicas.\n"
    "Seja extremamente preciso, direto e profissional. Responda em português brasileiro."
)


class VisionService:
    """Análise de imagens HVAC via modelo multimodal (Groq Vision ou local llama.cpp Qwen 2.5 VL)."""

    def __init__(self) -> None:
        self._groq_key = os.getenv("GROQ_API_KEY", "")
        self._evo_url = os.getenv("EVOLUTION_API_URL", "http://localhost:8080")
        self._evo_key = os.getenv("EVOLUTION_API_KEY", os.getenv("AUTHENTICATION_API_KEY", ""))
        self._evo_instance = os.getenv("EVOLUTION_INSTANCE", "RefrimixLead")
        self._local_qwen_url = os.getenv("LOCAL_QWEN_BASE_URL", "http://127.0.0.1:8010/v1").rstrip("/")
        self._local_qwen_model = os.getenv("LOCAL_QWEN_MODEL", "qwen2.5-vl-7b-instruct")

    async def _fetch_image_b64(
        self,
        image_url: str,
        instance: str | None,
        msg_id: str | None = None,
        media_base64: str | None = None,
    ) -> str:
        """Baixa imagem e retorna como base64. Usa Evolution API se URL privada."""
        if media_base64:
            return media_base64

        if image_url:
            try:
                async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
                    resp = await client.get(image_url)
                    if resp.status_code == 200 and len(resp.content) > 512:
                        return base64.b64encode(resp.content).decode()
            except Exception:
                pass

        if not msg_id:
            raise RuntimeError("Sem media_base64, URL acessível ou msg_id para baixar a imagem")

        # Fallback: Evolution API via msg_id
        inst = instance or self._evo_instance
        async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
            resp = await client.post(
                f"{self._evo_url}/chat/getBase64FromMediaMessage/{inst}",
                headers={"apikey": self._evo_key, "Content-Type": "application/json"},
                json={"message": {"key": {"id": msg_id}}, "convertToMp4": False},
            )
            resp.raise_for_status()
            data = resp.json()
            b64 = data.get("base64") or data.get("data", {}).get("base64", "")
            if not b64:
                raise RuntimeError(f"Evolution API não retornou base64 de imagem: {data}")
            return b64

    async def _analyze_groq(self, image_b64: str, caption: str) -> str:
        """Primary: Groq Vision (llama-3.2-11b-vision-preview)."""
        if not self._groq_key:
            raise RuntimeError("GROQ_API_KEY não configurado")

        user_text = _HVAC_VISION_PROMPT
        if caption:
            user_text += f"\nLegenda do usuário: {caption}"

        messages = [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": user_text},
                    {
                        "type": "image_url",
                        "image_url": {"url": f"data:image/jpeg;base64,{image_b64}"},
                    },
                ],
            }
        ]

        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.post(
                _GROQ_CHAT_URL,
                headers={
                    "Authorization": f"Bearer {self._groq_key}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": _GROQ_VISION_MODEL,
                    "messages": messages,
                    "max_tokens": 512,
                    "temperature": 0.2,
                },
            )
            resp.raise_for_status()
            data = resp.json()
            if not data.get("choices"):
                raise RuntimeError(f"Groq Vision sem choices: {data}")
            return data["choices"][0]["message"]["content"].strip()

    async def _analyze_local_qwen(self, image_b64: str, caption: str) -> str:
        """Fallback: Local Qwen 2.5 VL via llamacpp."""
        user_text = _HVAC_VISION_PROMPT
        if caption:
            user_text += f"\nLegenda do usuário: {caption}"

        messages = [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": user_text},
                    {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{image_b64}"}}
                ]
            }
        ]

        async with httpx.AsyncClient(timeout=45.0) as client:
            resp = await client.post(
                f"{self._local_qwen_url}/chat/completions",
                headers={"Content-Type": "application/json"},
                json={
                    "model": self._local_qwen_model,
                    "messages": messages,
                    "max_tokens": 512,
                    "temperature": 0.2,
                    "frequency_penalty": 0.5,
                },
            )
            resp.raise_for_status()
            data = resp.json()
            if not data.get("choices"):
                raise RuntimeError(f"Vision local sem choices: {data}")
            return data["choices"][0]["message"]["content"].strip()

    async def analyze_image(
        self,
        image_url: str,
        caption: str = "",
        instance: str | None = None,
        msg_id: str | None = None,
        media_base64: str | None = None,
    ) -> str:
        """Analisa imagem HVAC e retorna descrição técnica em pt-BR."""
        try:
            image_b64 = await self._fetch_image_b64(image_url, instance, msg_id, media_base64)
        except Exception as e:
            logger.warning(f"Vision: falhou ao buscar imagem {image_url!r}: {e}")
            return caption or "Imagem não processada."

        # 1. Tenta primeiro o local llama.cpp Qwen 2.5 VL (porta 8010, custo zero)
        try:
            result = await self._analyze_local_qwen(image_b64, caption)
            logger.info(f"Vision (Local Qwen): {result[:80]!r}")
            return result
        except Exception as e:
            logger.warning(f"Vision Local Qwen falhou, tentando fallback com Groq Vision: {e}")

        # 2. Fallback para Groq Vision (llama-3.2-11b-vision-preview na nuvem)
        try:
            result = await self._analyze_groq(image_b64, caption)
            logger.info(f"Vision (Groq): {result[:80]!r}")
            return result
        except Exception as e:
            logger.error(f"Vision Groq também falhou: {e}")
            return caption or "Não foi possível analisar a imagem."


_vision = VisionService()


async def analyze_image(
    image_url: str,
    caption: str = "",
    instance: str | None = None,
    msg_id: str | None = None,
    media_base64: str | None = None,
) -> str:
    return await _vision.analyze_image(image_url, caption, instance, msg_id, media_base64)
