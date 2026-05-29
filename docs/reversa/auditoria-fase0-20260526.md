# AUDITORIA FASE 0 — sex 29 mai 2026 02:05:53 -03
## Top-level
total 244
drwxrwxr-x 1 will will   650 mai 27 14:53 .
drwxr-x--- 1 will will  2192 mai 29 02:00 ..
drwxrwxr-x 1 will will   114 mai 27 05:23 agent_graph
-rw-rw-r-- 1 will will  4718 mai 26 12:19 AGENTS.md
drwxrwxr-x 1 will will   308 mai 27 05:23 app
drwxrwxr-x 1 will will    40 mai 26 12:19 _archive
drwxrwxr-x 1 will will   152 mai 27 05:22 autonomous_refiner
drwxrwxr-x 1 will will   216 mai 26 12:08 backups
-rwxrwxr-x 1 will will  2254 mai 25 02:21 bot.sh
-rw-rw-r-- 1 will will 33831 mai 27 14:53 CLAUDE.md
drwxrwxr-x 1 will will    42 mai 26 12:19 .context
-rw-rw-r-- 1 will will  2269 mai 27 08:34 docker-compose.yml
drwxrwxr-x 1 will will   606 mai 27 08:56 docs
-rw------- 1 will will  2806 mai 27 10:02 .env
-rw-rw-r-- 1 will will  4906 mai 27 08:34 .env.example
-rw-rw-r-- 1 will will 13649 mai 26 12:19 env.schema.md
drwxrwxr-x 1 will will   176 mai 29 02:00 .git
-rw-rw-r-- 1 will will    13 mai 25 03:32 .gitattributes
-rw-rw-r-- 1 will will   701 mai 26 12:19 .gitignore
-rwxrwxr-x 1 will will  1971 mai 25 06:32 git.sh
-rw-rw-r-- 1 will will 64464 mai 26 08:28 image.png
drwxrwxr-x 1 will will    16 mai 25 21:50 knowledge
-rw-rw-r-- 1 will will 64548 mai 25 03:30 orcamento_teste.pdf
drwxrwxr-x 1 will will    50 mai 26 04:04 prisma
drwxrwxr-x 1 will will    64 mai 24 13:17 .pytest_cache
-rw-rw-r-- 1 will will   163 mai 27 02:28 pytest.ini
drwxrwxr-x 1 will will   144 mai 27 05:22 qdrant
-rw-rw-r-- 1 will will  7089 mai 26 12:19 README.md
drwxrwxr-x 1 will will   206 mai 27 05:40 refrimix_core
drwxrwxr-x 1 will will  1464 mai 27 14:48 reports
-rw-rw-r-- 1 will will   407 mai 27 11:22 requirements.txt
drwxrwxr-x 1 will will    58 mai 27 08:51 .ruff_cache
drwxrwxr-x 1 will will    76 mai 25 21:50 .rules
drwxrwxr-x 1 will will   974 mai 27 14:47 scripts
drwxrwxr-x 1 will will    40 mai 27 05:22 sre
-rwxrwxr-x 1 will will  6506 mai 26 12:19 sync.sh
drwxrwxr-x 1 will will  4584 mai 27 12:39 tests
drwxrwxr-x 1 will will    66 mai 24 09:52 .venv

## app/*.py
app/agenda_scheduler.py
app/api/bot.py
app/api/health.py
app/api/__init__.py
app/api/review.py
app/api/test_routes.py
app/api/webhook.py
app/config/__init__.py
app/config/settings.py
app/__init__.py
app/lead_repository.py
app/main.py
app/mvp_attendance.py
app/runtime_config.py
app/runtime.py
app/worker.py

## refrimix_core/*.py
refrimix_core/adapters/evolution_typing_adapter.py
refrimix_core/config/__init__.py
refrimix_core/config/settings.py
refrimix_core/domain/audio_delivery_policy.py
refrimix_core/domain/commercial_router.py
refrimix_core/domain/conversation_style.py
refrimix_core/domain/document_jobs.py
refrimix_core/domain/drive_naming.py
refrimix_core/domain/drive_taxonomy.py
refrimix_core/domain/__init__.py
refrimix_core/domain/model_router.py
refrimix_core/domain/natural_microcopy.py
refrimix_core/domain/pipeline.py
refrimix_core/domain/response_catalog.py
refrimix_core/domain/text_normalizer.py
refrimix_core/domain/tts_cache_key.py
refrimix_core/domain/tts_policy.py
refrimix_core/domain/types.py
refrimix_core/domain/typing_policy.py
refrimix_core/domain/whatsapp_runtime_policy.py
refrimix_core/evaluation/conversation_simulator.py
refrimix_core/evaluation/__init__.py
refrimix_core/evaluation/real_case_exporter.py
refrimix_core/evaluation/response_mutator.py
refrimix_core/evaluation/response_refinement_loop.py
refrimix_core/evaluation/response_rubric.py
refrimix_core/evaluation/scenario_generator.py
refrimix_core/guards/__init__.py
refrimix_core/guards/language_guard.py
refrimix_core/__init__.py
refrimix_core/integrations/__init__.py
refrimix_core/monitoring/assisted_pilot_report.py
refrimix_core/monitoring/conversation_metrics.py
refrimix_core/monitoring/__init__.py
refrimix_core/monitoring/lead_outcome_tracker.py
refrimix_core/monitoring/production_feedback.py
refrimix_core/monitoring/whatsapp_status_tracker.py
refrimix_core/nodes/__init__.py
refrimix_core/nodes/plan_next_action.py
refrimix_core/nodes/reduce_lead_state.py
refrimix_core/nodes/understand_message.py
refrimix_core/review/__init__.py
refrimix_core/review/review_actions.py
refrimix_core/review/review_models.py
refrimix_core/review/review_policy.py
refrimix_core/review/review_queue.py
refrimix_core/runtime/whatsapp_orchestrator.py
refrimix_core/tools/audio_transcode.py
refrimix_core/tools/google_auth.py
refrimix_core/tools/google_calendar_tool.py
refrimix_core/tools/google_drive_tool.py
refrimix_core/tools/google_integration_smoke.py

## prisma/
prisma/.env.example
prisma/schema.prisma
