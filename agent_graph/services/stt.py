from __future__ import annotations

import os
import logging
import httpx

logger = logging.getLogger(__name__)

_GROQ_AUDIO_URL = "https://api.groq.com/openai/v1/audio/transcriptions"
_WHISPER_MODEL = "whisper-large-v3-turbo"
_EVO_TIMEOUT = 20.0
_GROQ_TIMEOUT = 30.0


class STTService:
    """Transcrição de áudio via Groq Whisper Large v3 Turbo."""

    def __init__(self) -> None:
        self._groq_key = os.getenv("GROQ_API_KEY", "")
        self._evo_url = os.getenv("EVOLUTION_API_URL", "http://localhost:8080")
        self._evo_key = os.getenv("EVOLUTION_API_KEY", os.getenv("AUTHENTICATION_API_KEY", ""))
        self._evo_instance = os.getenv("EVOLUTION_INSTANCE", "RefrimixLead")

    async def _fetch_audio_bytes(
        self,
        media_url: str,
        instance: str | None,
        msg_id: str | None = None,
        media_base64: str | None = None,
    ) -> bytes:
        import base64
        
        if media_base64:
            return base64.b64decode(media_base64)

        if media_url:
            try:
                async with httpx.AsyncClient(timeout=_EVO_TIMEOUT) as client:
                    resp = await client.get(media_url, headers={"User-Agent": "Mozilla/5.0"})
                    if resp.status_code == 200 and len(resp.content) > 1024:
                        return resp.content
            except Exception:
                pass

        if not msg_id:
            raise RuntimeError("Sem media_base64, URL acessível ou msg_id para baixar o áudio")

        # Fallback: Evolution API converte mensagem para base64 via msg_id
        inst = instance or self._evo_instance
        async with httpx.AsyncClient(timeout=_EVO_TIMEOUT) as client:
            resp = await client.post(
                f"{self._evo_url}/chat/getBase64FromMediaMessage/{inst}",
                headers={"apikey": self._evo_key, "Content-Type": "application/json"},
                json={"message": {"key": {"id": msg_id}}, "convertToMp4": False},
            )
            resp.raise_for_status()
            data = resp.json()
            b64 = data.get("base64") or data.get("data", {}).get("base64", "")
            if not b64:
                raise RuntimeError(f"Evolution API não retornou base64: {data}")
            return base64.b64decode(b64)

    async def transcribe_audio(
        self,
        media_url: str,
        instance: str | None = None,
        msg_id: str | None = None,
        media_base64: str | None = None,
    ) -> str:
        """Baixa áudio e transcreve via Groq Whisper."""
        audio_bytes = await self._fetch_audio_bytes(media_url, instance, msg_id, media_base64)
        return await self.transcribe_bytes(audio_bytes, filename="audio.ogg")

    async def transcribe_bytes(self, audio_bytes: bytes, filename: str = "audio.ogg") -> str:
        """Envia bytes de áudio para Groq Whisper e retorna transcrição."""
        if not self._groq_key:
            raise RuntimeError("GROQ_API_KEY não configurado")

        async with httpx.AsyncClient(timeout=_GROQ_TIMEOUT) as client:
            resp = await client.post(
                _GROQ_AUDIO_URL,
                headers={"Authorization": f"Bearer {self._groq_key}"},
                files={"file": (filename, audio_bytes, "audio/ogg")},
                data={
                    "model": _WHISPER_MODEL,
                    "language": "pt",
                    "response_format": "json",
                    "prompt": "Will da Refrimix, ar condicionado split, Midea, LG, Springer Carrier, Daikin, Elgin, Samsung, Gree, Fujitsu, Consul, Electrolux, PMOC, inverter, BTUs, higienização, orçamento, Guarujá, Santos.",
                },
            )
            resp.raise_for_status()
            data = resp.json()
            text = data.get("text", "").strip()
            if not text:
                raise RuntimeError(f"Whisper retornou transcrição vazia: {data}")
            logger.info(f"STT transcribed {len(audio_bytes)} bytes → {text[:80]!r}")
            return text


_stt = STTService()


async def transcribe_audio(
    media_url: str,
    instance: str | None = None,
    msg_id: str | None = None,
    media_base64: str | None = None,
) -> str:
    return await _stt.transcribe_audio(media_url, instance, msg_id, media_base64)


async def transcribe_bytes(audio_bytes: bytes, filename: str = "audio.ogg") -> str:
    return await _stt.transcribe_bytes(audio_bytes, filename)
