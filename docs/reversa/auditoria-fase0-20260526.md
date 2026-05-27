# AUDITORIA FASE 0 — ter 26 mai 2026 22:30:07 -03
## Top-level
total 220
drwxrwxr-x 1 will will   636 mai 26 12:19 .
drwxr-x--- 1 will will  2002 mai 26 22:25 ..
drwxrwxr-x 1 will will   114 mai 25 19:58 agent_graph
-rw-rw-r-- 1 will will  4718 mai 26 12:19 AGENTS.md
drwxrwxr-x 1 will will   274 mai 26 12:19 app
drwxrwxr-x 1 will will    40 mai 26 12:19 _archive
drwxrwxr-x 1 will will   174 mai 26 09:38 autonomous_refiner
drwxrwxr-x 1 will will   216 mai 26 12:08 backups
-rwxrwxr-x 1 will will  2254 mai 25 02:21 bot.sh
-rw-rw-r-- 1 will will 14962 mai 26 12:19 CLAUDE.md
drwxrwxr-x 1 will will    42 mai 26 12:19 .context
-rw-rw-r-- 1 will will  2162 mai 26 12:19 docker-compose.yml
drwxrwxr-x 1 will will    98 mai 26 08:51 docs
-rw------- 1 will will  2733 mai 26 10:28 .env
-rw-rw-r-- 1 will will  3612 mai 26 12:19 .env.example
-rw-rw-r-- 1 will will 13649 mai 26 12:19 env.schema.md
drwxrwxr-x 1 will will   158 mai 26 22:25 .git
-rw-rw-r-- 1 will will    13 mai 25 03:32 .gitattributes
-rw-rw-r-- 1 will will   701 mai 26 12:19 .gitignore
-rwxrwxr-x 1 will will  1971 mai 25 06:32 git.sh
-rw-rw-r-- 1 will will 64464 mai 26 08:28 image.png
drwxrwxr-x 1 will will    16 mai 25 21:50 knowledge
-rw-rw-r-- 1 will will 64548 mai 25 03:30 orcamento_teste.pdf
drwxrwxr-x 1 will will    50 mai 26 04:04 prisma
drwxrwxr-x 1 will will   254 mai 26 09:05 __pycache__
drwxrwxr-x 1 will will    64 mai 24 13:17 .pytest_cache
-rw-rw-r-- 1 will will   125 mai 26 12:19 pytest.ini
drwxrwxr-x 1 will will   166 mai 25 21:50 qdrant
-rw-rw-r-- 1 will will  7089 mai 26 12:19 README.md
drwxrwxr-x 1 will will   114 mai 26 09:00 refrimix_core
-rw-rw-r-- 1 will will   391 mai 25 04:34 requirements.txt
drwxrwxr-x 1 will will    76 mai 25 21:50 .rules
drwxrwxr-x 1 will will   454 mai 26 12:43 scripts
drwxrwxr-x 1 will will    62 mai 25 21:50 sre
-rwxrwxr-x 1 will will  6506 mai 26 12:19 sync.sh
drwxrwxr-x 1 will will  2914 mai 26 12:19 tests
drwxrwxr-x 1 will will    66 mai 24 09:52 .venv

## app/*.py
app/agenda_scheduler.py
app/api/bot.py
app/api/health.py
app/api/__init__.py
app/api/test_routes.py
app/api/webhook.py
app/config/__init__.py
app/config/settings.py
app/__init__.py
app/lead_repository.py
app/main.py
app/mvp_attendance.py
app/runtime.py
app/worker.py

## refrimix_core/*.py
refrimix_core/config/__init__.py
refrimix_core/config/settings.py
refrimix_core/domain/commercial_router.py
refrimix_core/domain/__init__.py
refrimix_core/domain/pipeline.py
refrimix_core/domain/response_catalog.py
refrimix_core/domain/text_normalizer.py
refrimix_core/domain/types.py
refrimix_core/guards/__init__.py
refrimix_core/guards/language_guard.py
refrimix_core/__init__.py
refrimix_core/integrations/__init__.py
refrimix_core/nodes/__init__.py
refrimix_core/nodes/plan_next_action.py
refrimix_core/nodes/reduce_lead_state.py
refrimix_core/nodes/understand_message.py

## prisma/
prisma/.env.example
prisma/schema.prisma
