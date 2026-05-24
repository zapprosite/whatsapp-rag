from __future__ import annotations

import os
import logging
import httpx

logger = logging.getLogger(__name__)

# Coqui XTTS v2 rodando local em :8020
# Path dos samples de voz do Will (montados no PC1)
_XTTS_URL = "http://localhost:8020"
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
    """Síntese de voz via Coqui XTTS v2 local com voice clone do Will."""

    def __init__(self) -> None:
        self._xtts_url = os.getenv("XTTS_URL", _XTTS_URL)
        self._voices_path = os.getenv("TTS_VOICES_PATH", "/srv/data/tts/voices")

    def _speaker_wav_path(self, style: str) -> str:
        name = _VOICE_STYLES.get(style, _VOICE_STYLES[_DEFAULT_STYLE])
        return os.path.join(self._voices_path, f"{name}.wav")

    async def synthesize(
        self,
        text: str,
        voice_style: str = _DEFAULT_STYLE,
    ) -> bytes | None:
        """
        Sintetiza texto com voz clonada do Will via XTTS.
        Retorna WAV bytes ou None se XTTS indisponível.
        """
        speaker_wav = self._speaker_wav_path(voice_style)

        # Tenta endpoint /tts (XTTS API server padrão)
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
                    logger.info(f"TTS OK: {len(resp.content)} bytes (style={voice_style})")
                    return resp.content
                logger.warning(f"XTTS /tts retornou {resp.status_code}: {resp.text[:100]}")
        except httpx.ConnectError:
            logger.warning(f"XTTS indisponível em {self._xtts_url} — resposta será texto")
        except Exception as e:
            logger.error(f"XTTS erro: {e}")

        return None

    async def health(self) -> bool:
        """Verifica se o servidor XTTS está acessível."""
        try:
            async with httpx.AsyncClient(timeout=3.0) as client:
                resp = await client.get(f"{self._xtts_url}/health")
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
