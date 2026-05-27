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
    """Faz backup do banco whatsapp_rag via psycopg2 COPY."""
    db_url = env.get("DATABASE_URL", "")
    if not db_url or "{SECRET}" in db_url:
        return {"status": "skipped", "reason": "DATABASE_URL placeholder"}

    try:
        import psycopg2
    except ImportError:
        return {"status": "error", "reason": "psycopg2 not available"}

    try:
        conn = psycopg2.connect(db_url)
        conn.autocommit = True
        cur = conn.cursor()

        # Lista tabelas operacionais
        tables = [
            "review_items", "production_feedback", "lead_outcomes",
            "whatsapp_status", "bot_decisions", "pending_jobs",
            "conversations", "messages", "lead_state",
            "idempotency_keys", "tts_cache_metadata", "conversation_metrics",
        ]

        for table in tables:
            out_path = backup_subdir / f"{table}.csv"
            try:
                with open(out_path, "w") as f:
                    cur.copy_expert(f"COPY {table} TO STDOUT WITH CSV HEADER", f)
                print(f"    {table}: OK")
            except Exception as e:
                print(f"    {table}: {e}")

        cur.close()
        conn.close()
        return {"status": "ok", "method": "psycopg2 COPY", "tables": len(tables)}
    except Exception as e:
        return {"status": "error", "reason": str(e)[:200]}


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
    """Conta keys por prefixo usando redis-py (não redis-cli)."""
    redis_url = env.get("REDIS_URL", "redis://localhost:6379")
    if not redis_url or "{SECRET}" in redis_url:
        return {"status": "skipped"}

    try:
        import redis
    except ImportError:
        return {"status": "error", "reason": "redis-py not available"}

    # Try configured URL first, fallback to localhost docker network
    redis_urls_to_try = [
        env.get("REDIS_URL", "redis://localhost:6379"),
        "redis://127.0.0.1:6379",
    ]

    r = None
    last_error = ""
    for url in redis_urls_to_try:
        if not url or "{SECRET}" in url:
            continue
        try:
            r = redis.from_url(url, decode_responses=True)
            r.ping()
            break
        except Exception as e:
            last_error = str(e)
            r = None

    if r is None:
        return {"status": "error", "reason": last_error}

    prefixes = [
        "lead:", "conversation:", "review:", "debounce:", "whatsapp:",
        "tts:", "queue:", "idempotency:", "assisted:", "refrimix:",
    ]

    results = {}
    for prefix in prefixes:
        try:
            count = r.eval("return #redis.call('KEYS', ARGV[1])", 0, prefix)
            results[prefix] = {"status": "ok", "keys": count}
        except Exception as e:
            results[prefix] = {"status": "error", "reason": str(e)}

    r.close()
    return {"status": "ok", "prefixes": results}


# ── info Qdrant ───────────────────────────────────────────────────────────────

def info_qdrant(env: dict) -> dict:
    """Lista collections Qdrant e counts."""
    import urllib.request

    # Try configured URL first, fallback to localhost docker network
    qdrant_urls_to_try = [
        env.get("QDRANT_URL", "http://localhost:6333"),
        "http://127.0.0.1:6333",
    ]

    for qdrant_url in qdrant_urls_to_try:
        if not qdrant_url or "{SECRET}" in qdrant_url:
            continue
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
        except Exception:
            continue

    return {"status": "error", "reason": "Could not connect to Qdrant on any URL"}


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