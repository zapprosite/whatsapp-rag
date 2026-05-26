#!/usr/bin/env python3
"""
Reset script: clean WhatsApp RAG data only.
Preserves: evolution_api DB, voice_embeddings, Hermes Redis keys.
"""
import os, sys, json, subprocess

os.chdir('/home/will/whatsapp-rag')
BK = 'backups/reset-20260526-100137'
os.makedirs(BK, exist_ok=True)

# ── Load env ──────────────────────────────────────────────────
env = {}
with open('.env') as f:
    for line in f:
        line = line.strip()
        if line and not line.startswith('#') and '=' in line:
            k, _, v = line.partition('=')
            env[k] = v

DB_URL = env['DATABASE_URL']
QDRANT_URL = env.get('QDRANT_URL', 'http://localhost:6333')

# ── 1. Backup Redis WhatsApp keys ─────────────────────────────
import redis
r = redis.Redis(host='localhost', port=6379, decode_responses=True)
wa_keys = sorted([k for k in r.keys()
                  if k.startswith('whatsapp_rag:') or k.startswith('sales_reply:')])
print(f'=== Redis WhatsApp keys ({len(wa_keys)}) ===')
with open(f'{BK}/redis_wa_keys.txt', 'w') as f:
    for k in wa_keys:
        t = r.type(k)
        v = r.get(k) if t == 'string' else r.lrange(k, 0, -1)
        f.write(f'{k} [{t}]: {v}\n')
print(f'Saved → {BK}/redis_wa_keys.txt')

# ── 2. Truncate Postgres whatsapp_rag tables ─────────────────
print('\n=== Truncating whatsapp_rag Postgres ===')
import psycopg2
conn = psycopg2.connect(DB_URL)
conn.autocommit = True
cur = conn.cursor()

cur.execute("""
SELECT tablename
FROM pg_tables
WHERE schemaname = 'public'
  AND tablename <> '_prisma_migrations'
ORDER BY tablename;
""")
tables = [row[0] for row in cur.fetchall()]
print(f'Tables: {tables}')

for tbl in tables:
    cur.execute(f'TRUNCATE TABLE public."{tbl}" RESTART IDENTITY CASCADE;')
    print(f'  ✓ {tbl}')

cur.execute("""
SELECT schemaname, relname, n_live_tup
FROM pg_stat_user_tables
ORDER BY relname;
""")
print('\nPost-truncate row counts:')
for row in cur.fetchall():
    print(f'  {row[1]}: {row[2]} rows')
cur.close()
conn.close()

# ── 3. Prisma db push (force sync schema) ────────────────────
print('\n=== Prisma db push --force ===')
result = subprocess.run(
    ['.venv/bin/prisma', 'db', 'push', '--force-reset', '--skip-generate'],
    capture_output=True, text=True, timeout=60
)
print(result.stdout[-500:] if result.stdout else '')
if result.returncode != 0:
    print('STDERR:', result.stderr[-300:])
    with open(f'{BK}/prisma_push.log', 'w') as f:
        f.write(result.stdout + '\n' + result.stderr)
print('Return code:', result.returncode)

# ── 4. Delete Qdrant HVAC collection only ────────────────────
print('\n=== Deleting Qdrant hermes_hvac_rag_service_staging ===')
import requests
resp = requests.delete(f'{QDRANT_URL}/collections/hermes_hvac_rag_service_staging')
print(f'DELETE collection: {resp.status_code} {resp.text[:200]}')
with open(f'{BK}/qdrant_delete.json', 'w') as f:
    json.dump({'status_code': resp.status_code, 'body': resp.text}, f)

resp = requests.get(f'{QDRANT_URL}/collections')
print('\nRemaining collections:')
print(resp.json())

# ── 5. Clear Redis WhatsApp keys only ────────────────────────
print('\n=== Deleting Redis WhatsApp keys ===')
if wa_keys:
    r.delete(*wa_keys)
print(f'Deleted {len(wa_keys)} keys')
remaining = [k for k in r.keys()
             if k.startswith('whatsapp_rag:') or k.startswith('sales_reply:')]
print(f'Remaining whatsapp_rag/sales_reply keys: {len(remaining)}')

# ── 6. Health smoke ─────────────────────────────────────────
print('\n=== Health check ===')
result = subprocess.run(
    ['curl', '-s', 'http://localhost:8000/health'],
    capture_output=True, text=True, timeout=10
)
health = result.stdout.strip()
print(health)
health_data = json.loads(health)
with open(f'{BK}/health_after.json', 'w') as f:
    json.dump(health_data, f, indent=2)

print(f'\n✅ Done. Backup: {BK}/')
print('If worker is running: docker compose restart fastapi-rag')
