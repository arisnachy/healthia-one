from __future__ import annotations

import json
import os
import re
from pathlib import Path

os.environ["HEALTHIA_STORE_BACKEND"] = "memory"
os.environ["HEALTHIA_LLM_BACKEND"] = "mock"
os.environ["HEALTHIA_PROACTIVE_ENABLED"] = "false"
os.environ["GEMINI_API_KEY"] = "browser-smoke-fake-key"

from fastapi.testclient import TestClient
from playwright.sync_api import sync_playwright

from app.main import app, service
from healthia_one.adk_gemini import AdkGeminiResponder
from healthia_one.clinical_intake import ANSWER_PREFIX
from healthia_one.config import Settings

ROOT = Path(__file__).resolve().parents[1]
WEB = ROOT / "web"
OUTPUT = ROOT / "dist" / "browser-smoke"


def plan(stage: int) -> dict:
    if stage == 1:
        questions = [
            ("pain_location", "¿Dónde sientes la molestia con mayor claridad?", ["Solo al orinar", "Parte baja del abdomen", "Espalda o costado", "Zona genital"], True),
            ("urine_change", "¿Has notado cambios visibles u olor diferente en la orina?", ["Sin cambios", "Orina turbia", "Sangre visible", "Olor más fuerte"], True),
            ("case_alarm", "¿Ha ocurrido alguna señal de alarma desde que empezó?", ["Ninguna", "Fiebre alta o escalofríos", "Vómitos repetidos", "Empeoramiento rápido"], True),
            ("genital_context", "¿Hay flujo, irritación genital o una posibilidad de embarazo?", ["No", "Flujo o irritación", "Embarazo posible", "No estoy segura"], True),
            ("prior_episode", "¿Tuviste antes un episodio parecido y cómo se confirmó?", ["Nunca", "Sí, sin estudios", "Sí, con análisis de orina", "No lo recuerdo"], False),
        ]
        selected = ["interview", "safety", "medication"]
        focus = "Distinguir síntomas urinarios bajos de señales que requieren otra dirección"
    else:
        questions = [
            ("hydration", "¿Cuánto líquido has podido tomar desde que comenzaron las molestias?", ["Cantidad habitual", "Menos de lo habitual", "Muy poco", "No lo sé"], False),
            ("voiding_pattern", "¿La urgencia aparece con poca cantidad de orina o con un volumen habitual?", ["Poca cantidad", "Cantidad habitual", "Varía", "No lo sé"], False),
            ("new_alarm", "¿Desde el bloque anterior apareció alguna señal de alarma nueva?", ["Ninguna", "Fiebre alta", "Dolor en espalda o costado", "Vómitos o debilidad"], True),
            ("medication_detail", "¿Qué medicamento o producto usaste y a qué hora?", ["No usé ninguno", "Analgésico", "Antibiótico previo", "Otro producto"], True),
            ("priority_goal", "¿Qué necesitas resolver primero con un profesional?", ["Saber el nivel de urgencia", "Confirmar la causa", "Revisar un análisis", "Planificar seguimiento"], True),
        ]
        selected = ["interview", "safety", "history", "follow_up"]
        focus = "Completar el contexto sin repetir lo ya contestado"
    return {
        "intent": "clinical_consultation",
        "clinical_focus": focus,
        "why_these_questions": [
            "Buscan datos que cambian el nivel de atención",
            "Separan explicaciones plausibles sin confirmar un diagnóstico",
        ],
        "missing_information": ["localización", "señales de alarma", "contexto longitudinal"],
        "selected_specialists": [{"role": role, "reason": "necesario para este bloque"} for role in selected],
        "questions": [
            {
                "id": question_id,
                "prompt": prompt,
                "options": options,
                "multiple": multiple,
                "detail_placeholder": "Agrega un detalle si lo deseas",
            }
            for question_id, prompt, options, multiple in questions
        ],
    }


class BrowserResponder(AdkGeminiResponder):
    """Deterministic browser fixture for the current ADK/Gemini patient contract.

    The real provider/ADK trajectory is proven separately by the encrypted live
    workflow. This fixture only proves that the browser renders the exact runtime
    states that the current responder produces, without spending tokens in CI.
    """

    def __init__(self, settings: Settings) -> None:
        super().__init__(settings)
        self.simulated_ai_steps = 0

    def _generate_clinical_block(self, state, *, chief_complaint, stage, previous_answers):
        self.simulated_ai_steps += 1
        return plan(stage)

    def _generate_clinical_resolution(self, state, *, chief_complaint, stage, answers):
        self.simulated_ai_steps += 1
        return {
            "decision": "summarize",
            "clinical_focus": "Orientar un cuadro urinario sin confirmar un diagnóstico",
            "missing_information": [],
            "decision_reason": "Los dos bloques ya reúnen suficiente contexto para orientar el siguiente paso sin otra ronda rutinaria.",
            "patient_message": (
                "Ya reuní lo necesario para orientarte con esta consulta. Por el patrón que describiste, una causa urinaria baja "
                "es una posibilidad que un profesional puede valorar, pero esta conversación no confirma un diagnóstico. "
                "Por ahora no aparecen en tus respuestas las señales de alarma seleccionadas en el formulario. Si surge fiebre alta, "
                "dolor en el costado, vómitos persistentes, embarazo o un empeoramiento importante, busca valoración presencial con mayor prioridad. "
                "Cuando hables con el profesional, cuéntale cuándo empezó, la frecuencia urinaria, los cambios visibles y cualquier medicamento usado."
            ),
            "possible_explanations": [
                {
                    "name": "Irritación o infección urinaria baja como posibilidad",
                    "why_possible": "Ardor y aumento de frecuencia urinaria",
                    "why_uncertain": "La conversación no sustituye examen ni pruebas clínicas",
                }
            ],
            "care_level": "routine_professional",
        }


def answer_payload(interview: dict) -> str:
    answers = [
        {"question_id": question["id"], "question_prompt": question["prompt"], "selected": [question["options"][0]], "detail": ""}
        for question in interview["question_block"]["questions"]
    ]
    return ANSWER_PREFIX + json.dumps(
        {"interview_id": interview["id"], "stage": interview["stage"], "answers": answers},
        ensure_ascii=False,
    )


def backend_fixture() -> tuple[dict, list[dict], int]:
    responder = BrowserResponder(
        Settings(
            llm_backend="gemini_api",
            store_backend="memory",
            cost_mode="guarded",
            ai_request_limit=4,
            cost_guard_start_enabled=True,
            ai_max_output_tokens=1400,
            proactive_enabled=False,
        )
    )
    service.gemini = responder
    with TestClient(app) as client:
        client.post("/api/demo/reset").raise_for_status()
        bootstrap = client.get("/api/bootstrap").json()
        first = client.post(
            "/api/chat",
            json={"message": "Desde ayer me arde al orinar y tengo que ir al baño a cada rato"},
        ).json()
        second = client.post(
            "/api/chat",
            json={"message": answer_payload(first["message"]["metadata"]["clinical_interview"])},
        ).json()
        final = client.post(
            "/api/chat",
            json={"message": answer_payload(second["message"]["metadata"]["clinical_interview"])},
        ).json()
    return bootstrap, [first, second, final], responder.simulated_ai_steps


def mock_script(bootstrap: dict, responses: list[dict]) -> str:
    return f"""
window.__mockSnapshot = {json.dumps(bootstrap, ensure_ascii=False)};
window.__mockChatResponses = {json.dumps(responses, ensure_ascii=False)};
window.__mockChatIndex = 0;
window.__recognitionInstances = 0;
window.SpeechRecognition = class {{
  constructor() {{ window.__recognitionInstances += 1; }}
  start() {{ this.onstart?.(); }}
  stop() {{ this.onend?.(); }}
}};
class MockResponse {{
  constructor(body,status=200) {{ this._body=body; this.status=status; this.ok=status>=200&&status<300; }}
  async json() {{ return JSON.parse(JSON.stringify(this._body)); }}
}}
window.fetch = async function(path, options={{}}) {{
  const url=String(path);
  if((options.method||'GET').toUpperCase()==='DELETE' && url.includes('/api/devices/')) {{
    const connection=window.__mockSnapshot.device_summary.connections.find(item=>url.endsWith(item.id));
    if(connection) connection.status='disconnected';
    return new MockResponse({{disconnected:true}});
  }}
  if(url.includes('/api/readiness')) return new MockResponse({{ready:true,llm_backend:'gemini_api',model:'gemini-3.6-flash',ai_ready:true,adk_ready:true}});
  if(url.includes('/api/devices')) return new MockResponse(window.__mockSnapshot.device_summary);
  if(url.includes('/api/bootstrap')) return new MockResponse(window.__mockSnapshot);
  if(url.includes('/api/cost-control')) return new MockResponse({{mode:'guarded',enabled:true,requests_used:3,requests_remaining:1,request_limit:4,max_output_tokens:1400,llm_backend:'gemini_api',model:'gemini-3.6-flash',api_key_configured:true,ui_control_available:true}});
  if(url.includes('/api/integrations/providers')) return new MockResponse({{providers:[]}});
  if(url.includes('/api/demo/tick')) return new MockResponse({{created:0,messages:[]}});
  if(url.includes('/api/demo/reset')) return new MockResponse({{reset:true,patient_id:'patient_demo'}});
  if(url.includes('/api/chat')) {{
    const payload=JSON.parse(options.body||'{{}}');
    const patient={{id:'browser_patient_'+Date.now()+'_'+window.__mockChatIndex,patient_id:'patient_demo',role:'patient',author:window.__mockSnapshot.profile.display_name,content:payload.message,created_at:new Date().toISOString(),risk_level:'info',mission_id:null,agent_plan:[],metadata:{{}}}};
    const response=window.__mockChatResponses[window.__mockChatIndex++];
    window.__mockSnapshot.messages.push(patient,response.message);
    if(response.mission) {{
      const missionIndex=window.__mockSnapshot.missions.findIndex(item=>item.id===response.mission.id);
      if(missionIndex>=0) window.__mockSnapshot.missions[missionIndex]=response.mission;
      else window.__mockSnapshot.missions.push(response.mission);
    }}
    setTimeout(() => window.__mockEventSource?.onmessage?.({{data: JSON.stringify({{type:'state',section:'chat'}})}}), 0);
    return new MockResponse(response);
  }}
  return new MockResponse({{}},200);
}};
window.EventSource = class {{ constructor(url){{this.url=url; window.__mockEventSource=this;}} close(){{}} }};
"""


def require(condition: bool, message: str) -> None:
    if not condition:
        raise RuntimeError(message)


def reveal_and_answer(block) -> None:
    require(block.locator(".clinical-question").count() == 5, "dynamic clinical block is not exactly five questions")
    require(block.locator(".clinical-question:visible").count() == 2, "progressive block must begin with exactly two visible questions")
    reveal = block.locator(".clinical-show-all")
    require(reveal.is_visible(), "progressive 2+3 continuation control is missing")
    reveal.click()
    require(block.locator(".clinical-question:visible").count() == 5, "remaining three questions were not revealed")
    for field in block.locator(".clinical-question").all():
        field.locator(".clinical-option").first.click()
    submit = block.locator(".clinical-submit")
    require(submit.is_visible(), "clinical submit did not become visible after progressive reveal")
    submit.click()


def run() -> dict:
    bootstrap, responses, simulated_ai_steps = backend_fixture()
    require(simulated_ai_steps == 3, f"expected two question generations plus one resolution, found {simulated_ai_steps}")
    require(all(item["message"]["metadata"].get("question_source") == "gemini_dynamic" for item in responses[:2]), "dynamic question source missing")
    require(responses[2]["message"]["metadata"].get("llm_status") == "clinical_ai_orientation_completed", "patient orientation state missing")
    final_mission = responses[2].get("mission") or {}
    require(final_mission.get("status") == "waiting_professional", "backend did not return updated existing mission")
    require(
        final_mission.get("next_action") == "Revisar la orientación con un profesional y actualizar HealthIA con el resultado",
        "backend mission response carries stale next action",
    )
    require("ai_clinical_orientation_generated" in (final_mission.get("closure_evidence") or []), "backend mission response lost AI orientation evidence")

    bootstrap["device_summary"]["connections"] = [
        {
            "id": "hc_browser_verified",
            "provider": "health_connect",
            "device_id": "browser-phone",
            "display_name": "Browser Health Connect",
            "status": "connected",
            "permissions": ["steps", "heart_rate"],
            "background_read": False,
            "last_sync_at": bootstrap["updated_at"],
            "last_error": "",
        }
    ]
    html = (WEB / "index.html").read_text(encoding="utf-8")
    html = re.sub(r'<link[^>]+href="/assets/[^"]+"[^>]*>', "", html)
    html = re.sub(r'<script[^>]+src="/assets/[^"]+"[^>]*></script>', "", html)
    OUTPUT.mkdir(parents=True, exist_ok=True)
    report: dict = {"status": "PASS", "simulated_ai_steps": simulated_ai_steps, "console_errors": [], "page_errors": [], "checks": {}}

    with sync_playwright() as playwright:
        launch: dict = {"headless": True, "args": ["--no-sandbox"]}
        explicit = os.getenv("HEALTHIA_CHROMIUM_EXECUTABLE")
        if explicit:
            launch["executable_path"] = explicit
        elif Path("/usr/bin/chromium").exists():
            launch["executable_path"] = "/usr/bin/chromium"
        browser = playwright.chromium.launch(**launch)
        page = browser.new_page(viewport={"width": 1600, "height": 900}, locale="en-US")
        page.on("console", lambda message: report["console_errors"].append(message.text) if message.type == "error" else None)
        page.on("pageerror", lambda error: report["page_errors"].append(str(error)))
        page.set_content(html, wait_until="domcontentloaded")
        page.add_script_tag(content=mock_script(bootstrap, responses))
        for stylesheet in ("styles.css", "interactions.css", "clinical-council.css", "cost-control.css"):
            page.add_style_tag(path=str(WEB / stylesheet))
        page.evaluate(
            """() => { for (const name of ['runtime','providers','clinical-council','cost-control']) { const script=document.createElement('script'); script.setAttribute('data-healthia-'+name,'true'); document.head.append(script); } }"""
        )
        for script in (
            "app.js",
            "patient-record.js",
            "family-documents.js",
            "continuity.js",
            "privacy-controls.js",
            "profile-devices.js",
            "runtime-integrations.js",
            "provider-integrations.js",
            "clinical-council.js",
            "cost-control.js",
            "icons.js",
        ):
            page.add_script_tag(path=str(WEB / script))
        page.wait_for_timeout(900)
        page.screenshot(path=str(OUTPUT / "01-home.png"), full_page=True)

        require(page.locator("#accountPill strong").inner_text() == "Ana Martínez", "patient identity not consolidated")
        require(page.locator(".patient-chip").count() == 0, "duplicate identity remains")
        require(page.locator("html").get_attribute("lang") == "en", "en-US browser locale did not render the English shell")
        page.locator("#collapseLeft").click()
        page.wait_for_timeout(150)
        require(page.locator(".main-nav button:visible").count() == 6, "collapsed navigation lost core destinations")
        require(page.locator("#newConsultation:visible").count() == 1, "collapsed new-consultation control missing")
        page.screenshot(path=str(OUTPUT / "02-collapsed.png"), full_page=True)
        page.locator("#expandLeft").click()

        page.locator('.main-nav [data-open="devices"]').click()
        page.wait_for_selector('#view-devices.is-active [data-disconnect-device="hc_browser_verified"]')
        require(page.get_by_text("Authorized: steps, heart rate", exact=False).count() > 0, "device permissions are not visible")
        require(page.get_by_text("The bridge credential authenticates the phone", exact=False).count() > 0, "device truth boundary is missing")
        page.screenshot(path=str(OUTPUT / "03-devices.png"), full_page=True)
        page.once("dialog", lambda dialog: dialog.accept())
        page.locator('[data-disconnect-device="hc_browser_verified"]').click()
        page.wait_for_function("window.__mockSnapshot.device_summary.connections[0].status === 'disconnected'")
        page.locator('.main-nav [data-open="chat"]').click()

        input_box = page.locator("#chatInput")
        input_box.click()
        input_box.press_sequentially("abc++def", delay=25)
        page.wait_for_timeout(500)
        require(input_box.input_value() == "abc++def", "chat input duplicated characters or lost typed text")
        page.locator("#voiceButton").click()
        require(page.evaluate("window.__recognitionInstances") == 1, "voice input created duplicate recognition handlers")
        page.locator("#voiceButton").click(force=True)
        input_box.fill("")

        page.locator("#chatInput").fill("Desde ayer me arde al orinar y tengo que ir al baño a cada rato")
        page.locator("#sendButton").click()
        page.wait_for_selector('.clinical-question-block[data-question-source="gemini_dynamic"]', timeout=10_000)
        first_block = page.locator(".clinical-question-block").last
        require(first_block.locator(".clinical-question").count() == 5, "first dynamic block does not have five questions")
        require(first_block.bounding_box() and first_block.bounding_box()["height"] > 100, "first block is not visible")
        require(first_block.locator(".clinical-source.is-dynamic").inner_text() == "Questions created for this case", "patient-natural dynamic source badge missing")
        require(page.locator(".chat-pending").count() == 0, "pending message remained after fast response")
        page.screenshot(path=str(OUTPUT / "03-dynamic-block.png"), full_page=True)

        reveal_and_answer(first_block)
        page.wait_for_function("window.__mockChatIndex >= 2")
        page.wait_for_timeout(350)
        second_block = page.locator(".clinical-question-block").last
        require(second_block.get_attribute("data-stage") == "2", "second block did not render")
        reveal_and_answer(second_block)
        page.wait_for_function("window.__mockChatIndex >= 3")
        page.wait_for_timeout(350)
        require(page.get_by_text("Ya reuní lo necesario para orientarte con esta consulta.", exact=False).count() > 0, "Spanish patient-facing clinical orientation is missing after Spanish input")
        require(page.get_by_text("¿Dónde sientes la molestia con mayor claridad?").count() > 0, "final transcript lost readable question labels")
        require(page.get_by_text("pain_location", exact=True).count() == 0, "internal question id leaked into patient transcript")
        require(page.get_by_text("Revisar la orientación con un profesional y actualizar HealthIA con el resultado").count() > 0, "mission card remained stale after AI orientation")
        require(page.locator(".action-receipt").count() > 0, "visible action receipt was not rendered")
        require(page.locator(".chat-pending").count() == 0, "pending message remained after completion")
        require(not report["console_errors"] and not report["page_errors"], "browser emitted errors")
        page.screenshot(path=str(OUTPUT / "04-final.png"), full_page=True)
        browser.close()

    report["checks"] = {
        "single_identity": "pass",
        "english_shell_locale": "pass",
        "spanish_input_preserves_spanish_clinical_content": "pass",
        "collapsed_navigation": "pass",
        "device_permissions_and_truth_boundary": "pass",
        "device_disconnect_action": "pass",
        "chat_input_exact_typing": "pass",
        "single_voice_handler": "pass",
        "first_message_visible": "pass",
        "dynamic_question_source": "pass",
        "two_five_question_blocks": "pass",
        "progressive_two_plus_three_presentation": "pass",
        "pending_race_removed": "pass",
        "canonical_mission_returned": "pass",
        "mission_upsert_without_sse_race": "pass",
        "patient_facing_orientation": "pass",
        "visible_action_receipt": "pass",
        "readable_transcript_labels": "pass",
    }
    (OUTPUT / "report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    return report


if __name__ == "__main__":
    print(json.dumps(run(), ensure_ascii=False, indent=2))
