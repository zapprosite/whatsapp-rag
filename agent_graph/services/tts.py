from __future__ import annotations

import os
import logging
import httpx

logger = logging.getLogger(__name__)

# TTS local/PC1. OmniVoice usa API OpenAI-compatible; XTTS fica como legado.
_XTTS_URL = "http://localhost:8020"
_OMNIVOICE_URL = "http://127.0.0.1:8202"
_TTS_TIMEOUT = 30.0

# Estilos de voz mapeados para samples WAV no PC1
_VOICE_STYLES: dict[str, str] = {
    "influencer": "willrefrimix-influencer",
    "tecnico":    "willrefrimix-tecnico",
    "calmo":      "willrefrimix-calmo",
    "animado":    "willrefrimix-animado",
    "normal":     "willrefrimix-normal",
    "serio":      "willrefrimix-serio",
}
_DEFAULT_STYLE = "normal"

# Mensagens que devem sempre ser respondidas em áudio
_AUDIO_INTENT_KEYWORDS = frozenset([
    "oi", "olá", "boa tarde", "bom dia", "boa noite",
    "tudo bem", "pode me ajudar", "quero falar",
])


class TTSService:
    """Síntese de voz com clone do Will via OmniVoice ou XTTS legado."""

    def __init__(self) -> None:
        self._engine = os.getenv("TTS_ENGINE", "omnivoice").lower().strip()
        self._xtts_url = os.getenv("XTTS_URL", _XTTS_URL)
        self._omnivoice_url = os.getenv("OMNIVOICE_URL", _OMNIVOICE_URL)
        self._voices_path = os.getenv("TTS_VOICES_PATH", "/srv/data/tts/voices")

    def _voice_name(self, style: str) -> str:
        return _VOICE_STYLES.get(style, _VOICE_STYLES[_DEFAULT_STYLE])

    def _speaker_wav_path(self, style: str) -> str:
        name = self._voice_name(style)
        return os.path.join(self._voices_path, f"{name}.wav")

    async def _synthesize_omnivoice(self, text: str, voice_style: str) -> bytes | None:
        voice = self._voice_name(voice_style)
        ssh_host = os.getenv("SSH_HOST_PC1", "will-zappro@192.168.15.83")
        
        remote_code = r"""
import json
import sys
import requests

data = json.load(sys.stdin)
base_url = data.pop("_base_url").rstrip("/")
timeout = float(data.pop("_timeout"))
try:
    response = requests.post(f"{base_url}/v1/audio/speech", json=data, timeout=timeout)
    response.raise_for_status()
except requests.HTTPError as exc:
    detail = response.text[:500]
    print(f"OmniVoice request failed: {exc}; body={detail}", file=sys.stderr)
    sys.exit(1)
except Exception as exc:
    print(f"OmniVoice request failed: {exc}", file=sys.stderr)
    sys.exit(1)
sys.stdout.buffer.write(response.content)
"""
        try:
            import shlex
            import json
            import asyncio
            payload = {
                "model": "omnivoice",
                "input": text,
                "voice": voice,
                "language": "pt-BR",
                "response_format": "wav",
                "_base_url": self._omnivoice_url,
                "_timeout": _TTS_TIMEOUT
            }
            proc = await asyncio.create_subprocess_exec(
                "/usr/bin/ssh", "-o", "StrictHostKeyChecking=no", ssh_host, f"python3 -c {shlex.quote(remote_code)}",
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            stdout, stderr = await proc.communicate(input=json.dumps(payload, ensure_ascii=False).encode("utf-8"))
            
            if proc.returncode != 0:
                logger.warning(f"OmniVoice SSH falhou: {stderr.decode('utf-8', errors='replace')}")
                return None
                
            if len(stdout) > 512:
                logger.info(f"OmniVoice SSH OK: {len(stdout)} bytes (voice={voice})")
                return stdout
        except Exception as e:
            logger.error(f"OmniVoice erro SSH: {e}")
        return None

    async def _synthesize_xtts(self, text: str, voice_style: str) -> bytes | None:
        speaker_wav = self._speaker_wav_path(voice_style)

        try:
            async with httpx.AsyncClient(timeout=_TTS_TIMEOUT) as client:
                resp = await client.post(
                    f"{self._xtts_url}/tts",
                    json={
                        "text": text,
                        "language": "pt",
                        "speaker_wav": speaker_wav,
                    },
                )
                if resp.status_code == 200 and len(resp.content) > 512:
                    logger.info(f"XTTS OK: {len(resp.content)} bytes (style={voice_style})")
                    return resp.content
                logger.warning(f"XTTS /tts retornou {resp.status_code}: {resp.text[:100]}")
        except httpx.ConnectError:
            logger.warning(f"XTTS indisponível em {self._xtts_url} — resposta será texto")
        except Exception as e:
            logger.error(f"XTTS erro: {e}")
        return None

    async def synthesize(
        self,
        text: str,
        voice_style: str = _DEFAULT_STYLE,
    ) -> bytes | None:
        """
        Sintetiza texto com voz clonada do Will.
        Retorna WAV bytes ou None se os engines estiverem indisponíveis.
        """
        if self._engine == "omnivoice":
            audio = await self._synthesize_omnivoice(text, voice_style)
            if audio:
                return audio
            return await self._synthesize_xtts(text, voice_style)
        if self._engine == "xtts":
            audio = await self._synthesize_xtts(text, voice_style)
            if audio:
                return audio
            return await self._synthesize_omnivoice(text, voice_style)

        logger.warning(f"TTS_ENGINE inválido: {self._engine}")
        return None

    async def health(self) -> bool:
        """Verifica se o servidor TTS primário está acessível."""
        try:
            async with httpx.AsyncClient(timeout=3.0) as client:
                base_url = self._omnivoice_url if self._engine == "omnivoice" else self._xtts_url
                resp = await client.get(f"{base_url}/health")
                return resp.status_code == 200
        except Exception:
            return False


def choose_voice_style(intent: str | None, outcome: str | None) -> str:
    """Seleciona estilo de voz do Will conforme contexto da conversa."""
    if outcome == "escalar_humano":
        return "calmo"
    if intent in ("pmoc", "consultoria", "projeto-central"):
        return "tecnico"
    if outcome in ("analise_tecnica", "higienizacao_preventiva"):
        return "animado"
    return "normal"


def should_respond_with_audio(
    message_type: str | None,
    intent: str | None,
    outcome: str | None,
    user_text: str = "",
) -> bool:
    """
    Decide se a resposta deve ser em áudio.
    Regras:
    - Espelha inbound: se veio áudio, responde áudio
    - Saudações e qualificação inicial → áudio
    - Preços, listas longas, PMOC (texto técnico) → texto
    """
    if message_type == "audioMessage":
        return True

    # Nunca áudio para conteúdo técnico longo
    if intent in ("pmoc", "consultoria") or outcome in ("reuniao_projeto",):
        return False

    # Áudio para saudação / qualificação / agendamento
    text_lower = user_text.lower()
    if any(kw in text_lower for kw in _AUDIO_INTENT_KEYWORDS):
        return True

    return False


_tts = TTSService()


async def synthesize(text: str, voice_style: str = _DEFAULT_STYLE) -> bytes | None:
    return await _tts.synthesize(text, voice_style)


async def tts_health() -> bool:
    return await _tts.health()
