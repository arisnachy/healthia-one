from __future__ import annotations

import json
import time

import record_live_product_film_v3_20260819 as v3
from cloud_browser_judge_proof import require

base = v3.base


def upload_document_v4(page, path, *, title: str, category: str) -> dict:
    """Upload through HealthIA's real Documents UI and prove the persisted record.

    A headless browser can observe the HTTP 2xx before the UI finishes its
    asynchronous refresh/close sequence. This helper does not bypass the product:
    it clicks the real form submit button, requires the real endpoint to succeed,
    requires the returned document ID to appear in the authenticated durable
    bootstrap state, then uses HealthIA's own close control only if the dialog is
    still open after that proof.
    """
    base.goto(page, "documents", 1.2)
    page.locator("#addDocumentButton").click()
    page.locator('#documentForm input[name="file"]').set_input_files(str(path))
    page.locator('#documentForm input[name="title"]').fill(title)
    page.locator('#documentForm select[name="category"]').select_option(category)

    with page.expect_response(
        lambda r: r.request.method == "POST" and "/api/documents/upload" in r.url,
        timeout=75_000,
    ) as pending:
        page.locator('#documentForm button[type="submit"]').click()

    response = pending.value
    body = response.text()
    require(
        response.ok,
        f"real Documents UI upload failed HTTP {response.status}: {body[:2000]}",
    )
    payload = json.loads(body)
    document_id = str(payload.get("id") or "")
    require(document_id, f"document upload returned no durable id: {payload}")
    require(payload.get("title") == title, f"document title mismatch: {payload}")
    require(payload.get("category") == category, f"document category mismatch: {payload}")

    deadline = time.time() + 60
    durable = None
    while time.time() < deadline:
        snapshot = base.state(page)
        durable = next(
            (item for item in snapshot.get("documents", []) if item.get("id") == document_id),
            None,
        )
        if durable is not None:
            break
        page.wait_for_timeout(400)
    require(durable is not None, f"document POST succeeded but durable record never showed {document_id}")

    dialog = page.locator("#documentDialog")
    if dialog.count() and dialog.evaluate("el => el.open"):
        close_button = dialog.locator('[data-close="documentDialog"]').first
        require(close_button.count() == 1, "document modal open but HealthIA close control missing")
        close_button.click()
    page.wait_for_function("!document.getElementById('documentDialog')?.open", timeout=10_000)

    # Require the real Documents view itself to render the persisted document.
    base.goto(page, "documents", 1.0)
    page.wait_for_function(
        "([docId, docTitle]) => { const root=document.getElementById('documentsRoot'); return !!root && root.textContent.includes(docTitle); }",
        arg=[document_id, title],
        timeout=30_000,
    )
    page.wait_for_timeout(1800)
    return payload


base.upload_document = upload_document_v4

if __name__ == "__main__":
    base.run()
