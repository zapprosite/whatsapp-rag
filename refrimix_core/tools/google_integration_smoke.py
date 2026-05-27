"""
Google Integration Smoke — Refrimix
Smoke test helpers para Google Drive + Calendar.

Regras:
- DRY_RUN=1 (default): simula sem chamar API real
- GOOGLE_INTEGRATION_DRY_RUN=0 + CONFIRM_GOOGLE_LIVE_TEST=1: executa real
- Sandbox: pasta 99_SANDBOX_HERMES_TESTES
- Eventos de teste começam com [TESTE HERMES]
- Nunca envia PDF por WhatsApp
- Nunca commita credenciais ou tokens
"""
from __future__ import annotations

import json
import logging
import os
import uuid
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from refrimix_core.tools.google_auth import auth_summary, get_access_token

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

DRY_RUN = os.getenv("GOOGLE_INTEGRATION_DRY_RUN", "1") == "1"
CONFIRM_LIVE = os.getenv("CONFIRM_GOOGLE_LIVE_TEST", "0") == "1"
CLEANUP = os.getenv("GOOGLE_SMOKE_CLEANUP", "0") == "1"

SANDBOX_FOLDER_ID = os.getenv("GOOGLE_DRIVE_SANDBOX_FOLDER_ID", "")
CALENDAR_TEST_PREFIX = os.getenv(
    "GOOGLE_CALENDAR_TEST_PREFIX", "[TESTE HERMES]"
)
ROOT_FOLDER_ID = os.getenv("GOOGLE_DRIVE_ROOT_FOLDER_ID", "")
CALENDAR_ID = os.getenv("GOOGLE_CALENDAR_ID", "refrimixtecnologia@gmail.com")

SMOKE_LEAD_ID = f"smoke_{uuid.uuid4().hex[:12]}"
SMOKE_LEAD_PHONE = "5599999999999"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def is_dry_run() -> bool:
    return DRY_RUN


def is_live_allowed() -> bool:
    """True só se DRY_RUN=0 E CONFIRM_LIVE=1."""
    return not DRY_RUN and CONFIRM_LIVE


def _require_live():
    """Levanta se live test não permitido."""
    if not is_live_allowed():
        raise RuntimeError(
            "Live test não permitido. "
            "Configure GOOGLE_INTEGRATION_DRY_RUN=0 E CONFIRM_GOOGLE_LIVE_TEST=1."
        )


def _log(action: str, detail: str, dry: bool = False):
    prefix = "[DRY-RUN] " if dry else ""
    logger.info("%s%s: %s", prefix, action, detail)


# ---------------------------------------------------------------------------
# Fake lead factory
# ---------------------------------------------------------------------------

def build_fake_lead() -> dict[str, Any]:
    """Cria lead fake para smoke test."""
    return {
        "lead_id": SMOKE_LEAD_ID,
        "phone": SMOKE_LEAD_PHONE,
        "client_name": "Fulano de Teste",
        "city_bairro": "São Paulo - Vila Madalena",
        "service_type": "higienizacao",
        "intent": "higienizacao_rinite",
        "risk": "low",
        "status": "smoke_test",
        "source": "google_smoke_test",
        "notes": "Lead gerado automaticamente pelo smoke test Hermes. "
                 "Este lead deve ser descartado após o teste.",
    }


# ---------------------------------------------------------------------------
# Fake PDF factory
# ---------------------------------------------------------------------------

def build_fake_pdf_path() -> Path:
    """
    Cria PDF fake local para smoke test de upload.
    Não é PDF real — arquivo texto com extensão .pdf.
    """
    fake_pdf_dir = Path("/tmp/hermes_smoke_pdfs")
    fake_pdf_dir.mkdir(exist_ok=True)
    fake_pdf_path = fake_pdf_dir / f"SMOKE_TEST_{SMOKE_LEAD_ID}.pdf"

    content = (
        f"%PDF-1.4\n"
        f"% Smoke Test PDF — Hermes Google Integration Test\n"
        f"% Lead: {SMOKE_LEAD_ID}\n"
        f"% Generated: {datetime.now().isoformat()}\n"
        f"% This is a TEST FILE, not a real document\n"
        f"1 0 obj << /Type /Catalog /Pages 2 0 R >> endobj\n"
        f"2 0 obj << /Type /Pages /Kids [3 0 R] /Count 1 >> endobj\n"
        f"3 0 obj << /Type /Page /Parent 2 0 R /MediaBox [0 0 595 842] >> endobj\n"
        f"xref\n"
        f"trailer << /Size 3 /Root 1 0 R >>\n"
        f"startxref\n"
        f"0\n"
        f"%%EOF\n"
    )
    fake_pdf_path.write_text(content)
    return fake_pdf_path


# ---------------------------------------------------------------------------
# Sandbox folder resolution
# ---------------------------------------------------------------------------

def resolve_sandbox_folder_id() -> str:
    """
    Retorna o folder_id da pasta sandbox.

    Se GOOGLE_DRIVE_SANDBOX_FOLDER_ID está configurado, usa diretamente.
    Se não, busca (ou cria) '99_SANDBOX_HERMES_TESTES' dentro da raiz.
    """
    if SANDBOX_FOLDER_ID:
        _log("Sandbox", f"Usando folder_id do env: {SANDBOX_FOLDER_ID[:8]}...")
        return SANDBOX_FOLDER_ID

    if DRY_RUN:
        fake_id = f"dry_run_sandbox_{uuid.uuid4().hex[:8]}"
        _log("Sandbox", f"[DRY-RUN] usaria: 99_SANDBOX_HERMES_TESTES → {fake_id}", dry=True)
        return fake_id

    _require_live()
    root_id = _require_root_folder_id()
    return _ensure_sandbox_folder(root_id)


def _require_root_folder_id() -> str:
    if not ROOT_FOLDER_ID:
        raise RuntimeError(
            "GOOGLE_DRIVE_ROOT_FOLDER_ID não configurado. "
            "Informe o folder_id raiz ou use GOOGLE_DRIVE_SANDBOX_FOLDER_ID."
        )
    return ROOT_FOLDER_ID


def _ensure_sandbox_folder(parent_id: str) -> str:
    """Busca ou cria a pasta sandbox."""
    import httpx

    access_token = get_access_token()
    headers = {"Authorization": f"Bearer {access_token}"}
    sandbox_name = "99_SANDBOX_HERMES_TESTES"

    # Busca
    query = (
        f"name='{sandbox_name}' and "
        f"mimeType='application/vnd.google-apps.folder' and "
        f"'{parent_id}' in parents and trashed=false"
    )
    url = f"https://www.googleapis.com/drive/v3/files?q={query}&fields=files(id,name)"
    with httpx.Client() as client:
        resp = client.get(url, headers=headers, timeout=30)
    resp.raise_for_status()
    files = resp.json().get("files", [])
    if files:
        folder_id = files[0]["id"]
        _log("Sandbox", f"Encontrada pasta existente: {folder_id}")
        return folder_id

    # Cria
    create_url = "https://www.googleapis.com/drive/v3/files"
    payload = {
        "name": sandbox_name,
        "mimeType": "application/vnd.google-apps.folder",
        "parents": [parent_id],
    }
    with httpx.Client() as client:
        resp = client.post(create_url, headers=headers, json=payload, timeout=30)
    resp.raise_for_status()
    folder_id = resp.json()["id"]
    _log("Sandbox", f"Criada nova pasta sandbox: {folder_id}")
    return folder_id


# ---------------------------------------------------------------------------
# Smoke: Drive
# ---------------------------------------------------------------------------

def run_smoke_drive() -> dict[str, Any]:
    """
    Executa smoke test do Google Drive.

    Fluxo:
    1. Resolve sandbox folder
    2. Cria pasta do atendimento fake
    3. Salva metadata.json
    4. Salva resumo_lead.md
    5. Gera PDF fake local
    6. Faz upload do PDF fake

    Returns dict com resultados de cada etapa.
    """
    results: dict[str, Any] = {
        "stage": "drive",
        "dry_run": DRY_RUN,
        "steps": {},
        "sandbox_folder_id": None,
        "job_folder_id": None,
        "metadata_file_id": None,
        "resumo_file_id": None,
        "pdf_file_id": None,
        "success": False,
    }

    # Stage 1: sandbox
    if DRY_RUN:
        _log("Drive S1", "Simularia resolução da sandbox folder", dry=True)
        results["sandbox_folder_id"] = "dry_run_sandbox_id"
    else:
        try:
            _require_live()
            sandbox_id = resolve_sandbox_folder_id()
            results["sandbox_folder_id"] = sandbox_id
            _log("Drive S1", f"Sandbox: {sandbox_id}")
        except Exception as exc:
            results["steps"]["sandbox"] = {"status": "error", "message": str(exc)}
            results["error"] = str(exc)
            return results

    # Stage 2: job folder
    fake_lead = build_fake_lead()
    if DRY_RUN:
        fake_job_folder_id = f"dry_run_job_folder_{uuid.uuid4().hex[:8]}"
        results["job_folder_id"] = fake_job_folder_id
        _log("Drive S2", f"[DRY-RUN] criaria pasta: {fake_lead['lead_id']}", dry=True)
        results["steps"]["job_folder"] = {
            "status": "ok",
            "folder_id": fake_job_folder_id,
            "folder_name": "smoke_.../2026-01-01_...",
        }
    else:
        try:
            from refrimix_core.tools.google_drive_tool import ensure_job_folder
            from refrimix_core.domain.drive_naming import build_job_folder_name

            sandbox_id = results["sandbox_folder_id"]
            folder_name = build_job_folder_name(
                date_str=date.today().isoformat(),
                phone=fake_lead["phone"],
                client_name=fake_lead["client_name"],
                city_bairro=fake_lead["city_bairro"],
                service_type=fake_lead["service_type"],
            )
            job_folder_id = ensure_job_folder(
                parent_folder_id=sandbox_id,
                date_str=date.today().isoformat(),
                phone=fake_lead["phone"],
                client_name=fake_lead["client_name"],
                city_bairro=fake_lead["city_bairro"],
                service_type=fake_lead["service_type"],
            )
            results["job_folder_id"] = job_folder_id
            results["steps"]["job_folder"] = {
                "status": "ok",
                "folder_id": job_folder_id,
                "folder_name": folder_name,
            }
            _log("Drive S2", f"Job folder: {job_folder_id}")
        except Exception as exc:
            results["steps"]["job_folder"] = {"status": "error", "message": str(exc)}
            results["error"] = str(exc)
            return results

    # Stage 3: metadata.json
    metadata = {
        "lead_id": fake_lead["lead_id"],
        "phone": fake_lead["phone"],
        "client_name": fake_lead["client_name"],
        "city_bairro": fake_lead["city_bairro"],
        "service_type": fake_lead["service_type"],
        "intent": fake_lead["intent"],
        "risk": fake_lead["risk"],
        "status": "smoke_test",
        "source": "google_smoke_test",
        "drive_folder_id": results["job_folder_id"],
        "documents": [],
        "created_at": datetime.now().isoformat(),
        "updated_at": datetime.now().isoformat(),
    }

    if DRY_RUN:
        results["metadata_file_id"] = "dry_run_metadata_id"
        results["steps"]["metadata_json"] = {
            "status": "ok",
            "file_id": "dry_run_metadata_id",
            "lead_id": fake_lead["lead_id"],
        }
        _log("Drive S3", "[DRY-RUN] salvaria metadata.json", dry=True)
    else:
        try:
            from refrimix_core.tools.google_drive_tool import save_metadata_json

            file_info = save_metadata_json(
                folder_id=results["job_folder_id"],
                metadata=metadata,
            )
            results["metadata_file_id"] = file_info["id"]
            results["steps"]["metadata_json"] = {
                "status": "ok",
                "file_id": file_info["id"],
                "lead_id": fake_lead["lead_id"],
            }
            _log("Drive S3", f"metadata.json: {file_info['id']}")
        except Exception as exc:
            results["steps"]["metadata_json"] = {"status": "error", "message": str(exc)}
            results["error"] = str(exc)
            return results

    # Stage 4: resumo_lead.md
    if DRY_RUN:
        results["resumo_file_id"] = "dry_run_resumo_id"
        results["steps"]["resumo_lead"] = {
            "status": "ok",
            "file_id": "dry_run_resumo_id",
        }
        _log("Drive S4", "[DRY-RUN] salvaria resumo_lead.md", dry=True)
    else:
        try:
            from refrimix_core.tools.google_drive_tool import save_lead_summary_markdown

            file_info = save_lead_summary_markdown(
                folder_id=results["job_folder_id"],
                lead_summary=fake_lead,
            )
            results["resumo_file_id"] = file_info["id"]
            results["steps"]["resumo_lead"] = {
                "status": "ok",
                "file_id": file_info["id"],
            }
            _log("Drive S4", f"resumo_lead.md: {file_info['id']}")
        except Exception as exc:
            results["steps"]["resumo_lead"] = {"status": "error", "message": str(exc)}
            results["error"] = str(exc)
            return results

    # Stage 5: PDF fake
    fake_pdf_path = build_fake_pdf_path()
    results["fake_pdf_path"] = str(fake_pdf_path)

    if DRY_RUN:
        results["pdf_file_id"] = "dry_run_pdf_id"
        results["steps"]["pdf_upload"] = {
            "status": "ok",
            "file_id": "dry_run_pdf_id",
            "local_path": str(fake_pdf_path),
        }
        _log("Drive S5", f"[DRY-RUN] faria upload de: {fake_pdf_path.name}", dry=True)
    else:
        try:
            from refrimix_core.tools.google_drive_tool import save_generated_pdf

            file_info = save_generated_pdf(
                folder_id=results["job_folder_id"],
                local_pdf_path=str(fake_pdf_path),
                document_type="quote_pdf",
                metadata=metadata,
            )
            results["pdf_file_id"] = file_info["id"]
            results["steps"]["pdf_upload"] = {
                "status": "ok",
                "file_id": file_info["id"],
                "local_path": str(fake_pdf_path),
                "drive_name": file_info.get("name"),
            }
            _log("Drive S5", f"PDF uploaded: {file_info['id']}")
        except Exception as exc:
            results["steps"]["pdf_upload"] = {"status": "error", "message": str(exc)}
            results["error"] = str(exc)
            return results

    results["success"] = True
    return results


# ---------------------------------------------------------------------------
# Smoke: Calendar
# ---------------------------------------------------------------------------

def run_smoke_calendar(job_folder_id: str | None = None) -> dict[str, Any]:
    """
    Executa smoke test do Google Calendar.

    Fluxo:
    1. Consulta FreeBusy (dias-ahead)
    2. Cria evento com prefixo [TESTE HERMES]
    3. Inclui link da pasta Drive no evento

    Returns dict com resultados.
    """
    results: dict[str, Any] = {
        "stage": "calendar",
        "dry_run": DRY_RUN,
        "steps": {},
        "freebusy_slots": [],
        "event_id": None,
        "event_html_link": None,
        "success": False,
    }

    if DRY_RUN:
        _log("Calendar S1", "[DRY-RUN] consultaria FreeBusy", dry=True)
        results["freebusy_slots"] = [
            {"date": "2026-01-01", "start": "09:00", "end": "10:00"},
            {"date": "2026-01-01", "start": "10:30", "end": "11:30"},
        ]
        results["steps"]["freebusy"] = {
            "status": "ok",
            "slots_found": 2,
            "note": "DRY-RUN — dados simulados",
        }
        fake_event_id = f"dry_run_event_{uuid.uuid4().hex[:8]}"
        results["event_id"] = fake_event_id
        results["steps"]["create_event"] = {
            "status": "ok",
            "event_id": fake_event_id,
            "summary": f"{CALENDAR_TEST_PREFIX} Fulano de Teste — São Paulo",
            "drive_folder_link": job_folder_id or "dry_run_folder_id",
        }
        _log("Calendar", "[DRY-RUN] criaria evento e vincularia pasta Drive", dry=True)
        results["success"] = True
        return results

    try:
        _require_live()
    except RuntimeError as exc:
        results["error"] = str(exc)
        return results

    # Stage 1: FreeBusy
    try:
        from refrimix_core.tools.google_calendar_tool import list_available_slots

        slots = list_available_slots(
            service_type="higienizacao",
            preferred_window=None,
            city_bairro="São Paulo",
            days_ahead=3,
        )
        results["freebusy_slots"] = slots[:3]
        results["steps"]["freebusy"] = {
            "status": "ok",
            "slots_found": len(slots),
            "shown": min(3, len(slots)),
        }
        _log("Calendar S1", f"FreeBusy: {len(slots)} slots encontrados")
    except Exception as exc:
        results["steps"]["freebusy"] = {"status": "error", "message": str(exc)}
        results["error"] = str(exc)
        return results

    # Stage 2: Create event
    fake_lead = build_fake_lead()
    if not slots:
        slot_start = (datetime.now() + timedelta(days=1)).replace(
            hour=9, minute=0, second=0, microsecond=0, tzinfo=timezone.utc
        )
    else:
        slot = slots[0]
        slot_date = datetime.fromisoformat(slot["date"])
        hour, minute = map(int, slot["start"].split(":"))
        slot_start = slot_date.replace(hour=hour, minute=minute, second=0, microsecond=0, tzinfo=timezone.utc)

    drive_folder_url = None
    if job_folder_id:
        drive_folder_url = f"https://drive.google.com/drive/folders/{job_folder_id}"

    try:
        from refrimix_core.tools.google_calendar_tool import create_service_event

        event = create_service_event(
            lead_id=fake_lead["lead_id"],
            phone=fake_lead["phone"],
            client_name=fake_lead["client_name"],
            service_type=fake_lead["service_type"],
            city_bairro=fake_lead["city_bairro"],
            start_iso=slot_start.isoformat(),
            duration_minutes=90,
            drive_folder_url=drive_folder_url,
            notes=f"Smoke test — lead_id: {fake_lead['lead_id']}",
        )
        results["event_id"] = event["id"]
        results["event_html_link"] = event.get("html_link")
        results["steps"]["create_event"] = {
            "status": "ok",
            "event_id": event["id"],
            "summary": event.get("summary"),
            "drive_folder_link": drive_folder_url,
            "start": event.get("start"),
            "end": event.get("end"),
        }
        _log("Calendar S2", f"Evento criado: {event['id']}")
    except Exception as exc:
        results["steps"]["create_event"] = {"status": "error", "message": str(exc)}
        results["error"] = str(exc)
        return results

    results["success"] = True
    return results


# ---------------------------------------------------------------------------
# Full smoke
# ---------------------------------------------------------------------------

def run_full_smoke() -> dict[str, Any]:
    """
    Executa smoke completo: Drive + Calendar.

    Se CLEANUP=1, remove artefatos ao final.
    """
    print("\n" + "=" * 60)
    print("GOOGLE INTEGRATION SMOKE TEST")
    print("=" * 60)
    print(f"  DRY_RUN:       {DRY_RUN}")
    print(f"  LIVE_CONFIRMED: {CONFIRM_LIVE}")
    print(f"  CLEANUP:        {CLEANUP}")
    print(f"  Lead ID:        {SMOKE_LEAD_ID}")
    print(f"  Phone:          {SMOKE_LEAD_PHONE}")
    print()

    # Auth check
    try:
        auth_info = auth_summary()
        print(f"  Auth:           {auth_info['token_status']}")
        print(f"  Token path:     {auth_info['token_path']}")
    except Exception as exc:
        print(f"  Auth ERRO:      {exc}")
        return {"success": False, "error": str(exc)}

    # Drive
    print("\n--- DRIVE ---")
    drive_results = run_smoke_drive()
    print(f"  Success:        {drive_results.get('success')}")
    if not DRY_RUN:
        print(f"  Sandbox ID:     {drive_results.get('sandbox_folder_id', '')[:16]}...")
        print(f"  Job Folder ID: {drive_results.get('job_folder_id', '')[:16]}...")
        print(f"  metadata.json:  {drive_results.get('metadata_file_id', '')[:16]}...")
        print(f"  resumo_lead.md: {drive_results.get('resumo_file_id', '')[:16]}...")
        print(f"  PDF file ID:    {drive_results.get('pdf_file_id', '')[:16]}...")

    if not drive_results.get("success"):
        print(f"  ERRO:           {drive_results.get('error', 'unknown')}")

    # Calendar
    print("\n--- CALENDAR ---")
    job_folder_id = drive_results.get("job_folder_id") if drive_results.get("success") else None
    cal_results = run_smoke_calendar(job_folder_id=job_folder_id)
    print(f"  Success:        {cal_results.get('success')}")
    if not DRY_RUN:
        print(f"  Event ID:       {cal_results.get('event_id', '')[:16]}...")
        print(f"  Event Link:     {cal_results.get('event_html_link', 'N/A')}")
        slots = cal_results.get("freebusy_slots", [])
        print(f"  FreeBusy slots: {len(slots)}")

    if not cal_results.get("success"):
        print(f"  ERRO:           {cal_results.get('error', 'unknown')}")

    # Cleanup
    if CLEANUP and not DRY_RUN and drive_results.get("success"):
        print("\n--- CLEANUP ---")
        print("  Removendo artefatos de smoke test...")
        # Cleanup implementation deferred — would delete test files/folders
        print("  (Cleanup não implementado nesta versão — remover manualmente)")
        print("  Pasta sandbox: 99_SANDBOX_HERMES_TESTES")

    # Summary
    overall_success = drive_results.get("success") and cal_results.get("success")
    print("\n" + "=" * 60)
    print(f"OVERALL: {'PASS' if overall_success else 'FAIL'}")
    print("=" * 60)

    return {
        "success": overall_success,
        "drive": drive_results,
        "calendar": cal_results,
        "smoke_lead_id": SMOKE_LEAD_ID,
        "dry_run": DRY_RUN,
    }
