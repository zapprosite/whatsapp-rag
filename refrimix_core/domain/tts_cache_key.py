"""TTS Cache Key Generator.

Generates deterministic cache keys for synthesized audio.
Format: tts:{engine}:{voice}:{speed}:{sha256(normalized_text)}

Normalized text: lowercase, stripped, collapsed whitespace.
Cache entry stores WAV 16kHz mono + metadata.
"""

import hashlib
import os
import time
from dataclasses import dataclass
from pathlib import Path

import json  # noqa: F401 - kept for cache entry compatibility


TTS_CACHE_DIR = Path(os.getenv("TTS_CACHE_DIR", "/tmp/refrimix_tts_cache"))
TTS_CACHE_TTL_SECONDS = int(os.getenv("TTS_CACHE_TTL_SECONDS", "604800"))  # 7 days


def _normalize_for_cache(text: str) -> str:
    """Normalize text for consistent cache key across variations."""
    return " ".join(text.lower().strip().split())


def make_cache_key(engine: str, voice: str, speed: str, text: str) -> str:
    """Generate a deterministic cache key for TTS audio.

    Args:
        engine: tts engine name (edge, chatterbox, omnivoice)
        voice: voice identifier (e.g. pt-BR-ThalitaMultilingualNeural)
        speed: speed string (e.g. +0%, +10%)
        text: raw input text

    Returns:
        Cache key string: tts:{engine}:{voice}:{speed}:{sha256}
    """
    normalized = _normalize_for_cache(text)
    hash_digest = hashlib.sha256(normalized.encode("utf-8")).hexdigest()[:32]
    return f"tts:{engine}:{voice}:{speed}:{hash_digest}"


@dataclass(frozen=True)
class CacheEntry:
    """Cache entry metadata stored alongside the WAV file as .meta.json."""
    wav_path: str
    engine: str
    voice: str
    speed: str
    text_hash: str
    char_count: int
    duration_ms: int
    created_at: float  # unix timestamp


def cache_get(
    engine: str,
    voice: str,
    speed: str,
    text: str,
) -> CacheEntry | None:
    """Retrieve cached TTS entry if exists and not expired.

    Returns None if cache miss or TTL expired.
    """
    key = make_cache_key(engine, voice, speed, text)
    wav_path = TTS_CACHE_DIR / f"{key}.wav"
    meta_path = TTS_CACHE_DIR / f"{key}.meta.json"

    if not meta_path.exists():
        return None

    try:
        with open(meta_path, "r", encoding="utf-8") as f:
            import json
            meta = json.load(f)
    except (OSError, ValueError):
        return None

    # TTL check
    if time.time() - meta.get("created_at", 0) > TTS_CACHE_TTL_SECONDS:
        # Expired — clean up
        for p in (wav_path, meta_path):
            p.unlink(missing_ok=True)
        return None

    if not wav_path.exists():
        return None

    return CacheEntry(
        wav_path=str(wav_path),
        engine=meta["engine"],
        voice=meta["voice"],
        speed=meta["speed"],
        text_hash=meta["text_hash"],
        char_count=meta["char_count"],
        duration_ms=meta["duration_ms"],
        created_at=meta["created_at"],
    )


def cache_put(
    engine: str,
    voice: str,
    speed: str,
    text: str,
    wav_path: str,
    duration_ms: int,
) -> CacheEntry:
    """Store TTS result in cache with metadata.

    Args:
        engine: tts engine name
        voice: voice used
        speed: speed string
        text: original text
        wav_path: path to synthesized WAV file (moved into cache)
        duration_ms: audio duration in milliseconds

    Returns:
        CacheEntry with stored paths
    """
    key = make_cache_key(engine, voice, speed, text)
    normalized = _normalize_for_cache(text)
    text_hash = hashlib.sha256(normalized.encode("utf-8")).hexdigest()[:32]

    TTS_CACHE_DIR.mkdir(parents=True, exist_ok=True)

    cached_wav = TTS_CACHE_DIR / f"{key}.wav"
    meta_path = TTS_CACHE_DIR / f"{key}.meta.json"

    # Move WAV into cache
    Path(wav_path).rename(cached_wav)

    entry = CacheEntry(
        wav_path=str(cached_wav),
        engine=engine,
        voice=voice,
        speed=speed,
        text_hash=text_hash,
        char_count=len(text),
        duration_ms=duration_ms,
        created_at=time.time(),
    )

    with open(meta_path, "w", encoding="utf-8") as f:
        import json
        json.dump(
            {
                "engine": entry.engine,
                "voice": entry.voice,
                "speed": entry.speed,
                "text_hash": entry.text_hash,
                "char_count": entry.char_count,
                "duration_ms": entry.duration_ms,
                "created_at": entry.created_at,
            },
            f,
        )

    return entry
