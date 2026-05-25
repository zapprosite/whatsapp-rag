from __future__ import annotations

import asyncio
import json
import logging
import os
import re
import shlex

import httpx

logger = logging.getLogger(__name__)

# TTS local/PC1. Chatterbox Multilingual é primário; OmniVoice é fallback seguro.
_XTTS_URL = "http://localhost:8020"
_OMNIVOICE_URL = "http://127.0.0.1:8202"
_CHATTERBOX_URL = "http://127.0.0.1:8200"
_DEFAULT_LOCALE = "pt-BR"
_XTTS_LANGUAGE = "pt"
_TTS_TIMEOUT = 30.0
_MIN_AUDIO_BYTES = 512
_DEFAULT_MAX_CHARS = 420

# Estilos de voz mapeados para samples WAV no PC1
_VOICE_STYLES: dict[str, str] = {
    "influencer": "willrefrimix-influencer",
    "tecnico":    "willrefrimix-tecnico",
    "calmo":      "willrefrimix-calmo",
    "animado":    "willrefrimix-animado",
    "normal":     "willrefrimix-normal",
    "serio":      "willrefrimix-serio",
}
_DEFAULT_STYLE = "influencer"

# Mensagens que devem sempre ser respondidas em áudio
_AUDIO_INTENT_KEYWORDS = frozenset([
    "oi", "olá", "boa tarde", "bom dia", "boa noite",
    "tudo bem", "pode me ajudar", "quero falar",
    "opa", "fala", "e aí", "beleza", "blz",
])

_ACRONYM_REPLACEMENTS = {
    "PMOC": "P M O C",
    "ART": "A R T",
    "CREA": "C R E A",
    "BTU": "B T U",
    "BTUS": "B T U",
    "HVAC": "H V A C",
    "API": "A P I",
    "IA": "I A",
    "PIX": "Pix",
}

_UNITS = (
    "zero", "um", "dois", "três", "quatro",
    "cinco", "seis", "sete", "oito", "nove",
)
_TEENS = {
    10: "dez",
    11: "onze",
    12: "doze",
    13: "treze",
    14: "quatorze",
    15: "quinze",
    16: "dezesseis",
    17: "dezessete",
    18: "dezoito",
    19: "dezenove",
}
_TENS = {
    20: "vinte",
    30: "trinta",
    40: "quarenta",
    50: "cinquenta",
    60: "sessenta",
    70: "setenta",
    80: "oitenta",
    90: "noventa",
}
_HUNDREDS = {
    100: "cem",
    200: "duzentos",
    300: "trezentos",
    400: "quatrocentos",
    500: "quinhentos",
    600: "seiscentos",
    700: "setecentos",
    800: "oitocentos",
    900: "novecentos",
}


def _env_bool(name: str, default: bool = False) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on", "sim"}


def _env_int(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, str(default)).strip())
    except (AttributeError, ValueError):
        return default


def _number_to_words_ptbr(value: int) -> str:
    if value < 0:
        return str(value)
    if value < 10:
        return _UNITS[value]
    if value < 20:
        return _TEENS[value]
    if value < 100:
        tens = (value // 10) * 10
        remainder = value % 10
        return _TENS[tens] if remainder == 0 else f"{_TENS[tens]} e {_UNITS[remainder]}"
    if value < 1000:
        if value == 100:
            return "cem"
        hundreds = (value // 100) * 100
        remainder = value % 100
        prefix = "cento" if hundreds == 100 else _HUNDREDS[hundreds]
        return prefix if remainder == 0 else f"{prefix} e {_number_to_words_ptbr(remainder)}"
    if value < 10000:
        thousands = value // 1000
        remainder = value % 1000
        prefix = "mil" if thousands == 1 else f"{_number_to_words_ptbr(thousands)} mil"
        if remainder == 0:
            return prefix
        separator = " e " if remainder < 100 or remainder % 100 == 0 else " "
        return f"{prefix}{separator}{_number_to_words_ptbr(remainder)}"
    return str(value)


def _money_to_words(match: re.Match[str]) -> str:
    raw_reais = match.group("reais").replace(".", "")
    raw_centavos = match.group("centavos")
    reais = int(raw_reais)
    centavos = int(raw_centavos) if raw_centavos else 0
    reais_text = "um real" if reais == 1 else f"{_number_to_words_ptbr(reais)} reais"
    if not centavos:
        return reais_text
    centavos_text = "um centavo" if centavos == 1 else f"{_number_to_words_ptbr(centavos)} centavos"
    return f"{reais_text} e {centavos_text}"


def _normalize_tts_text_ptbr(text: str) -> str:
    """Normaliza texto escrito para fala curta em pt-BR de WhatsApp."""
    normalized = re.sub(r"https?://\S+|www\.\S+", "link", text.strip(), flags=re.IGNORECASE)
    normalized = re.sub(r"[*_`#>]+", " ", normalized)
    normalized = re.sub(r"\b(equipo|equipos)\b", "equipamento", normalized, flags=re.IGNORECASE)
    normalized = re.sub(
        r"R\$\s*(?P<reais>\d{1,3}(?:\.\d{3})*|\d+)(?:,(?P<centavos>\d{2}))?",
        _money_to_words,
        normalized,
    )

    def times_to_words(match: re.Match[str]) -> str:
        number = int(match.group(1))
        if 1 <= number <= 12:
            return f"{_number_to_words_ptbr(number)} vezes"
        return f"{number} vezes"

    normalized = re.sub(r"\b(\d{1,2})x\b", times_to_words, normalized, flags=re.IGNORECASE)

    def acronym_to_speech(match: re.Match[str]) -> str:
        word = match.group(0).upper()
        return _ACRONYM_REPLACEMENTS.get(word, match.group(0))

    normalized = re.sub(
        r"\b(PMOC|ART|CREA|BTUS?|HVAC|API|IA|PIX)\b",
        acronym_to_speech,
        normalized,
        flags=re.IGNORECASE,
    )
    normalized = re.sub(r"\s+", " ", normalized).strip()
    return normalized


def _truncate_for_audio(text: str, max_chars: int) -> str:
    if max_chars <= 0 or len(text) <= max_chars:
        return text
    candidate = text[:max_chars].rstrip()
    punctuation_cut = max(candidate.rfind("."), candidate.rfind("?"), candidate.rfind("!"))
    if punctuation_cut >= max(20, int(max_chars * 0.25)):
        return candidate[: punctuation_cut + 1].strip()
    space_cut = candidate.rfind(" ")
    if space_cut >= int(max_chars * 0.55):
        candidate = candidate[:space_cut]
    return candidate.rstrip(" ,;:-") + "."


class TTSService:
    """Síntese de voz com clone do Will via Chatterbox/OmniVoice e fallbacks controlados."""

    def __init__(self) -> None:
        self._engine = os.getenv("TTS_ENGINE", "omnivoice").lower().strip()
        self._xtts_url = os.getenv("XTTS_URL", _XTTS_URL)
        self._omnivoice_url = os.getenv("OMNIVOICE_URL", _OMNIVOICE_URL)
        self._chatterbox_url = os.getenv("CHATTERBOX_URL", _CHATTERBOX_URL)
        self._voices_path = os.getenv("TTS_VOICES_PATH", "/srv/data/tts/voices")
        self._locale = os.getenv("TTS_LOCALE", _DEFAULT_LOCALE).strip() or _DEFAULT_LOCALE
        self._xtts_language = os.getenv("TTS_XTTS_LANGUAGE", _XTTS_LANGUAGE).strip() or _XTTS_LANGUAGE
        self._allow_xtts_pt_fallback = _env_bool("TTS_ALLOW_XTTS_PT_FALLBACK", False)
        self._allow_chatterbox_ptbr = _env_bool("TTS_ALLOW_CHATTERBOX_PTBR", False)
        self._max_chars = _env_int("TTS_MAX_CHARS", _DEFAULT_MAX_CHARS)

    def _voice_name(self, style: str) -> str:
        return _VOICE_STYLES.get(style, _VOICE_STYLES[_DEFAULT_STYLE])

    def _speaker_wav_path(self, style: str) -> str:
        name = self._voice_name(style)
        return os.path.join(self._voices_path, f"{name}.wav")

    def _target_is_ptbr(self) -> bool:
        return self._locale.lower().replace("_", "-") == "pt-br"

    async def _post_pc1_audio(
        self,
        base_url: str,
        path: str,
        payload: dict[str, object],
        service_name: str,
    ) -> bytes | None:
        ssh_host = os.getenv("SSH_HOST_PC1", "will-zappro@192.168.15.83")
        remote_code = r"""
import json
import sys
import requests

data = json.load(sys.stdin)
base_url = data.pop("_base_url").rstrip("/")
path = data.pop("_path")
timeout = float(data.pop("_timeout"))
try:
    response = requests.post(f"{base_url}{path}", json=data, timeout=timeout)
    response.raise_for_status()
except requests.HTTPError as exc:
    detail = response.text[:500]
    print(f"request failed: {exc}; body={detail}", file=sys.stderr)
    sys.exit(1)
except Exception as exc:
    print(f"request failed: {exc}", file=sys.stderr)
    sys.exit(1)
sys.stdout.buffer.write(response.content)
"""
        try:
            remote_payload = dict(payload)
            remote_payload["_base_url"] = base_url
            remote_payload["_path"] = path
            remote_payload["_timeout"] = _TTS_TIMEOUT
            proc = await asyncio.create_subprocess_exec(
                "/usr/bin/ssh",
                "-o",
                "StrictHostKeyChecking=no",
                ssh_host,
                f"python3 -c {shlex.quote(remote_code)}",
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await proc.communicate(
                input=json.dumps(remote_payload, ensure_ascii=False).encode("utf-8")
            )
            
            if proc.returncode != 0:
                logger.warning("%s SSH falhou: %s", service_name, stderr.decode("utf-8", errors="replace"))
                return None
                
            if len(stdout) > _MIN_AUDIO_BYTES:
                logger.info("%s SSH OK: %s bytes", service_name, len(stdout))
                return stdout
        except Exception as e:
            logger.error("%s erro SSH: %s", service_name, e)
        return None

    async def _get_pc1_json(self, base_url: str, path: str, service_name: str) -> dict[str, object] | None:
        ssh_host = os.getenv("SSH_HOST_PC1", "will-zappro@192.168.15.83")
        remote_code = r"""
import json
import sys
import requests

data = json.load(sys.stdin)
base_url = data["_base_url"].rstrip("/")
path = data["_path"]
timeout = float(data["_timeout"])
try:
    response = requests.get(f"{base_url}{path}", timeout=timeout)
    response.raise_for_status()
except Exception as exc:
    print(f"request failed: {exc}", file=sys.stderr)
    sys.exit(1)
sys.stdout.write(response.text)
"""
        try:
            proc = await asyncio.create_subprocess_exec(
                "/usr/bin/ssh",
                "-o",
                "StrictHostKeyChecking=no",
                ssh_host,
                f"python3 -c {shlex.quote(remote_code)}",
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await proc.communicate(
                input=json.dumps(
                    {"_base_url": base_url, "_path": path, "_timeout": 3.0},
                    ensure_ascii=False,
                ).encode("utf-8")
            )
            if proc.returncode != 0:
                logger.warning("%s health SSH falhou: %s", service_name, stderr.decode("utf-8", errors="replace"))
                return None
            return json.loads(stdout.decode("utf-8"))
        except Exception as e:
            logger.error("%s health erro SSH: %s", service_name, e)
            return None

    async def _synthesize_omnivoice(self, text: str, voice_style: str) -> bytes | None:
        voice = self._voice_name(voice_style)
        payload: dict[str, object] = {
            "model": "omnivoice",
            "input": text,
            "voice": voice,
            "language": self._locale,
            "response_format": "wav",
        }
        speed = os.getenv("TTS_OMNIVOICE_SPEED", "").strip()
        if speed:
            try:
                payload["speed"] = float(speed)
            except ValueError:
                logger.warning("TTS_OMNIVOICE_SPEED inválido: %s", speed)
        return await self._post_pc1_audio(
            self._omnivoice_url,
            "/v1/audio/speech",
            payload,
            f"OmniVoice voice={voice} locale={self._locale}",
        )

    async def _synthesize_chatterbox(self, text: str, voice_style: str) -> bytes | None:
        if self._target_is_ptbr() and not self._allow_chatterbox_ptbr:
            logger.warning("Chatterbox local bloqueado para pt-BR: modelo atual do PC1 não está em modo multilíngue")
            return None

        voice = f"{self._voice_name(voice_style)}.wav"
        payload: dict[str, object] = {
            "text": text,
            "voice_mode": "predefined",
            "predefined_voice_id": voice,
            "output_format": "wav",
            "language": self._xtts_language,
            "split_text": True,
            "chunk_size": 120,
        }
        return await self._post_pc1_audio(
            self._chatterbox_url,
            "/tts",
            payload,
            f"Chatterbox voice={voice} language={self._xtts_language}",
        )

    async def _synthesize_xtts(self, text: str, voice_style: str) -> bytes | None:
        speaker_wav = self._speaker_wav_path(voice_style)

        try:
            async with httpx.AsyncClient(timeout=_TTS_TIMEOUT) as client:
                resp = await client.post(
                    f"{self._xtts_url}/tts",
                    json={
                        "text": text,
                        "language": self._xtts_language,
                        "speaker_wav": speaker_wav,
                    },
                )
                if resp.status_code == 200 and len(resp.content) > _MIN_AUDIO_BYTES:
                    logger.info("XTTS OK: %s bytes (style=%s, language=%s)", len(resp.content), voice_style, self._xtts_language)
                    return resp.content
                logger.warning("XTTS /tts retornou %s: %s", resp.status_code, resp.text[:100])
        except httpx.ConnectError:
            logger.warning("XTTS indisponível em %s; resposta será texto", self._xtts_url)
        except Exception as e:
            logger.error("XTTS erro: %s", e)
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
        prepared_text = _truncate_for_audio(_normalize_tts_text_ptbr(text), self._max_chars)
        if not prepared_text:
            return None

        if self._engine == "omnivoice":
            audio = await self._synthesize_omnivoice(prepared_text, voice_style)
            if audio:
                return audio
            if self._allow_xtts_pt_fallback:
                return await self._synthesize_xtts(prepared_text, voice_style)
            logger.warning("OmniVoice falhou; fallback XTTS bloqueado para manter pt-BR/SP")
            return None

        if self._engine == "xtts":
            if self._target_is_ptbr() and not self._allow_xtts_pt_fallback:
                logger.warning("XTTS bloqueado como engine primário para pt-BR; tentando OmniVoice")
                return await self._synthesize_omnivoice(prepared_text, voice_style)
            audio = await self._synthesize_xtts(prepared_text, voice_style)
            if audio:
                return audio
            return await self._synthesize_omnivoice(prepared_text, voice_style)

        if self._engine == "chatterbox":
            audio = await self._synthesize_chatterbox(prepared_text, voice_style)
            if audio:
                return audio
            return await self._synthesize_omnivoice(prepared_text, voice_style)

        logger.warning("TTS_ENGINE inválido: %s; tentando OmniVoice", self._engine)
        return await self._synthesize_omnivoice(prepared_text, voice_style)

    async def health(self) -> bool:
        """Verifica se o servidor TTS primário está acessível."""
        if self._engine in {"omnivoice", "chatterbox"}:
            base_url = self._chatterbox_url if self._engine == "chatterbox" else self._omnivoice_url
            path = "/api/model-info" if self._engine == "chatterbox" else "/health"
            info = await self._get_pc1_json(base_url, path, self._engine)
            if not info:
                return False
            if self._engine == "chatterbox" and self._target_is_ptbr():
                languages = info.get("supported_languages")
                return bool(info.get("loaded")) and isinstance(languages, dict) and "pt" in languages
            return bool(info.get("loaded", True))

        try:
            async with httpx.AsyncClient(timeout=3.0) as client:
                resp = await client.get(f"{self._xtts_url}/health")
                return resp.status_code == 200
        except Exception:
            return False


def choose_voice_style(intent: str | None, outcome: str | None) -> str:
    """Seleciona estilo de voz do Will conforme contexto da conversa."""
    # O foco do projeto é sempre manter a persona de influenciador/dono da empresa
    return "influencer"


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
    import re
    text_lower = user_text.lower()
    for kw in _AUDIO_INTENT_KEYWORDS:
        if re.search(r'\b' + re.escape(kw) + r'\b', text_lower):
            return True

    return False


_tts = TTSService()


async def synthesize(text: str, voice_style: str = _DEFAULT_STYLE) -> bytes | None:
    return await _tts.synthesize(text, voice_style)


async def tts_health() -> bool:
    return await _tts.health()
