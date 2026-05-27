#!/usr/bin/env python3
"""
backup_before_clean_state.py

Faz backup obrigatório antes de qualquer limpeza de estado operacional.
Backup PostgreSQL + export tabelas operacionais + snapshot Redis + info Qdrant.

Uso:
    python scripts/backup_before_clean_state.py

Exit code 0 = backup criado com sucesso.
Exit code 1 = falha no backup — NÃO prosseguir com limpeza.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
from datetime import datetime
from pathlib import Path

# ── helpers ──────────────────────────────────────────────────────────────────

def run_cmd(cmd: list[str], capture: bool = True, timeout: int = 120, env: dict | None = None) -> tuple[int, str, str]:
    """Executa comando shell. Returns (exit_code, stdout, stderr)."""
    full_env = os.environ.copy()
    if env:
        full_env.update(env)
    try:
        result = subprocess.run(cmd, capture_output=capture, text=True, timeout=timeout, env=full_env)
        return result.returncode, result.stdout or "", result.stderr or ""
    except Exception as e:
        return 1, "", str(e)


def load_env() -> dict:
    """Carrega .env do projeto."""
    env_path = Path(__file__).parent.parent / ".env"
    env = {}
    if env_path.exists():
        for line in env_path.read_text().splitlines():
            if "=" in line and not line.startswith("#"):
                key, _, val = line.partition("=")
                env[key.strip()] = val.strip()
    return env


def _parse_postgres_url(db_url: str) -> dict:
    """Parse postgresql://user:***@host:port/dbname."""
    addr = db_url.replace("postgresql://", "")
    user_part = addr.split("@")[0] if "@" in addr else ""
    host_part = addr.split("@")[1] if "@" in addr else addr
    if "/" in host_part:
        host_port = host_part.split("/")[0]
        dbname = host_part.split("/")[1].split("?")[0]
    else:
        host_port = host_part
        dbname = "whatsapp_rag"
    user = user_part.split(":")[0] if user_part else "postgres"
    password = user_part.split(":")[1] if ":" in user_part else ""
    pg_host = host_port.split(":")[0]
    pg_port = host_port.split(":")[1] if ":" in host_port else "5432"
    return {"user": user, "password": password, "host": pg_host, "port": pg_port, "dbname": dbname}


# ── backup PostgreSQL ─────────────────────────────────────────────────────────

def backup_postgres(env: dict, backup_subdir: Path) -> dict:
    """Faz pg_dump do banco whatsapp_rag."""
    db_url = env.get("DATABASE_URL", "")
    if not db_url or "{SECRET}" in db_url:
        return {"status": "skipped", "reason": "DATABASE_URL placeholder"}

    parsed = _parse_postgres_url(db_url)
    pg_env = os.environ.copy()
    if parsed["password"] and parsed["password"] != "***":
        pg_env["PGPASSWORD"] = parsed["password"]

    # pg_dump custom format
    dump_path = backup_subdir / "whatsapp_rag.dump"
    cmd_dump = [
        "pg_dump", "-h", parsed["host"], "-p", parsed["port"],
        "-U", parsed["user"], "-d", parsed["dbname"],
        "-Fc", "-f", str(dump_path),
    ]
    code, _, stderr = run_cmd(cmd_dump, env=pg_env, timeout=180)
    if code == 0:
        return {"status": "ok", "path": str(dump_path), "format": "custom"}
    # Fallback: plain SQL
    plain_path = backup_subdir / "whatsapp_rag.sql"
    cmd_plain = [
        "pg_dump", "-h", parsed["host"], "-p", parsed["port"],
        "-U", parsed["user"], "-d", parsed["dbname"],
        "-f", str(plain_path),
    ]
    code2, _, _ = run_cmd(cmd_plain, env=pg_env, timeout=180)
    if code2 == 0:
        return {"status": "partial", "path": str(plain_path), "note": "plain SQL fallback"}
    return {"status": "error", "reason": stderr.strip()[:200]}


# ── export tabelas operacionais ────────────────────────────────────────────────

def export_postgres_operational_tables(env: dict, backup_subdir: Path) -> dict:
    """Exporta cada tabela operacional para .jsonl."""
    db_url = env.get("DATABASE_URL", "")
    if not db_url or "{SECRET}" in db_url:
        return {}

    parsed = _parse_postgres_url(db_url)
    pg_env = os.environ.copy()
    if parsed["password"] and parsed["password"] != "***":
        pg_env["PGPASSWORD"] = parsed["password"]

    tables = [
        "review_items", "production_feedback", "lead_outcomes",
        "whatsapp_status", "bot_decisions", "pending_jobs",
        "conversations", "messages", "lead_state",
        "idempotency_keys", "tts_cache_metadata", "conversation_metrics",
    ]

    results = {}
    for table in tables:
        out_path = backup_subdir / f"{table}.jsonl"
        cmd = [
            "psql", "-h", parsed["host"], "-p", parsed["port"],
            "-U", parsed["user"], "-d", parsed["dbname"],
            "-t", "-c", f"COPY {table} TO STDOUT WITH (FORMAT CSV, HEADER true);",
        ]
        code, stdout, stderr = run_cmd(cmd, env=pg_env)
        if code == 0 and stdout.strip():
            out_path.write_text(stdout.strip())
            results[table] = {"status": "ok", "rows": len(stdout.strip().splitlines())}
        else:
            results[table] = {"status": "empty", "reason": (stderr or "no data")[:80]}

    return results


# ── backup Redis ──────────────────────────────────────────────────────────────

def backup_redis(env: dict) -> dict:
    """Lista chaves Redis por prefixo — sem vazar conteúdo."""
    redis_url = env.get("REDIS_URL", "")
    if not redis_url or "{SECRET}" in redis_url:
        return {"status": "skipped", "reason": "REDIS_URL placeholder"}

    try:
        addr = redis_url.replace("redis://", "")
        host_part = addr.split("@")[1] if "@" in addr else addr
        host_port = host_part.rstrip("/")
        host = host_port.split(":")[0]
        port = host_port.split(":")[1] if ":" in host_port else "6379"
    except Exception as e:
        return {"status": "error", "reason": str(e)}

    prefixes = [
        "lead:", "conversation:", "review:", "debounce:", "whatsapp:",
        "tts:", "queue:", "idempotency:", "assisted:", "refrimix:",
    ]

    results = {}
    for prefix in prefixes:
        cmd = ["redis-cli", "-h", host, "-p", port, "--no-raw", "DBSIZE"]
        code, stdout, _ = run_cmd(cmd)
        results[prefix] = {"status": "ok", "dbsize": stdout.strip() if code == 0 else "unknown"}

    return results


# ── info Qdrant ───────────────────────────────────────────────────────────────

def info_qdrant(env: dict) -> dict:
    """Lista collections Qdrant e counts."""
    import urllib.request

    qdrant_url = env.get("QDRANT_URL", "http://localhost:6333")
    if not qdrant_url or "{SECRET}" in qdrant_url:
        return {"status": "skipped"}

    try:
        req = urllib.request.Request(f"{qdrant_url}/collections")
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read())
        collections = data.get("result", {}).get("collections", [])
        results = []
        for col in collections:
            name = col.get("name", "")
            try:
                count_req = urllib.request.Request(
                    f"{qdrant_url}/collections/{name}/points/count",
                    data=json.dumps({"exact": False}).encode(),
                    headers={"Content-Type": "application/json"},
                )
                with urllib.request.urlopen(count_req, timeout=10) as cr:
                    count = json.loads(cr.read()).get("result", {}).get("count", 0)
            except Exception:
                count = "unknown"
            results.append({"name": name, "points": count})
        return {"status": "ok", "collections": results}
    except Exception as e:
        return {"status": "error", "reason": str(e)}


# ── main ─────────────────────────────────────────────────────────────────────

def main():
    print("=" * 60)
    print("Backup antes da limpeza — Phase 2.10")
    print("=" * 60)

    ts = datetime.now().strftime("%Y%m%d-%H%M%S")
    backup_dir = Path(os.environ.get("BACKUP_DIR", "/tmp/refrimix-backups"))
    backup_subdir = backup_dir / f"refrimix-clean-state-{ts}"
    backup_subdir.mkdir(parents=True, exist_ok=True)

    env = load_env()

    print(f"\n📁 Backup dir: {backup_subdir}")

    print("\n[1/4] PostgreSQL pg_dump...")
    pg_result = backup_postgres(env, backup_subdir)
    print(f"  → {pg_result.get('status', 'error')}")

    print("\n[2/4] Exportar tabelas operacionais...")
    pg_tables = export_postgres_operational_tables(env, backup_subdir)
    exported = [t for t, r in pg_tables.items() if r.get("status") == "ok"]
    print(f"  → {len(exported)}/{len(pg_tables)} tables exported")

    print("\n[3/4] Redis key counts...")
    redis_result = backup_redis(env)
    print(f"  → {redis_result.get('status', 'error')}")

    print("\n[4/4] Qdrant collections...")
    qdrant_result = info_qdrant(env)
    print(f"  → {qdrant_result.get('status', 'error')}")

    # Salva relatório JSON
    report = {
        "timestamp": ts,
        "backup_dir": str(backup_subdir),
        "postgres": pg_result,
        "postgres_tables": pg_tables,
        "redis": redis_result,
        "qdrant": qdrant_result,
    }

    report_path = backup_subdir / "backup_report.json"
    report_path.write_text(json.dumps(report, indent=2, ensure_ascii=False))
    print(f"\n📄 Relatório: {report_path}")

    # Verifica se backup principal funcionou
    if pg_result.get("status") not in ("ok", "partial"):
        print("\n❌ BACKUP FALHOU — não prosseguir com limpeza.")
        sys.exit(1)

    print("\n✅ Backup concluído com sucesso.")
    sys.exit(0)


if __name__ == "__main__":
    main()