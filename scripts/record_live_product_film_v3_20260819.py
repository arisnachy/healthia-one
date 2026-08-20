from __future__ import annotations

import json
import time

import record_live_product_film_20260819 as base
from cloud_browser_judge_proof import require


def submit_real_appointment_form_v3(page):
    """Submit through the real HealthIA form and prove the durable mutation.

    The production continuity UI has an intermittent post-success modal-close race
    under the headless recorder. We do not bypass the form or API. We require the
    real POST to return 2xx, then require the same appointment ID to appear in the
    authenticated bootstrap state. Only after both proofs succeed may the recorder
    use HealthIA's own close control if the dialog remains open.
    """
    values = page.locator("#appointmentForm").evaluate(
        "form => Object.fromEntries(new FormData(form).entries())"
    )
    require(bool(values.get("title")), f"appointment title missing before submit: {values}")
    require(bool(values.get("scheduled_at")), f"appointment date missing before submit: {values}")

    with page.expect_response(
        lambda r: r.request.method == "POST" and r.url.endswith("/api/appointments"),
        timeout=75_000,
    ) as pending:
        page.locator('#appointmentForm button[type="submit"]').click()

    response = pending.value
    body = response.text()
    require(
        response.ok,
        f"real appointment UI POST failed HTTP {response.status}: {body[:2000]} | form={values}",
    )
    payload = json.loads(body)
    appointment_id = str(payload.get("id") or "")
    require(appointment_id, f"real appointment response has no id: {payload}")
    require(payload.get("title") == values.get("title"), f"appointment response mismatch: {payload}")

    deadline = time.time() + 60
    durable = None
    while time.time() < deadline:
        snapshot = base.state(page)
        durable = next(
            (item for item in snapshot.get("appointments", []) if item.get("id") == appointment_id),
            None,
        )
        if durable is not None:
            break
        page.wait_for_timeout(400)
    require(durable is not None, f"appointment POST succeeded but durable state never showed {appointment_id}")

    dialog = page.locator("#appointmentDialog")
    if dialog.count() and dialog.evaluate("el => el.open"):
        close_button = dialog.locator("[data-cont-close]").first
        require(close_button.count() == 1, "appointment modal is open but HealthIA close control is missing")
        close_button.click()
    page.wait_for_function("!document.getElementById('appointmentDialog')?.open", timeout=10_000)
    page.wait_for_timeout(1200)
    return payload


base.submit_real_appointment_form = submit_real_appointment_form_v3

if __name__ == "__main__":
    base.run()
