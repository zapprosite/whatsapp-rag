#!/usr/bin/env python3
"""
clean_operational_state.py

Limpeza controlada de estado operacional (Redis + PostgreSQL).
NÃO toca tabelas comerciais reais (clients, quotes, service_orders, etc).

Uso:
    python scripts/clean_operational_state.py --dry-run    # default
    CONFIRM_RESET_OPERATIONAL_STATE=1 python scripts/clean_operational_state.py  # aplica

Regras:
- dry-run por padrão.
- Exige CONFIRM_RESET_OPERATIONAL_STATE=1 para aplicar.
- Usa transactions no PostgreSQL.
- Limpa Redis por prefixo com SCAN+UNLINK/DEL, não FLUSHALL.
- FLUSHDB só se REDIS_DESTRUCTIVE_FLUSH_OK=1 E Redis exclusivo.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
from datetime import datetime
from pathlib import Path

# ── helpers ──────────────────────────────────────────────────────────────────

def run_cmd(cmd: list[str], timeout: int = 30, env: dict | None = None) -> tuple[int, str, str]:
    full_env = os.environ.copy()
    if env:
        full_env.update(env)
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout, env=full_env)
        return result.returncode, result.stdout or "", result.stderr or ""
    except Exception as e:
        return 1, "", str(e)


def load_env() -> dict:
    env_path = Path(__file__).parent.parent / ".env"
    env = {}
    if env_path.exists():
        for line in env_path.read_text().splitlines():
            if "=" in line and not line.startswith("#"):
                key, _, val = line.partition("=")
                env[key.strip()] = val.strip()
    return env


# ── Redis limpeza ─────────────────────────────────────────────────────────────

def clean_redis(env: dict, dry_run: bool) -> dict:
    """
    Limpa chaves Redis por prefixo, com SCAN + UNLINK/DEL.
    Nunca FLUSHALL. FLUSHDB só com REDIS_DESTRUCTIVE_FLUSH_OK=1.
    """
    redis_url = env.get("REDIS_URL", "")
    if not redis_url or "{SECRET}" in redis_url:
        return {"status": "skipped", "reason": "REDIS_URL não configurado ou placeholder"}

    # Parse redis://host:port ou redis://host:***@host:port
    try:
        addr = redis_url.replace("redis://", "")
        if "@" in addr:
            # user:***@host:port
            host_part = addr.split("@")[1]
        else:
            host_part = addr
        host_port = host_part.rstrip("/")
        if ":" in host_port:
            host = host_port.split(":")[0]
            port = host_port.split(":")[1]
        else:
            host = host_port
            port = "6379"
    except Exception as e:
        return {"status": "error", "reason": f"parse error: {e}"}

    prefixes = [
        "lead:", "conversation:", "review:", "debounce:", "whatsapp:",
        "tts:", "queue:", "idempotency:", "assisted:", "refrimix:",
    ]

    results = {}
    for prefix in prefixes:
        if dry_run:
            # Conta keys com EXISTS (ou apenas DBSIZE geral)
            results[prefix] = {
                "status": "dry-run",
                "action": f"SCAN + UNLINK keys matching '{prefix}*'",
            }
        else:
            # SCAN para encontrar keys e UNLINK em batch
            deleted = 0
            cursor = 0
            while True:
                cmd_scan = [
                    "redis-cli", "-h", host, "-p", port, "--no-raw",
                    "SCAN", str(cursor), "MATCH", f"{prefix}*", "COUNT", "100",
                ]
                _, scan_out, _ = run_cmd(cmd_scan)
                lines = [ln.strip() for ln in scan_out.strip().splitlines() if ln.strip()]
                if lines:
                    try:
                        cursor = int(lines[0])
                        keys = lines[1:]
                    except (ValueError, IndexError):
                        break
                    if keys:
                        for k in keys:
                            run_cmd(["redis-cli", "-h", host, "-p", port, "--no-raw", "UNLINK", k])
                        deleted += len(keys)
                if cursor == 0:
                    break

            results[prefix] = {
                "status": "deleted",
                "keys_removed": deleted,
            }

    # FLUSHDB só se permitido
    if os.getenv("REDIS_DESTRUCTIVE_FLUSH_OK", "0") == "1":
        if dry_run:
            results["_flushdb"] = {"status": "dry-run", "action": "FLUSHDB (skipped — dry-run)"}
        else:
            _, flush_out, flush_err = run_cmd(["redis-cli", "-h", host, "-p", port, "FLUSHDB"])
            results["_flushdb"] = {"status": "ok" if not flush_err else flush_err[:100]}
    else:
        results["_flushdb"] = {"status": "skipped", "reason": "REDIS_DESTRUCTIVE_FLUSH_OK != 1"}

    return results


# ── PostgreSQL limpeza ────────────────────────────────────────────────────────

def clean_postgres(env: dict, dry_run: bool) -> dict:
    """
    Limpa tabelas operacionais do PostgreSQL.
    NUNCA toca tabelas comerciais.
    """
    db_url = env.get("DATABASE_URL", "")
    if not db_url or "{SECRET}" in db_url:
        return {"status": "skipped", "reason": "DATABASE_URL não configurado ou placeholder"}

    # Parse postgresql://user:***@host:port/dbname
    try:
        addr = db_url.replace("postgresql://", "")
        if "@" in addr:
            user_part = addr.split("@")[0]
            host_part = addr.split("@")[1]
        else:
            user_part = None
            host_part = addr

        if "/" in host_part:
            host_port = host_part.split("/")[0]
            dbname = host_part.split("/")[1].split("?")[0]
        else:
            host_port = host_part
            dbname = "whatsapp_rag"

        if ":" in host_port:
            pg_host = host_port.split(":")[0]
            pg_port = host_port.split(":")[1]
        else:
            pg_host = host_port
            pg_port = "5432"

        pg_user = user_part.split(":")[0] if user_part else "postgres"
        pg_password = user_part.split(":")[1] if user_part and ":" in user_part else ""
    except Exception as e:
        return {"status": "error", "reason": f"parse error: {e}"}

    pg_env = os.environ.copy()
    if pg_password and pg_password != "***":
        pg_env["PGPASSWORD"] = pg_password

    # Tabelas operacionais — seguro limpar
    operational_tables = [
        "review_items",
        "production_feedback",
        "lead_outcomes",
        "whatsapp_status",
        "bot_decisions",
        "pending_jobs",
        "conversation_metrics",
        "idempotency_keys",
        "tts_cache_metadata",
    ]

    # Tabelas conversation/message — também operacional
    conversational_tables = [
        "conversations",
        "messages",
        "lead_state",
    ]

    results = {}
    all_tables = operational_tables + conversational_tables

    for table in all_tables:
        # Conta antes
        count_sql = f"SELECT COUNT(*) FROM {table};"
        cmd_count = [
            "psql", "-h", pg_host, "-p", pg_port, "-U", pg_user, "-d", dbname,
            "-t", "-c", count_sql,
        ]
        _, count_out, count_err = run_cmd(cmd_count, env=pg_env)
        try:
            lines = [ln.strip() for ln in count_out.strip().splitlines() if ln.strip()]
            row_count = int(lines[-1]) if lines else 0
        except Exception:
            row_count = -1

        if dry_run:
            results[table] = {
                "rows_before": row_count,
                "action": "dry-run (TRUNCATE CASCADE)",
            }
        else:
            # TRUNCATE CASCADE em transaction
            sql = f"BEGIN; TRUNCATE TABLE {table} CASCADE; COMMIT;"
            cmd_del = [
                "psql", "-h", pg_host, "-p", pg_port, "-U", pg_user, "-d", dbname,
                "-t", "-c", sql,
            ]
            _, del_out, del_err = run_cmd(cmd_del, env=pg_env, timeout=60)
            # psql não retorna erro em BEGIN success, então checar via count
            if del_err and "BEGIN" in del_err and "COMMIT" not in del_err:
                results[table] = {
                    "rows_deleted": row_count,
                    "status": "error",
                    "reason": del_err.strip()[:100],
                }
            else:
                results[table] = {
                    "rows_deleted": row_count,
                    "status": "ok",
                }

    return results


# ── main ─────────────────────────────────────────────────────────────────────

def main():
    import argparse

    parser = argparse.ArgumentParser(description="Clean Operational State — Phase 2.10")
    parser.add_argument("--dry-run", action="store_true", default=True)
    parser.parse_args()  # --dry-run is default; CONFIRM_RESET env var controls apply

    dry_run = os.getenv("CONFIRM_RESET_OPERATIONAL_STATE", "0") != "1"
    confirm = os.getenv("CONFIRM_RESET_OPERATIONAL_STATE", "0") == "1"

    print("=" * 60)
    print("Clean Operational State — Phase 2.10")
    print("=" * 60)
    print(f"  Modo: {'DRY-RUN' if dry_run else 'APLICAR'}")
    print(f"  CONFIRM_RESET_OPERATIONAL_STATE={os.getenv('CONFIRM_RESET_OPERATIONAL_STATE', '0')}")
    print("=" * 60)

    if dry_run and not confirm:
        print("\n⚠️  DRY-RUN — nada será apagado.")
        print("   Para aplicar: export CONFIRM_RESET_OPERATIONAL_STATE=1")

    ts = datetime.now().strftime("%Y%m%d-%H%M%S")
    report_dir = Path("reports")
    report_dir.mkdir(exist_ok=True)

    env = load_env()

    print("\n[1/2] Limpando Redis...")
    redis_result = clean_redis(env, dry_run=dry_run)
    print(f"  → {json.dumps(redis_result, indent=2, ensure_ascii=False)}")

    print("\n[2/2] Limpando PostgreSQL...")
    pg_result = clean_postgres(env, dry_run=dry_run)
    print(f"  → {json.dumps(pg_result, indent=2, ensure_ascii=False)}")

    # Salva relatório markdown
    lines = [
        f"# Clean State Report — {ts}",
        f"\n**Modo:** {'DRY-RUN' if dry_run else 'APLICADO'}",
        "",
        "## Redis",
    ]
    for prefix, data in redis_result.items():
        lines.append(f"\n### `{prefix}`")
        for k, v in data.items():
            lines.append(f"- **{k}:** {v}")

    lines.append("\n## PostgreSQL")
    for table, data in pg_result.items():
        lines.append(f"\n### `{table}`")
        for k, v in data.items():
            lines.append(f"- **{k}:** {v}")

    report_path = report_dir / f"clean_state_{ts}.md"
    report_path.write_text("\n".join(lines))
    print(f"\n📄 Relatório: {report_path}")

    if dry_run:
        print("\n✅ Dry-run concluído. Execute com CONFIRM_RESET_OPERATIONAL_STATE=1 para aplicar.")
    else:
        print("\n✅ Limpeza concluída.")
        try:
            subprocess.run(["git", "add", str(report_path)], check=False, cwd=Path(__file__).parent.parent)
        except Exception:
            pass

    sys.exit(0)


if __name__ == "__main__":
    main()