from __future__ import annotations

import os
import base64
import logging
import httpx

logger = logging.getLogger(__name__)

# Groq suporta llama-3.2-11b-vision-preview (multimodal)
# Qwen 2.5 VL via HF como fallback
_GROQ_VISION_MODEL = "llama-3.2-11b-vision-preview"
_GROQ_CHAT_URL = "https://api.groq.com/openai/v1/chat/completions"
_HF_QWEN_MODEL = "Qwen/Qwen2.5-VL-7B-Instruct"
_TIMEOUT = 8.0

_HVAC_VISION_PROMPT = (
    "Você é um técnico de refrigeração e climatização HVAC da Refrimix Tecnologia. "
    "Analise a imagem e descreva: (1) o equipamento mostrado, se identificável; "
    "(2) o problema ou dano visível; (3) possível causa. "
    "Seja direto e técnico. Responda em português brasileiro."
)


class VisionService:
    """Análise de imagens HVAC via modelo multimodal (Groq Vision ou HF Qwen 2.5 VL)."""

    def __init__(self) -> None:
        self._groq_key = os.getenv("GROQ_API_KEY", "")
        self._hf_key = os.getenv("HF_TOKEN", os.getenv("HUGGINGFACE_TOKEN", ""))
        self._evo_url = os.getenv("EVOLUTION_API_URL", "http://localhost:8080")
        self._evo_key = os.getenv("EVOLUTION_API_KEY", os.getenv("AUTHENTICATION_API_KEY", ""))
        self._evo_instance = os.getenv("EVOLUTION_INSTANCE", "RefrimixLead")

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

    async def _analyze_hf(self, image_b64: str, caption: str) -> str:
        """Fallback: Qwen 2.5 VL."""
        base_url = "http://127.0.0.1:8011/v1"
        model = "qwen2.5-vl-7b-instruct"
        
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
                f"{base_url}/chat/completions",
                headers={"Content-Type": "application/json"},
                json={
                    "model": model,
                    "messages": messages,
                    "max_tokens": 300,
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

        try:
            result = await self._analyze_hf(image_b64, caption)
            logger.info(f"Vision (HF): {result[:80]!r}")
            return result
        except Exception as e:
            logger.error(f"Vision HF também falhou: {e}")
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
