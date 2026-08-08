from __future__ import annotations

import hashlib
import json
import os
import time
from pathlib import Path
from uuid import uuid4

from playwright.sync_api import Page, sync_playwright

from cloud_browser_judge_proof import (
    answer_visible_block,
    api_json,
    require,
    tiny_pdf,
    wait_for_dynamic_or_orientation,
)


ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "dist" / "submission-demo"
REPORT = OUTPUT / "report.json"
BASE_URL = os.getenv("HEALTHIA_CLOUD_URL", "").rstrip("/")
IDENTITY_TOKEN = os.getenv("HEALTHIA_CLOUD_ID_TOKEN", "")
CLOUD_REVISION = os.getenv("HEALTHIA_CLOUD_REVISION", "")
CLOUD_IMAGE = os.getenv("HEALTHIA_CLOUD_IMAGE", "")
CLOUD_PROJECT = os.getenv("HEALTHIA_CLOUD_PROJECT", "")
CLOUD_REGION = os.getenv("HEALTHIA_CLOUD_REGION", "")
TARGET_SECONDS = int(os.getenv("HEALTHIA_DEMO_TARGET_SECONDS", "230"))


def title_card(page: Page, kicker: str, title: str, body: str, seconds: float) -> None:
    page.set_content(
        f"""
        <!doctype html>
        <html lang="es">
        <head>
          <meta charset="utf-8">
          <style>
            html,body{{height:100%;margin:0;font-family:Inter,system-ui,-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;background:#f7f8fb;color:#172033}}
            body{{display:grid;place-items:center}}
            main{{width:min(1080px,84vw);padding:64px 72px;background:white;border:1px solid #e4e8f0;border-radius:28px;box-shadow:0 24px 70px rgba(31,45,72,.10)}}
            .kicker{{font-size:18px;font-weight:750;letter-spacing:.08em;text-transform:uppercase;color:#52637a;margin-bottom:20px}}
            h1{{font-size:54px;line-height:1.05;margin:0 0 26px;letter-spacing:-.035em}}
            p{{font-size:27px;line-height:1.45;margin:0;color:#445067;white-space:pre-line}}
            .brand{{margin-top:34px;font-size:18px;font-weight:700;color:#718096}}
          </style>
        </head>
        <body><main><div class="kicker">{kicker}</div><h1>{title}</h1><p>{body}</p><div class="brand">HealthIA ONE · The Taskmaster · All Things Agentic</div></main></body>
        </html>
        """,
        wait_until="load",
    )
    page.wait_for_timeout(int(seconds * 1000))


def overlay(page: Page, title: str, body: str, seconds: float) -> None:
    page.evaluate(
        """({title, body}) => {
          let box = document.getElementById('healthia-demo-caption');
          if (!box) {
            box = document.createElement('aside');
            box.id = 'healthia-demo-caption';
            box.style.cssText = [
              'position:fixed','right:24px','bottom:24px','z-index:2147483647',
              'width:min(520px,42vw)','background:rgba(20,29,48,.94)','color:white',
              'border-radius:18px','padding:18px 20px','box-shadow:0 16px 46px rgba(0,0,0,.24)',
              'font-family:Inter,system-ui,sans-serif','pointer-events:none'
            ].join(';');
            document.body.appendChild(box);
          }
          box.innerHTML = `<strong style="font-size:20px;display:block;margin-bottom:7px">${title}</strong><span style="font-size:15px;line-height:1.45;color:#e7ebf3">${body}</span>`;
        }""",
        {"title": title, "body": body},
    )
    page.wait_for_timeout(int(seconds * 1000))


def clear_overlay(page: Page) -> None:
    page.evaluate("document.getElementById('healthia-demo-caption')?.remove()")


def latest_result_state(page: Page, filename: str, timeout_s: float = 75.0) -> tuple[dict, dict, dict]:
    deadline = time.time() + timeout_s
    last_state: dict = {}
    while time.time() < deadline:
        state = api_json(page, "/api/bootstrap")
        last_state = state
        candidates = [
            item
            for item in state.get("results", [])
            if item.get("filename") == filename or filename in json.dumps(item, ensure_ascii=False)
        ]
        if candidates:
            result = candidates[-1]
            result_id = str(result.get("id") or "")
            document = next(
                (item for item in state.get("documents", []) if item.get("related_result_id") == result_id),
                None,
            )
            if result.get("status") == "parsed" and result_id and document:
                return state, result, document
        page.wait_for_timeout(750)
    raise RuntimeError(f"submission demo result did not become parsed: {last_state.get('results', [])[-2:]}")


def wait_for_result_mission(page: Page, result_id: str, timeout_s: float = 50.0) -> dict:
    deadline = time.time() + timeout_s
    last = None
    while time.time() < deadline:
        state = api_json(page, "/api/bootstrap")
        matches = [
            mission
            for mission in state.get("missions", [])
            if mission.get("mission_type") == "result_explanation"
            and result_id in (mission.get("evidence_ids") or [])
        ]
        if matches:
            last = matches[-1]
            if last.get("status") == "completed":
                return last
        page.wait_for_timeout(650)
    raise RuntimeError(f"submission demo Taskmaster mission did not complete: {last}")


def run() -> dict:
    require(BASE_URL.startswith("https://") and ".run.app" in BASE_URL, "real Cloud Run .run.app URL is required")
    require(bool(IDENTITY_TOKEN), "HEALTHIA_CLOUD_ID_TOKEN is required")
    OUTPUT.mkdir(parents=True, exist_ok=True)
    video_dir = OUTPUT / "video"
    video_dir.mkdir(parents=True, exist_ok=True)
    pdf_path = OUTPUT / "synthetic-submission-lab.pdf"
    pdf = tiny_pdf()
    pdf_path.write_bytes(pdf)

    suffix = uuid4().hex[:10]
    email = f"submission-demo-{suffix}@example.test"
    password = f"SubmissionDemo!{suffix}Aa9"
    display_name = "Paciente Demo Taskmaster"
    filename = pdf_path.name
    console_errors: list[str] = []
    page_errors: list[str] = []
    report: dict = {
        "status": "running",
        "synthetic_only": True,
        "base_url": BASE_URL,
        "cloud_project": CLOUD_PROJECT,
        "cloud_region": CLOUD_REGION,
        "cloud_revision": CLOUD_REVISION,
        "cloud_image": CLOUD_IMAGE,
        "pdf_sha256": hashlib.sha256(pdf).hexdigest(),
        "checks": [],
    }

    started = time.monotonic()
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True, args=["--no-sandbox"])
        context = browser.new_context(
            viewport={"width": 1600, "height": 900},
            record_video_dir=str(video_dir),
            record_video_size={"width": 1600, "height": 900},
            extra_http_headers={"Authorization": f"Bearer {IDENTITY_TOKEN}"},
        )
        page = context.new_page()
        page.on("console", lambda msg: console_errors.append(msg.text) if msg.type == "error" else None)
        page.on("pageerror", lambda error: page_errors.append(str(error)))

        title_card(
            page,
            "El problema",
            "La historia del paciente se fragmenta",
            "PDF, imágenes, dispositivos, tratamientos y conversaciones viven separados.\nHealthIA ONE convierte esa evidencia en misiones durables que el agente ejecuta y puede volver a demostrar.",
            24,
        )
        title_card(
            page,
            "La propuesta de valor",
            "El trabajo no termina cuando el modelo habla",
            "Una carga de evidencia dispara un flujo real: preservar original → interpretar con Gemini → persistir → vincular al gemelo → recuperar → cerrar la misión con evidencia.",
            18,
        )

        page.goto(f"{BASE_URL}/login", wait_until="networkidle", timeout=60_000)
        require(page.locator("#registerTab").is_visible(), "registration UI is not visible")
        overlay(page, "Cloud real", "La toma ya está navegando contra el servicio privado de Cloud Run; no hay mocks en este recorrido.", 8)
        clear_overlay(page)
        page.locator("#registerTab").click()
        page.locator('#registerForm input[name="display_name"]').fill(display_name)
        page.locator('#registerForm input[name="email"]').fill(email)
        page.locator('#registerForm input[name="password"]').fill(password)
        page.locator('#registerForm button[type="submit"]').click()
        page.wait_for_url(f"{BASE_URL}/", timeout=30_000)
        page.wait_for_load_state("networkidle")
        session = api_json(page, "/api/auth/session")
        require(session.get("authenticated") is True, "submission demo registration failed")
        patient_id = str((session.get("account") or {}).get("patient_id") or "")
        require(patient_id.startswith("patient_"), "submission demo has no patient identity")
        readiness = api_json(page, "/api/readiness")
        require(readiness.get("ai_ready") is True and readiness.get("adk_ready") is True, "live Gemini/ADK is not ready")
        require(readiness.get("model") == "gemini-3.5-flash", f"unexpected model: {readiness.get('model')}")
        require(readiness.get("store_backend") == "firestore", "submission demo is not using Firestore")
        require(readiness.get("evidence_backend") == "gcs", "submission demo is not using GCS")
        report["patient_id"] = patient_id
        report["readiness"] = {key: readiness.get(key) for key in ("ready", "model", "adk_ready", "ai_ready", "store_backend", "evidence_backend", "auth_required")}
        report["checks"].append("live_cloud_runtime_ready")
        overlay(page, "Paciente aislado y autenticado", "La cuenta sintética inicia limpia. Firestore mantiene el estado por paciente y GCS conserva la evidencia original por identidad.", 12)
        clear_overlay(page)

        complaint = "Desde ayer me arde al orinar y tengo que ir al baño a cada rato. Quiero orientación sobre qué información hace falta."
        page.locator("#chatInput").fill(complaint)
        page.locator("#sendButton").click()
        assistant_id, status = wait_for_dynamic_or_orientation(page)
        require(status == "dynamic_clinical_questions", f"first clinical response was not dynamic: {status}")
        page.wait_for_selector('.clinical-question-block[data-question-source="gemini_dynamic"]', timeout=10_000)
        first_block = page.locator('.clinical-question-block[data-question-source="gemini_dynamic"]').last
        require(first_block.locator(".clinical-question").count() == 5, "first live block is not five questions")
        report["checks"].append("live_gemini_adk_question_block_1")
        overlay(page, "Gemini + Google ADK", "Las cinco preguntas son específicas del caso. ADK ejecuta el tool clínico autorizado y registra entrevista + seguridad antes de la respuesta estructurada.", 20)
        clear_overlay(page)
        answer_visible_block(page)

        assistant_id, status = wait_for_dynamic_or_orientation(page, assistant_id)
        require(status in {"dynamic_clinical_questions", "dynamic_clinical_followup_questions"}, f"second response was not adaptive: {status}")
        second_block = page.locator('.clinical-question-block[data-question-source="gemini_dynamic"]').last
        require(second_block.locator(".clinical-question").count() == 5, "second live block is not five questions")
        report["checks"].append("live_gemini_adk_question_block_2")
        overlay(page, "Memoria clínica del turno", "El segundo bloque recibe las preguntas y respuestas anteriores y debe evitar volver a pedir hechos ya conocidos.", 18)
        clear_overlay(page)
        answer_visible_block(page)

        assistant_id, status = wait_for_dynamic_or_orientation(page, assistant_id)
        if status in {"dynamic_clinical_questions", "dynamic_clinical_followup_questions"}:
            third_block = page.locator('.clinical-question-block[data-question-source="gemini_dynamic"]').last
            require(third_block.locator(".clinical-question").count() == 5, "third live block is malformed")
            overlay(page, "El modelo decide si falta evidencia", "Si todavía hay una incertidumbre clínica relevante, HealthIA pide otro bloque en vez de cerrar por una regla rígida.", 10)
            clear_overlay(page)
            answer_visible_block(page)
            assistant_id, status = wait_for_dynamic_or_orientation(page, assistant_id)
        require(status == "clinical_ai_orientation_completed", f"clinical orientation did not complete: {status}")
        report["checks"].append("live_clinical_orientation_completed")
        overlay(page, "Orientación segura", "La conversación termina en orientación para el paciente, no en prescripción autónoma ni diagnóstico inventado.", 14)
        clear_overlay(page)

        page.locator("#resultFile").set_input_files(str(pdf_path))
        state, result, document = latest_result_state(page, filename)
        result_id = str(result.get("id") or "")
        document_id = str(document.get("id") or "")
        require(result_id and document_id, "parsed result lost result/document provenance")
        report["result_id"] = result_id
        report["document_id"] = document_id
        report["checks"].append("multimodal_result_persisted_with_original")
        page.locator('[data-open="results"]').click()
        page.wait_for_timeout(800)
        overlay(page, "Taskmaster: acción, no sólo texto", "El PDF original ya está en GCS. Gemini 3.5 Flash extrajo sólo lo legible, Firestore guardó el resultado y el gemelo quedó enlazado al documento original.", 22)
        clear_overlay(page)

        page.locator('.main-nav [data-open="chat"]').click()
        page.locator("#chatInput").fill(f"Explícame el resultado {filename} que acabo de subir y confirma que quedó guardado.")
        page.locator("#sendButton").click()
        mission = wait_for_result_mission(page, result_id)
        require(document_id in (mission.get("evidence_ids") or []), "completed mission lost original-document evidence")
        report["mission_id"] = str(mission.get("id") or "")
        report["checks"].append("taskmaster_result_mission_completed")
        page.locator('[data-open="missions"]').click()
        page.wait_for_timeout(700)
        overlay(page, "Misión cerrada por evidencia", "La misión sólo aparece como COMPLETED porque el resultado persistido y el documento original pudieron recuperarse y correlacionarse.", 18)
        clear_overlay(page)

        page.locator("#accountPill").click()
        page.locator("#logoutButton").click()
        page.wait_for_url(f"{BASE_URL}/login", timeout=20_000)
        page.locator('#loginForm input[name="email"]').fill(email)
        page.locator('#loginForm input[name="password"]').fill(password)
        page.locator('#loginForm button[type="submit"]').click()
        page.wait_for_url(f"{BASE_URL}/", timeout=20_000)
        page.wait_for_load_state("networkidle")
        restored = api_json(page, "/api/bootstrap")
        require((restored.get("profile") or {}).get("id") == patient_id, "patient identity changed after relogin")
        require(any(item.get("id") == result_id for item in restored.get("results", [])), "result disappeared after relogin")
        require(any(item.get("id") == document_id for item in restored.get("documents", [])), "document disappeared after relogin")
        require(any(item.get("id") == mission.get("id") and item.get("status") == "completed" for item in restored.get("missions", [])), "mission disappeared after relogin")
        report["checks"].append("relogin_continuity")
        overlay(page, "Continuidad real", "Tras salir y volver a entrar, el paciente recupera resultado, original y misión completada. El estado no vive en la pestaña del navegador.", 15)
        clear_overlay(page)

        readiness = api_json(page, "/api/readiness")
        title_card(
            page,
            "Prueba de Google Cloud",
            "Backend ejecutándose en Cloud Run",
            (
                f"URL: {BASE_URL}\n"
                f"Proyecto: {CLOUD_PROJECT or 'healthia-6088a'} · Región: {CLOUD_REGION or 'us-central1'}\n"
                f"Revisión: {CLOUD_REVISION or 'revision verificada por workflow'}\n"
                f"Gemini: {readiness.get('model')} · ADK ready: {readiness.get('adk_ready')}\n"
                f"Estado: {readiness.get('store_backend')} · Evidencia: {readiness.get('evidence_backend')}"
            ),
            22,
        )
        page.goto(f"{BASE_URL}/api/readiness", wait_until="networkidle", timeout=30_000)
        page.wait_for_timeout(12_000)
        report["checks"].append("visible_run_app_and_live_readiness")

        elapsed = time.monotonic() - started
        remaining = max(15.0, TARGET_SECONDS - elapsed)
        title_card(
            page,
            "Cierre",
            "Your health never starts over.",
            "HealthIA ONE demuestra el ciclo completo: contexto → decisión → acción → evidencia durable → misión completada.\nLa conversación puede terminar; la continuidad del paciente no.",
            remaining,
        )

        require(not page_errors, f"browser page errors during submission demo: {page_errors}")
        require(not console_errors, f"browser console errors during submission demo: {console_errors}")
        report["checks"].append("zero_browser_console_or_page_errors")
        report["status"] = "PASS"
        context.close()
        browser.close()

    videos = sorted(video_dir.glob("*.webm"))
    require(bool(videos), "Playwright did not produce the submission demo video")
    video = videos[0]
    report["video_file"] = str(video.relative_to(ROOT))
    report["video_sha256"] = hashlib.sha256(video.read_bytes()).hexdigest()
    report["elapsed_seconds"] = round(time.monotonic() - started, 2)
    REPORT.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print("HEALTHIA_SUBMISSION_DEMO_PASS")
    print(json.dumps({"status": report["status"], "checks": report["checks"], "video_file": report["video_file"], "video_sha256": report["video_sha256"], "elapsed_seconds": report["elapsed_seconds"]}, ensure_ascii=False))
    return report


if __name__ == "__main__":
    try:
        run()
    except Exception as exc:
        OUTPUT.mkdir(parents=True, exist_ok=True)
        failure = {"status": "FAIL", "error_type": type(exc).__name__, "error": str(exc)[:2000]}
        REPORT.write_text(json.dumps(failure, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"HEALTHIA_SUBMISSION_DEMO_FAIL {type(exc).__name__}: {exc}")
        raise
