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

    async def _analyze_groq(self, image_b64: str, caption: str) -> str:
        """Análise via Groq llama-3.2-11b-vision-preview."""
        user_content: list[dict] = [
            {
                "type": "image_url",
                "image_url": {"url": f"data:image/jpeg;base64,{image_b64}"},
            },
        ]
        if caption:
            user_content.append({"type": "text", "text": f"Legenda do usuário: {caption}"})

        max_retries = 5
        last_error = None
        for attempt in range(max_retries):
            try:
                async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
                    resp = await client.post(
                        _GROQ_CHAT_URL,
                        headers={
                            "Authorization": f"Bearer {self._groq_key}",
                            "Content-Type": "application/json",
                        },
                        json={
                            "model": _GROQ_VISION_MODEL,
                            "messages": [
                                {"role": "system", "content": _HVAC_VISION_PROMPT},
                                {"role": "user", "content": user_content},
                            ],
                            "max_tokens": 300,
                        },
                    )
                    if resp.status_code == 429:
                        import asyncio
                        wait_time = 2 ** attempt + 2.0
                        logger.warning(f"Groq Vision 429 Rate Limit. Retrying in {wait_time}s...")
                        await asyncio.sleep(wait_time)
                        continue

                    resp.raise_for_status()
                    data = resp.json()
                    if not data.get("choices"):
                        raise RuntimeError(f"Groq Vision sem choices: {data}")
                    return data["choices"][0]["message"]["content"].strip()
            except Exception as e:
                last_error = e
                if attempt < max_retries - 1:
                    import asyncio
                    await asyncio.sleep(2 ** attempt + 1.0)
                else:
                    raise RuntimeError(f"Erro no Groq Vision após {max_retries} tentativas: {e}")
        return ""

    async def _analyze_hf(self, image_b64: str, caption: str) -> str:
        """Fallback: Qwen 2.5 VL via SSH no PC1."""
        ssh_host = os.getenv("SSH_HOST_PC1", "will-zappro@192.168.15.83")
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
    print(f"Vision request failed: {exc}; body={response.text[:500]}", file=sys.stderr)
    sys.exit(1)
except Exception as exc:
    print(f"Vision request failed: {exc}", file=sys.stderr)
    sys.exit(1)
print(response.text)
"""
        import shlex
        import json
        import asyncio
        payload = {
            "model": model,
            "messages": messages,
            "max_tokens": 300,
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
            raise RuntimeError(f"Vision SSH failed: {stderr.decode('utf-8', errors='replace')}")
            
        data = json.loads(stdout.decode("utf-8"))
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

        if self._groq_key:
            try:
                result = await self._analyze_groq(image_b64, caption)
                logger.info(f"Vision (Groq): {result[:80]!r}")
                return result
            except Exception as e:
                logger.warning(f"Vision Groq falhou, tentando HF: {e}")

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
