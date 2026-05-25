#!/usr/bin/env python3
"""
refinar_tts.py — Sintetiza com Chatterbox, transcreve com Whisper, avalia pt-BR.

Uso:
  python3 refinar_tts.py                          # loop interativo completo
  python3 refinar_tts.py "Tá bom, me manda o BTU e a foto."
  python3 refinar_tts.py --loop 20               # bateria automática
  python3 refinar_tts.py --tune                  # comparativo de params
  python3 refinar_tts.py --sample "texto" --save-wav /tmp/out.wav
"""
from __future__ import annotations

import argparse
import asyncio
import difflib
import json
import os
import re
import shlex
import sys
import tempfile
from pathlib import Path

# ── Carrega .env sem dependência externa ─────────────────────────────────────
def _load_dotenv(path: Path = Path(".env")) -> None:
    if not path.exists():
        return
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, val = line.partition("=")
        key = key.strip()
        val = val.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = val

_load_dotenv()

try:
    import httpx
except ImportError:
    import subprocess
    subprocess.run([sys.executable, "-m", "pip", "install", "httpx", "-q"])
    import httpx

# ── Config ────────────────────────────────────────────────────────────────────
ROOT       = Path(__file__).parent
SSH_HOST   = os.getenv("SSH_HOST_PC1", "will-zappro@192.168.15.83")
CHATTERBOX = os.getenv("CHATTERBOX_URL", "http://127.0.0.1:8200")
GROQ_KEY   = os.getenv("GROQ_API_KEY", "")
GROQ_URL   = "https://api.groq.com/openai/v1/audio/transcriptions"
WHISPER    = "whisper-large-v3-turbo"
TTS_TIMEOUT = 60.0
STT_TIMEOUT = 30.0
MIN_AUDIO   = 512

def _ef(name: str, default: float) -> float:
    try:
        return float(os.getenv(name, str(default)).strip())
    except (AttributeError, ValueError):
        return default

def _ei(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, str(default)).strip())
    except (AttributeError, ValueError):
        return default

DEFAULT_PARAMS: dict[str, float | int] = {
    "exaggeration": _ef("TTS_CHATTERBOX_EXAGGERATION", 0.5),
    "cfg_weight":   _ef("TTS_CHATTERBOX_CFG_WEIGHT",   0.70),
    "temperature":  _ef("TTS_CHATTERBOX_TEMPERATURE",  0.75),
    "speed_factor": _ef("TTS_CHATTERBOX_SPEED_FACTOR", 1.05),
    "chunk_size":   _ei("TTS_CHATTERBOX_CHUNK_SIZE",   400),
}

# ── ANSI ──────────────────────────────────────────────────────────────────────
R = "\033[0m"; BOLD = "\033[1m"; DIM = "\033[2m"
CYAN = "\033[96m"; GREEN = "\033[92m"; YELLOW = "\033[93m"
RED = "\033[91m"; MAGENTA = "\033[95m"; BLUE = "\033[94m"

def c(color: str, text: str) -> str:
    return f"{color}{text}{R}"

# ── Corpus WhatsApp pt-BR Refrimix ────────────────────────────────────────────
CORPUS: list[tuple[str, str]] = [
    ("saudacao",    "Oi! Tudo bem? Aqui é o Will da Refrimix."),
    ("saudacao",    "Boa tarde! Pode deixar que a gente resolve pra você."),
    ("preco",       "A instalação de split com acesso simples fica oitocentos reais no Guarujá."),
    ("preco",       "Higienização de split fica duzentos reais por aparelho."),
    ("preco",       "Em Santos, São Vicente e Praia Grande, o valor é de oitocentos e cinquenta reais."),
    ("preco",       "A análise técnica custa cinquenta reais e esse valor abate se você aprovar o orçamento."),
    ("qualificacao","Me manda a BTU e a foto da unidade interna e do quadro de luz pra eu verificar o acesso."),
    ("sigla",       "Qual o BTU do aparelho? Doze mil BTUs cobre bem um quarto de doze metros quadrados."),
    ("sigla",       "VRF e VRV precisam de projeto e não têm preço fechado por WhatsApp."),
    ("qualificacao","Qual é a cidade e o bairro? Preciso confirmar a área de atendimento."),
    ("qualificacao","Quantos aparelhos são e qual é a marca?"),
    ("tecnico",     "Esse caso precisa de análise técnica no local porque é acesso difícil."),
    ("tecnico",     "O programa preventivo inclui laudo P M O C e A R T com registro no C R E A."),
    ("tecnico",     "Se o ar não tá gelando, pode ser filtro sujo, gás baixo ou falha no compressor."),
    ("objecao",     "Entendo que parece caro, mas inclui noventa dias de garantia no serviço."),
    ("objecao",     "No informal você paga menos, mas qualquer problema você paga de novo. Com a gente não."),
    ("agendamento", "A agenda tá enchendo rápido pro verão. Quando você precisa?"),
    ("agendamento", "Pode deixar, a gente encaixa assim que você decidir."),
    ("sotaque",     "Tá, sem problema! Me fala o que você precisa confirmar nesse serviço."),
    ("sotaque",     "A gente atende Guarujá, Santos, São Vicente e Praia Grande."),
    ("sotaque",     "Não tem segredo: manda as fotos que a gente resolve rápido."),
    ("sotaque",     "Fala comigo, posso te ajudar a escolher o equipamento certo pra sua loja."),
]

# ── Normalizador texto TTS ────────────────────────────────────────────────────
_ACRONYM_REPLACEMENTS = {
    # Sem hífen — hífen entre sílabas causa r de ligação no modelo
    "BTU":  "bê tê u",
    "BTUS": "bê tê us",
    "VRF":  "vê erre éfe",
    "VRV":  "vê erre vê",
    "PMOC": "pê ême ô cê",
    "ART":  "a erre tê",
    "CREA": "CREA",
    "HP":   "agá pê",
    "HVAC": "agá vê a cê",
    "API":  "a pê í",
    "IA":   "i á",
    "PIX":  "Pix",
}

def _normalize_tts_text(text: str) -> str:
    n = re.sub(r"https?://\S+|www\.\S+", "link", text.strip(), flags=re.IGNORECASE)
    n = re.sub(r"[*_`#>]+", " ", n)
    # "split" / "split" → "split" (termo técnico consolidado em pt-BR)
    n = re.sub(r"\bsplit[\s\-](?:high|hi)[\s\-]wall\b", "split", n, flags=re.IGNORECASE)
    n = re.sub(r"\b(?:high|hi)[\s\-]wall\b", "split", n, flags=re.IGNORECASE)
    n = re.sub(r"\binverters?\b", "invérter", n, flags=re.IGNORECASE)
    n = re.sub(
        r"\b(BTUS?|VRF|VRV|PMOC|ART|CREA|HP|HVAC|API|IA|PIX)\b",
        lambda m: _ACRONYM_REPLACEMENTS.get(m.group(0).upper(), m.group(0)),
        n, flags=re.IGNORECASE,
    )
    return re.sub(r"\s+", " ", n).strip()

# ── Guardrails pt-BR ──────────────────────────────────────────────────────────
_PTBR_BLOCKED: tuple[tuple[str, str], ...] = (
    (r"\bestou a\s+\w+",                "português europeu: 'estou a ...'"),
    (r"\btelemóvel\b",                   "português europeu: 'telemóvel'"),
    (r"\bcontacto\b",                    "português europeu: 'contacto'"),
    (r"\bmorada\b",                      "português europeu: 'morada'"),
    (r"\bavaria\b",                      "português europeu: 'avaria'"),
    (r"\bfrigorífico\b",                 "português europeu: 'frigorífico'"),
    (r"\bprezad[oa]s?\b",               "formalismo: 'prezado/a'"),
    (r"\batenciosamente\b",              "formalismo: 'atenciosamente'"),
    (r"\b(?:breakdown|budget|labor)\b",  "inglês em cópia"),
)

def _eval_transcription(original: str, transcribed: str) -> tuple[float, list[str], list[str]]:
    orig_norm  = original.lower().strip()
    trans_norm = transcribed.lower().strip()
    orig_words  = orig_norm.split()
    trans_words = trans_norm.split()
    score = difflib.SequenceMatcher(None, orig_words, trans_words).ratio()

    blockers: list[str] = []
    warnings:  list[str] = []

    for pattern, reason in _PTBR_BLOCKED:
        if re.search(pattern, transcribed, flags=re.IGNORECASE):
            blockers.append(reason)

    # Palavras acentuadas do original devem aparecer na transcrição
    accented = re.findall(r"\b\w*[áàãâéêíóôõúç]\w*\b", orig_norm, re.IGNORECASE)
    for word in set(accented):
        if word not in trans_norm and not difflib.get_close_matches(word, trans_words, n=1, cutoff=0.75):
            warnings.append(f"possível erro de pronúncia: '{word}' não encontrado na transcrição")

    if score < 0.6:
        warnings.append(f"similaridade baixa ({score:.0%}) — possível corte ou engasgamento")
    elif score < 0.8:
        warnings.append(f"similaridade parcial ({score:.0%})")

    return score, blockers, warnings

# ── TTS via SSH → Chatterbox PC1 ─────────────────────────────────────────────
_REMOTE_TTS = r"""
import json, sys, requests
d = json.load(sys.stdin)
base = d.pop("_base").rstrip("/")
path = d.pop("_path")
timeout = float(d.pop("_timeout"))
try:
    r = requests.post(f"{base}{path}", json=d, timeout=timeout)
    r.raise_for_status()
except Exception as exc:
    print(str(exc), file=sys.stderr); sys.exit(1)
sys.stdout.buffer.write(r.content)
"""

async def synthesize(text: str, params: dict | None = None) -> bytes | None:
    p = {**DEFAULT_PARAMS, **(params or {})}
    payload: dict = {
        "_base":    CHATTERBOX,
        "_path":    "/tts",
        "_timeout": TTS_TIMEOUT,
        "text":                text if text == _normalize_tts_text(text) else _normalize_tts_text(text),
        "voice_mode":          "clone",
        "reference_audio_filename": "willrefrimix-influencer-v2.wav",
        "output_format":       "wav",
        "language":            "pt",
        "split_text":          True,
        "chunk_size":          int(p["chunk_size"]),
        "temperature":         float(p["temperature"]),
        "exaggeration":        float(p["exaggeration"]),
        "cfg_weight":          float(p["cfg_weight"]),
        "speed_factor":        float(p["speed_factor"]),
    }
    try:
        proc = await asyncio.create_subprocess_exec(
            "/usr/bin/ssh", "-o", "StrictHostKeyChecking=no", SSH_HOST,
            f"python3 -c {shlex.quote(_REMOTE_TTS)}",
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        out, err = await proc.communicate(json.dumps(payload, ensure_ascii=False).encode())
        if proc.returncode != 0:
            print(c(RED, f"  ✗ TTS SSH: {err.decode(errors='replace')[:200]}"))
            return None
        if len(out) < MIN_AUDIO:
            print(c(RED, f"  ✗ TTS bytes insuficientes ({len(out)})"))
            return None
        return out
    except Exception as exc:
        print(c(RED, f"  ✗ TTS exceção: {exc}"))
        return None

# ── STT via Groq Whisper ──────────────────────────────────────────────────────
async def transcribe(audio: bytes) -> str | None:
    if not GROQ_KEY:
        print(c(RED, "  ✗ GROQ_API_KEY não configurado"))
        return None
    try:
        async with httpx.AsyncClient(timeout=STT_TIMEOUT) as client:
            resp = await client.post(
                GROQ_URL,
                headers={"Authorization": f"Bearer {GROQ_KEY}"},
                files={"file": ("audio.wav", audio, "audio/wav")},
                data={"model": WHISPER, "language": "pt", "response_format": "json"},
            )
            resp.raise_for_status()
            text = resp.json().get("text", "").strip()
            return text or None
    except Exception as exc:
        print(c(RED, f"  ✗ Whisper: {exc}"))
        return None

# ── Ciclo completo ────────────────────────────────────────────────────────────
async def run_one(
    text: str,
    params: dict | None = None,
    save_wav: str | None = None,
    verbose: bool = True,
) -> dict:
    if verbose:
        print(c(DIM, f"  ⟳ TTS ({len(text)} chars)..."), end=" ", flush=True)

    audio = await synthesize(text, params)
    if not audio:
        return {"ok": False, "error": "tts_fail", "score": 0.0}

    if verbose:
        print(c(GREEN, f"{len(audio):,} bytes"), end="  ")
        print(c(DIM, "⟳ Whisper..."), end=" ", flush=True)

    if save_wav:
        Path(save_wav).write_bytes(audio)
        if verbose:
            print(c(CYAN, f"→ {save_wav}"), end="  ")

    transcribed = await transcribe(audio)
    if not transcribed:
        if verbose:
            print()
        return {"ok": False, "error": "stt_fail", "score": 0.0, "audio_bytes": len(audio)}

    score, blockers, warnings = _eval_transcription(text, transcribed)
    ok = not blockers and score >= 0.6

    if verbose:
        print()

    return {
        "ok": ok,
        "original":    text,
        "transcribed": transcribed,
        "score":       score,
        "blockers":    blockers,
        "warnings":    warnings,
        "audio_bytes": len(audio),
        "params":      {**DEFAULT_PARAMS, **(params or {})},
    }

# ── Exibição ─────────────────────────────────────────────────────────────────
def show_result(res: dict) -> None:
    if res.get("error"):
        print(c(RED, f"  ✗ erro: {res['error']}"))
        return

    score = res["score"]
    sc = GREEN if score >= 0.8 else (YELLOW if score >= 0.6 else RED)

    print(f"\n  {BOLD}Original:{R}     {res['original']}")
    print(f"  {BOLD}Transcrito:{R}   {c(CYAN, res['transcribed'])}")
    print(f"  {BOLD}Similaridade:{R} {c(sc, f'{score:.0%}')}  ({res['audio_bytes']:,} bytes WAV)")

    for b in res.get("blockers", []):
        print(c(RED,    f"  ✗ BLOQUEIO: {b}"))
    for w in res.get("warnings", []):
        print(c(YELLOW, f"  ⚠ aviso: {w}"))
    if not res.get("blockers") and not res.get("warnings"):
        print(c(GREEN, "  ✓ pt-BR OK"))

    # diff palavra a palavra
    orig_w  = res["original"].lower().split()
    trans_w = res["transcribed"].lower().split()
    problems = [d for d in difflib.ndiff(orig_w, trans_w) if d[:2] in ("- ", "+ ")]
    if problems:
        print(c(DIM, "  diff: " + " ".join(problems[:14])))

# ── Loop automático ───────────────────────────────────────────────────────────
async def run_loop(count: int, params: dict | None = None) -> int:
    print(c(CYAN, f"\nBateria TTS/STT — {count} frases — willrefrimix-influencer\n"))
    results: list[dict] = []

    for i in range(count):
        cat, text = CORPUS[i % len(CORPUS)]
        print(f"{i+1:02d}/{count:02d} [{c(BLUE, cat)}] {text[:70]}")
        res = await run_one(text, params, verbose=True)
        results.append(res)

        score  = res.get("score", 0.0)
        ok     = res.get("ok", False)
        sc     = GREEN if score >= 0.8 else (YELLOW if score >= 0.6 else RED)
        status = c(GREEN, "OK") if ok else c(RED, "FAIL")
        print(f"         [{status}] sim={c(sc, f'{score:.0%}')} "
              f"blk={len(res.get('blockers', []))} wrn={len(res.get('warnings', []))}")
        for b in res.get("blockers", []):
            print(c(RED,    f"         ✗ {b}"))
        for w in (res.get("warnings", []) if not res.get("blockers") else [])[:2]:
            print(c(YELLOW, f"         ⚠ {w}"))
        print()

    ok_n   = sum(1 for r in results if r.get("ok"))
    avg    = sum(r.get("score", 0.0) for r in results) / max(len(results), 1)
    blk_n  = sum(len(r.get("blockers", [])) for r in results)
    wrn_n  = sum(len(r.get("warnings", [])) for r in results)
    col    = GREEN if ok_n == count else (YELLOW if ok_n >= count * 0.8 else RED)
    avc    = GREEN if avg >= 0.8 else YELLOW

    print(f"{BOLD}Resultado:{R} {c(col, f'{ok_n}/{count} OK')}  "
          f"sim média={c(avc, f'{avg:.0%}')}  bloqueios={blk_n}  avisos={wrn_n}")
    return 0 if ok_n == count else 1

# ── Modo tune ─────────────────────────────────────────────────────────────────
async def run_tune(text: str) -> None:
    variations: list[tuple[str, dict]] = [
        ("atual (padrão env)",       {}),
        ("exag=0.3 cfg=0.3 seed=42", {"exaggeration": 0.3, "cfg_weight": 0.3, "speed_factor": 1.0}),
        ("exag=0.5 cfg=0.35",        {"exaggeration": 0.5, "cfg_weight": 0.35}),
        ("exag=0.65 expressivo",     {"exaggeration": 0.65, "cfg_weight": 0.3}),
        ("rápido speed=1.15",        {"speed_factor": 1.15}),
        ("chunk=200 (frases)",       {"chunk_size": 200}),
    ]

    print(c(CYAN, f"\nTune — \"{text}\"\n"))
    rows: list[tuple[str, dict, str]] = []

    for label, p in variations:
        print(c(DIM, f"  ▶ {label}..."), end=" ", flush=True)
        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
            wav = f.name
        res = await run_one(text, p, save_wav=wav, verbose=False)
        score = res.get("score", 0.0)
        sc = GREEN if score >= 0.8 else (YELLOW if score >= 0.6 else RED)
        blk = len(res.get("blockers", []))
        wrn = len(res.get("warnings", []))
        print(f"sim={c(sc, f'{score:.0%}')}  {res.get('audio_bytes', 0):,}b  blk={blk}  wrn={wrn}")
        rows.append((label, res, wav))

    print(f"\n{BOLD}WAVs para escutar:{R}")
    for label, _, wav in rows:
        print(f"  aplay {wav}   # {label}")

    best_label, best_res, _ = max(rows, key=lambda x: x[1].get("score", 0))
    print(c(GREEN, f"\n  Melhor: {best_label} (sim={best_res.get('score', 0):.0%})"))

# ── Menu interativo ───────────────────────────────────────────────────────────
async def run_interactive() -> None:
    print(c(DIM, f"  SSH: {SSH_HOST}  Chatterbox: {CHATTERBOX}"))
    p = DEFAULT_PARAMS
    print(c(DIM, f"  Params: exag={p['exaggeration']} cfg={p['cfg_weight']} "
                 f"temp={p['temperature']} speed={p['speed_factor']} chunk={p['chunk_size']}\n"))

    custom: dict = {}

    while True:
        print(f"{BOLD}Frase{R} (ou {c(CYAN,'tune')} / {c(CYAN,'params')} / "
              f"{c(CYAN,'loop')} / {c(CYAN,'sair')}):")
        text = input(f"  {BOLD}>{R} ").strip()

        if text.lower() in ("sair", "exit", "q"):
            break

        if text.lower() == "loop":
            raw = input(c(DIM, "  Quantas frases? [20] ")).strip()
            await run_loop(int(raw) if raw.isdigit() else 20, custom or None)
            continue

        if text.lower() == "tune":
            sample = input(c(DIM, "  Texto para comparar: ")).strip()
            if sample:
                await run_tune(sample)
            continue

        if text.lower() == "params":
            print(c(DIM, "  Ex: exaggeration=0.4,speed_factor=1.0  (Enter = reset)"))
            raw = input(f"  {BOLD}>{R} ").strip()
            if not raw:
                custom = {}
                print(c(GREEN, "  ✓ Params resetados"))
            else:
                for pair in raw.split(","):
                    if "=" in pair:
                        k, _, v = pair.partition("=")
                        k = k.strip()
                        try:
                            custom[k] = int(v.strip()) if k == "chunk_size" else float(v.strip())
                        except ValueError:
                            print(c(YELLOW, f"  ⚠ ignorado: {pair}"))
                print(c(GREEN, f"  ✓ Custom: {custom}"))
            continue

        if not text:
            continue

        raw_wav = input(c(DIM, "  Salvar WAV? (Enter=não / 'tmp' / caminho): ")).strip()
        wav_path: str | None = None
        if raw_wav == "tmp":
            with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
                wav_path = f.name
        elif raw_wav:
            wav_path = raw_wav

        res = await run_one(text, custom or None, save_wav=wav_path)
        show_result(res)
        if wav_path and res.get("audio_bytes"):
            print(c(CYAN, f"\n  WAV → {wav_path}"))
            print(c(DIM,  f"  Escute: aplay {wav_path}"))
        print()

# ── CLI ───────────────────────────────────────────────────────────────────────
def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Refinador TTS — Chatterbox + Whisper pt-BR")
    p.add_argument("text", nargs="*", help="Frase única para testar.")
    p.add_argument("--loop",  type=int, default=0, metavar="N")
    p.add_argument("--tune",  action="store_true")
    p.add_argument("--sample", default="", metavar="TEXT")
    p.add_argument("--save-wav", default="", metavar="PATH")
    p.add_argument("--exaggeration", type=float, default=None)
    p.add_argument("--cfg-weight",   type=float, default=None)
    p.add_argument("--temperature",  type=float, default=None)
    p.add_argument("--speed-factor", type=float, default=None)
    p.add_argument("--chunk-size",   type=int,   default=None)
    return p


async def _main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv if argv is not None else sys.argv[1:])

    override: dict = {}
    if args.exaggeration is not None: override["exaggeration"] = args.exaggeration
    if args.cfg_weight    is not None: override["cfg_weight"]   = args.cfg_weight
    if args.temperature   is not None: override["temperature"]  = args.temperature
    if args.speed_factor  is not None: override["speed_factor"] = args.speed_factor
    if args.chunk_size    is not None: override["chunk_size"]   = args.chunk_size

    print(f"\n{BOLD}{MAGENTA}╔═══════════════════════════════════════════════╗{R}")
    print(f"{BOLD}{MAGENTA}║  Refinador TTS — willrefrimix-influencer pt-BR ║{R}")
    print(f"{BOLD}{MAGENTA}╚═══════════════════════════════════════════════╝{R}\n")

    if args.tune:
        sample = args.sample or (" ".join(args.text) if args.text else "")
        if not sample:
            sample = input(c(DIM, "  Texto para comparar variações: ")).strip()
        if sample:
            await run_tune(sample)
        return 0

    if args.loop:
        return await run_loop(args.loop, override or None)

    if args.text:
        text = " ".join(args.text)
        res  = await run_one(text, override or None, save_wav=args.save_wav or None)
        show_result(res)
        if args.save_wav and res.get("audio_bytes"):
            print(c(CYAN, f"\n  WAV → {args.save_wav}"))
            print(c(DIM,  f"  Escute: aplay {args.save_wav}"))
        return 0 if res.get("ok") else 1

    await run_interactive()
    return 0


def main(argv: list[str] | None = None) -> int:
    return asyncio.run(_main(argv))


if __name__ == "__main__":
    raise SystemExit(main())
