from __future__ import annotations

import argparse
import asyncio
import base64
import concurrent.futures
import json
import os
import subprocess
import sys
import time
import uuid
from dataclasses import dataclass
from typing import Any, Callable

import httpx

DEFAULT_WEBHOOK_URL = os.getenv("SRE_WEBHOOK_URL", "http://localhost:8000/webhook/evolution")
DEFAULT_EVOLUTION_URL = os.getenv("EVOLUTION_API_URL", "http://localhost:8080")
DEFAULT_INSTANCE = os.getenv("EVOLUTION_INSTANCE", "RefrimixLead")
DEFAULT_PHONE = os.getenv("SRE_TEST_PHONE", os.getenv("OWNER_PHONE", "5513999999999"))
DEFAULT_FASTAPI_URL = os.getenv("SRE_FASTAPI_URL", "http://localhost:8000")
DEFAULT_PC1_SSH_HOST = os.getenv("SSH_HOST_PC1", "will-zappro@192.168.15.83")
DEFAULT_OMNIVOICE_URL = os.getenv("OMNIVOICE_URL", "http://127.0.0.1:8202")
DEFAULT_CHATTERBOX_URL = os.getenv("CHATTERBOX_URL", "http://127.0.0.1:8200")
DEFAULT_TTS_SAMPLE = (
    "Opa, aqui é o Will da Refrimix. Instalação padrão fica R$ 850,00 em 3x no Pix. "
    "Me passa a cidade e a BTU do equipamento?"
)

AUDIO_URL = os.getenv(
    "SRE_AUDIO_URL",
    "https://upload.wikimedia.org/wikipedia/commons/c/c8/Example.ogg",
)
IMAGE_URL = os.getenv(
    "SRE_IMAGE_URL",
    "https://upload.wikimedia.org/wikipedia/commons/thumb/1/17/"
    "Air_Conditioner_-_Window_Type.jpg/320px-Air_Conditioner_-_Window_Type.jpg",
)
ONE_SECOND_WAV_B64 = "UklGRjIAAABXQVZFZm10IBAAAAABAAEAQB8AAEAfAAABAAgAAABmYWN0BAAAAAAAAABkYXRhAAAAAA=="


@dataclass(frozen=True)
class ProbeResult:
    name: str
    status_code: int
    body: str
    latency_seconds: float

    @property
    def ok(self) -> bool:
        return 200 <= self.status_code < 300


def build_webhook_payload(
    msg_type: str,
    *,
    phone: str = DEFAULT_PHONE,
    instance: str = DEFAULT_INSTANCE,
    content: str | None = None,
    msg_id: str | None = None,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "instance": instance,
        "data": {
            "key": {
                "remote": f"{phone}@s.whatsapp.net",
                "id": msg_id or str(uuid.uuid4()),
                "fromMe": False,
            },
            "messageType": msg_type,
            "message": {},
        },
    }

    if msg_type == "conversation":
        payload["data"]["message"]["conversation"] = content or "Teste operacional SRE."
    elif msg_type == "audioMessage":
        payload["data"]["message"]["audioMessage"] = {"url": AUDIO_URL}
    elif msg_type == "imageMessage":
        payload["data"]["message"]["imageMessage"] = {"url": IMAGE_URL, "caption": content or ""}
    else:
        raise ValueError(f"Tipo de mensagem nao suportado: {msg_type}")

    return payload


def _response_body(response: httpx.Response) -> str:
    try:
        return str(response.json())
    except ValueError:
        return response.text


def post_json(name: str, url: str, payload: dict[str, Any], *, headers: dict[str, str] | None = None, timeout: float) -> ProbeResult:
    started = time.perf_counter()
    try:
        with httpx.Client(timeout=timeout) as client:
            response = client.post(url, json=payload, headers=headers)
        return ProbeResult(name, response.status_code, _response_body(response), time.perf_counter() - started)
    except Exception as exc:
        return ProbeResult(name, 0, f"{type(exc).__name__}: {exc}", time.perf_counter() - started)


def get_url(name: str, url: str, *, timeout: float) -> ProbeResult:
    started = time.perf_counter()
    try:
        with httpx.Client(timeout=timeout) as client:
            response = client.get(url)
        return ProbeResult(name, response.status_code, _response_body(response), time.perf_counter() - started)
    except Exception as exc:
        return ProbeResult(name, 0, f"{type(exc).__name__}: {exc}", time.perf_counter() - started)


def ssh_curl(name: str, ssh_host: str, url: str, *, timeout: float) -> ProbeResult:
    started = time.perf_counter()
    command = f"curl -fsS --max-time {max(int(timeout), 1)} {url}"
    try:
        completed = subprocess.run(
            ["ssh", "-o", "StrictHostKeyChecking=no", ssh_host, command],
            check=False,
            capture_output=True,
            text=True,
            timeout=timeout + 5,
        )
    except Exception as exc:
        return ProbeResult(name, 0, f"{type(exc).__name__}: {exc}", time.perf_counter() - started)

    body = completed.stdout.strip() or completed.stderr.strip()
    return ProbeResult(name, 200 if completed.returncode == 0 else 0, body[:2000], time.perf_counter() - started)


def ssh_command(name: str, ssh_host: str, command: str, *, timeout: float) -> ProbeResult:
    started = time.perf_counter()
    try:
        completed = subprocess.run(
            ["ssh", "-o", "StrictHostKeyChecking=no", ssh_host, command],
            check=False,
            capture_output=True,
            text=True,
            timeout=timeout + 5,
        )
    except Exception as exc:
        return ProbeResult(name, 0, f"{type(exc).__name__}: {exc}", time.perf_counter() - started)

    body = completed.stdout.strip() or completed.stderr.strip()
    return ProbeResult(name, 200 if completed.returncode == 0 else 0, body[:2000], time.perf_counter() - started)


def print_result(result: ProbeResult) -> None:
    status = "OK" if result.ok else "FAIL"
    print(f"[{status}] {result.name}: status={result.status_code} latency={result.latency_seconds:.3f}s body={result.body}")


def run_webhook_smoke(args: argparse.Namespace) -> int:
    probes = [
        ("conversation", build_webhook_payload("conversation", phone=args.phone, instance=args.instance, content=args.message)),
        ("audioMessage", build_webhook_payload("audioMessage", phone=args.phone, instance=args.instance)),
        ("imageMessage", build_webhook_payload("imageMessage", phone=args.phone, instance=args.instance, content=args.caption)),
    ]

    results = [
        post_json(name, args.webhook_url, payload, timeout=args.timeout)
        for name, payload in probes
    ]
    for result in results:
        print_result(result)
        if args.delay:
            time.sleep(args.delay)

    return 0 if all(result.ok for result in results) else 1


def run_webhook_stress(args: argparse.Namespace) -> int:
    def make_payload(index: int) -> tuple[str, dict[str, Any]]:
        if index % 5 == 0:
            return f"audio-{index}", build_webhook_payload("audioMessage", phone=args.phone, instance=args.instance)
        if index % 5 == 1:
            return f"image-{index}", build_webhook_payload(
                "imageMessage",
                phone=args.phone,
                instance=args.instance,
                content=f"Probe SRE imagem #{index}",
            )
        return f"text-{index}", build_webhook_payload(
            "conversation",
            phone=args.phone,
            instance=args.instance,
            content=f"Probe SRE carga #{index}",
        )

    payloads = [make_payload(index) for index in range(args.requests)]
    started = time.perf_counter()

    with concurrent.futures.ThreadPoolExecutor(max_workers=args.concurrency) as executor:
        futures = [
            executor.submit(post_json, name, args.webhook_url, payload, timeout=args.timeout)
            for name, payload in payloads
        ]
        results = [future.result() for future in concurrent.futures.as_completed(futures)]

    total_time = max(time.perf_counter() - started, 0.001)
    successes = sum(1 for result in results if result.ok)
    failures = len(results) - successes
    avg_latency = sum(result.latency_seconds for result in results) / len(results) if results else 0.0

    print(f"requests={len(results)} concurrency={args.concurrency} total={total_time:.2f}s rps={len(results) / total_time:.2f}")
    print(f"success={successes} failures={failures} avg_latency={avg_latency:.3f}s")
    for result in sorted((item for item in results if not item.ok), key=lambda item: item.name):
        print_result(result)

    return 0 if failures == 0 else 1


def run_evolution_audio(args: argparse.Namespace) -> int:
    api_key = args.api_key or os.getenv("EVOLUTION_API_KEY") or os.getenv("AUTHENTICATION_API_KEY")
    if not api_key:
        print("EVOLUTION_API_KEY ou AUTHENTICATION_API_KEY precisa estar configurada.", file=sys.stderr)
        return 2

    audio = args.audio_b64 or ONE_SECOND_WAV_B64
    try:
        base64.b64decode(audio, validate=True)
    except Exception as exc:
        print(f"Audio base64 invalido: {exc}", file=sys.stderr)
        return 2

    headers = {"apikey": api_key, "Content-Type": "application/json"}
    base_url = args.evolution_url.rstrip("/")
    probes = [
        (
            "sendWhatsAppAudio",
            f"{base_url}/message/sendWhatsAppAudio/{args.instance}",
            {"number": args.phone, "audio": audio},
        ),
        (
            "sendMedia",
            f"{base_url}/message/sendMedia/{args.instance}",
            {"number": args.phone, "mediatype": "audio", "mimetype": "audio/mp4", "media": audio},
        ),
    ]
    results = [
        post_json(name, url, payload, headers=headers, timeout=args.timeout)
        for name, url, payload in probes
    ]
    for result in results:
        print_result(result)

    return 0 if all(result.ok for result in results) else 1


def _chatterbox_supports_pt(body: str) -> bool:
    try:
        info = json.loads(body)
    except ValueError:
        return False
    languages = info.get("supported_languages") or {}
    return bool(info.get("supports_multilingual")) and "pt" in languages


def run_tts_audit(args: argparse.Namespace) -> int:
    fastapi_url = args.fastapi_url.rstrip("/")
    omnivoice_url = args.omnivoice_url.rstrip("/")
    chatterbox_url = args.chatterbox_url.rstrip("/")

    results = [
        get_url("pc2-fastapi-health", f"{fastapi_url}/health", timeout=args.timeout),
        get_url("pc2-bot-status", f"{fastapi_url}/bot/status", timeout=args.timeout),
    ]

    if not args.skip_pc1:
        results.extend(
            [
                ssh_curl("pc1-omnivoice-health", args.pc1_ssh_host, f"{omnivoice_url}/health", timeout=args.timeout),
                ssh_curl("pc1-chatterbox-model", args.pc1_ssh_host, f"{chatterbox_url}/api/model-info", timeout=args.timeout),
                ssh_curl("pc1-chatterbox-voices", args.pc1_ssh_host, f"{chatterbox_url}/v1/audio/voices", timeout=args.timeout),
                ssh_command(
                    "pc1-tts-voice-files",
                    args.pc1_ssh_host,
                    "find /srv/data/tts/voices -maxdepth 1 -type f -name '*.wav' | sort | wc -l",
                    timeout=args.timeout,
                ),
            ]
        )

    for result in results:
        print_result(result)

    failures = [result for result in results if not result.ok]
    model_result = next((result for result in results if result.name == "pc1-chatterbox-model"), None)
    if model_result and model_result.ok and not _chatterbox_supports_pt(model_result.body):
        print("[WARN] pc1-chatterbox-model: Chatterbox local nao esta em modo multilingual/pt; nao use como fallback pt-BR.")
        if args.require_chatterbox_pt:
            failures.append(model_result)

    if args.synthesize:
        from agent_graph.services.tts import TTSService

        audio = asyncio.run(TTSService().synthesize(args.sample_text, "influencer"))
        if audio and len(audio) > 512:
            print(f"[OK] tts-synthesize: bytes={len(audio)}")
        else:
            print("[FAIL] tts-synthesize: sem audio valido")
            return 1

    return 0 if not failures else 1


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="SRE probes for WhatsApp RAG runtime checks.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    def add_common_webhook_options(command: argparse.ArgumentParser) -> None:
        command.add_argument("--webhook-url", default=DEFAULT_WEBHOOK_URL)
        command.add_argument("--instance", default=DEFAULT_INSTANCE)
        command.add_argument("--phone", default=DEFAULT_PHONE)
        command.add_argument("--timeout", type=float, default=10.0)

    smoke = subparsers.add_parser("webhook-smoke", help="Send one webhook payload per supported modality.")
    add_common_webhook_options(smoke)
    smoke.add_argument("--message", default="Ola, gostaria de fazer um orcamento de higienizacao.")
    smoke.add_argument("--caption", default="Da uma olhada em como esta esse ar.")
    smoke.add_argument("--delay", type=float, default=1.0)
    smoke.set_defaults(func=run_webhook_smoke)

    stress = subparsers.add_parser("webhook-stress", help="Run concurrent webhook load probe.")
    add_common_webhook_options(stress)
    stress.add_argument("--requests", type=int, default=30)
    stress.add_argument("--concurrency", type=int, default=10)
    stress.set_defaults(func=run_webhook_stress)

    audio = subparsers.add_parser("evolution-audio", help="Probe Evolution audio sending endpoints.")
    audio.add_argument("--evolution-url", default=DEFAULT_EVOLUTION_URL)
    audio.add_argument("--instance", default=DEFAULT_INSTANCE)
    audio.add_argument("--phone", default=DEFAULT_PHONE)
    audio.add_argument("--api-key", default="")
    audio.add_argument("--audio-b64", default="")
    audio.add_argument("--timeout", type=float, default=10.0)
    audio.set_defaults(func=run_evolution_audio)

    tts = subparsers.add_parser("tts-audit", help="Audit PC2 FastAPI and PC1 TTS services without sending WhatsApp.")
    tts.add_argument("--fastapi-url", default=DEFAULT_FASTAPI_URL)
    tts.add_argument("--pc1-ssh-host", default=DEFAULT_PC1_SSH_HOST)
    tts.add_argument("--omnivoice-url", default=DEFAULT_OMNIVOICE_URL)
    tts.add_argument("--chatterbox-url", default=DEFAULT_CHATTERBOX_URL)
    tts.add_argument("--timeout", type=float, default=5.0)
    tts.add_argument("--skip-pc1", action="store_true")
    tts.add_argument("--require-chatterbox-pt", action="store_true")
    tts.add_argument("--synthesize", action="store_true")
    tts.add_argument("--sample-text", default=DEFAULT_TTS_SAMPLE)
    tts.set_defaults(func=run_tts_audit)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    func: Callable[[argparse.Namespace], int] = args.func
    return func(args)


if __name__ == "__main__":
    raise SystemExit(main())
