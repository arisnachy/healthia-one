from __future__ import annotations

import json
import os
import re
from pathlib import Path
from types import SimpleNamespace

os.environ["HEALTHIA_STORE_BACKEND"] = "memory"
os.environ["HEALTHIA_LLM_BACKEND"] = "mock"
os.environ["HEALTHIA_PROACTIVE_ENABLED"] = "false"
os.environ["GEMINI_API_KEY"] = "browser-smoke-fake-key"

from fastapi.testclient import TestClient
from playwright.sync_api import sync_playwright

from app.main import app, service
from healthia_one.clinical_intake import ANSWER_PREFIX
from healthia_one.config import Settings
from healthia_one.gemini import GeminiResponder

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


class FakeInteractions:
    def __init__(self) -> None:
        self.calls: list[dict] = []

    def create(self, **kwargs):
        self.calls.append(kwargs)
        payload = json.loads(kwargs["input"])
        stage = int(payload.get("stage", 1))
        return SimpleNamespace(outputs=[SimpleNamespace(text=json.dumps(plan(stage), ensure_ascii=False))])


class FakeClient:
    def __init__(self) -> None:
        self.interactions = FakeInteractions()


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
    fake_client = FakeClient()
    service.gemini = GeminiResponder(
        Settings(
            llm_backend="gemini_api",
            store_backend="memory",
            cost_mode="guarded",
            ai_request_limit=4,
            cost_guard_start_enabled=True,
            ai_max_output_tokens=900,
            proactive_enabled=False,
        ),
        client_factory=lambda: fake_client,
    )
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
    return bootstrap, [first, second, final], len(fake_client.interactions.calls)


def mock_script(bootstrap: dict, responses: list[dict]) -> str:
    return f"""
window.__mockSnapshot = {json.dumps(bootstrap, ensure_ascii=False)};
window.__mockChatResponses = {json.dumps(responses, ensure_ascii=False)};
window.__mockChatIndex = 0;
class MockResponse {{
  constructor(body,status=200) {{ this._body=body; this.status=status; this.ok=status>=200&&status<300; }}
  async json() {{ return JSON.parse(JSON.stringify(this._body)); }}
}}
window.fetch = async function(path, options={{}}) {{
  const url=String(path);
  if(url.includes('/api/readiness')) return new MockResponse({{ready:true,llm_backend:'gemini_api',model:'gemini-3.6-flash',ai_ready:true,adk_ready:true}});
  if(url.includes('/api/bootstrap')) return new MockResponse(window.__mockSnapshot);
  if(url.includes('/api/cost-control')) return new MockResponse({{mode:'guarded',enabled:true,requests_used:2,requests_remaining:2,request_limit:4,max_output_tokens:900,llm_backend:'gemini_api',model:'gemini-3.6-flash',api_key_configured:true,ui_control_available:true}});
  if(url.includes('/api/integrations/providers')) return new MockResponse({{providers:[]}});
  if(url.includes('/api/demo/tick')) return new MockResponse({{created:0,messages:[]}});
  if(url.includes('/api/demo/reset')) return new MockResponse({{reset:true,patient_id:'patient_demo'}});
  if(url.includes('/api/chat')) {{
    const payload=JSON.parse(options.body||'{{}}');
    const patient={{id:'browser_patient_'+Date.now()+'_'+window.__mockChatIndex,patient_id:'patient_demo',role:'patient',author:window.__mockSnapshot.profile.display_name,content:payload.message,created_at:new Date().toISOString(),risk_level:'info',mission_id:null,agent_plan:[],metadata:{{}}}};
    const response=window.__mockChatResponses[window.__mockChatIndex++];
    window.__mockSnapshot.messages.push(patient,response.message);
    if(response.mission) window.__mockSnapshot.missions.push(response.mission);
    if(response.message?.metadata?.clinical_interview?.status==='completed') {{
      const mission=window.__mockSnapshot.missions.find(item=>item.id===response.message.mission_id);
      if(mission) {{ mission.status='waiting_professional'; mission.next_action='Revisar la síntesis clínica y confirmar el nivel de atención con un profesional'; mission.closure_evidence=['interview_two_blocks_completed']; }}
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


def run() -> dict:
    bootstrap, responses, model_calls = backend_fixture()
    require(model_calls == 2, f"expected two model calls, found {model_calls}")
    require(all(item["message"]["metadata"].get("question_source") == "gemini_dynamic" for item in responses[:2]), "dynamic question source missing")

    html = (WEB / "index.html").read_text(encoding="utf-8")
    html = re.sub(r'<link[^>]+href="/assets/[^"]+"[^>]*>', "", html)
    html = re.sub(r'<script[^>]+src="/assets/[^"]+"[^>]*></script>', "", html)
    OUTPUT.mkdir(parents=True, exist_ok=True)
    report: dict = {"status": "PASS", "model_calls": model_calls, "console_errors": [], "page_errors": [], "checks": {}}

    with sync_playwright() as playwright:
        launch: dict = {"headless": True, "args": ["--no-sandbox"]}
        explicit = os.getenv("HEALTHIA_CHROMIUM_EXECUTABLE")
        if explicit:
            launch["executable_path"] = explicit
        elif Path("/usr/bin/chromium").exists():
            launch["executable_path"] = "/usr/bin/chromium"
        browser = playwright.chromium.launch(**launch)
        page = browser.new_page(viewport={"width": 1600, "height": 900})
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
        page.locator("#collapseLeft").click()
        page.wait_for_timeout(150)
        require(page.locator(".main-nav button:visible").count() == 6, "collapsed navigation lost icons")
        require(page.locator("#newConsultation:visible").count() == 1, "collapsed new-consultation control missing")
        page.screenshot(path=str(OUTPUT / "02-collapsed.png"), full_page=True)
        page.locator("#expandLeft").click()

        page.locator("#chatInput").fill("Desde ayer me arde al orinar y tengo que ir al baño a cada rato")
        page.locator("#sendButton").click()
        page.wait_for_selector('.clinical-question-block[data-question-source="gemini_dynamic"]', timeout=10_000)
        first_block = page.locator(".clinical-question-block").last
        require(first_block.locator(".clinical-question").count() == 5, "first dynamic block does not have five questions")
        require(first_block.bounding_box() and first_block.bounding_box()["height"] > 100, "first block is not visible")
        require(first_block.locator(".clinical-source.is-dynamic").inner_text() == "Gemini · preguntas adaptativas", "dynamic source badge missing")
        require(page.locator(".chat-pending").count() == 0, "pending message remained after fast response")
        page.screenshot(path=str(OUTPUT / "03-dynamic-block.png"), full_page=True)

        for field in first_block.locator(".clinical-question").all():
            field.locator(".clinical-option").first.click()
        first_block.locator(".clinical-submit").click()
        page.wait_for_function("window.__mockChatIndex >= 2")
        page.wait_for_timeout(350)
        second_block = page.locator(".clinical-question-block").last
        require(second_block.get_attribute("data-stage") == "2", "second block did not render")
        require(second_block.locator(".clinical-question").count() == 5, "second dynamic block does not have five questions")

        for field in second_block.locator(".clinical-question").all():
            field.locator(".clinical-option").first.click()
        second_block.locator(".clinical-submit").click()
        page.wait_for_function("window.__mockChatIndex >= 3")
        page.wait_for_timeout(350)
        require(page.get_by_text("Síntesis para la junta clínica").count() > 0, "final clinical summary is missing")
        require(page.get_by_text("¿Dónde sientes la molestia con mayor claridad?").count() > 0, "final summary lost readable question labels")
        require(page.get_by_text("pain_location", exact=True).count() == 0, "internal question id leaked into patient summary")
        require(page.get_by_text("Revisar la síntesis clínica y confirmar el nivel de atención con un profesional").count() > 0, "mission card remained stale after completion")
        require(page.locator(".chat-pending").count() == 0, "pending message remained after completion")
        require(not report["console_errors"] and not report["page_errors"], "browser emitted errors")
        page.screenshot(path=str(OUTPUT / "04-final.png"), full_page=True)
        browser.close()

    report["checks"] = {
        "single_identity": "pass",
        "collapsed_navigation": "pass",
        "first_message_visible": "pass",
        "dynamic_question_source": "pass",
        "two_five_question_blocks": "pass",
        "pending_race_removed": "pass",
        "final_summary": "pass",
        "readable_summary_labels": "pass",
        "mission_state_refresh": "pass",
    }
    (OUTPUT / "report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    return report


if __name__ == "__main__":
    print(json.dumps(run(), ensure_ascii=False, indent=2))
