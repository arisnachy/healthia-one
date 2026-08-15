from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from playwright.sync_api import sync_playwright

from healthia_one.models import PatientState
from healthia_one.opportunity_autopilot import WatchTopic, therapeutic_comparison
from healthia_one.research_radar import ScientificRadar, SourceFetchError, candidate_to_discovery
from record_v6_functional_demo import (
    BASE_URL,
    OUT,
    api_json,
    candidate_name,
    close_resource_view,
    compact_mission,
    create_navigation_mission,
    micro_note,
    require,
    save_report,
    seed_synthetic_clinical_context,
    select_second_candidate,
    set_english,
    show_resource_view,
    wait_server,
)


def _published_key(candidate) -> float:
    value = candidate.published_at
    if value is None:
        return 0.0
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.timestamp()


def run_scientific_radar(page) -> dict:
    """Run HealthIA's real public-source scientific radar without an LLM retrieval call.

    The product ScientificRadar normally queries PubMed, Europe PMC and
    ClinicalTrials.gov. A single upstream outage must not hide the feature in the
    judge recording, so this demo first uses the canonical aggregate scan and, if
    one source fails, retries each canonical source independently and records the
    failure instead of inventing evidence.
    """
    state = PatientState.model_validate(api_json(page, "/api/bootstrap"))
    topic = WatchTopic(
        subject_id=state.profile.id,
        subject_label=state.profile.display_name or "Patient",
        relation="self",
        condition="Hypertension",
        source="profile",
        search_terms=["Hypertension"],
    )
    radar = ScientificRadar()
    source_errors: list[str] = []
    try:
        candidates = radar.scan(topic, per_source=3)
    except SourceFetchError as exc:
        source_errors.append(f"aggregate:{type(exc).__name__}")
        candidates = []
        seen: set[str] = set()
        for source in radar.sources:
            try:
                values = source.search(topic, max_results=3)
            except Exception as source_exc:  # evidence acquisition remains fail-closed per source
                source_errors.append(f"{type(source).__name__}:{type(source_exc).__name__}")
                continue
            for candidate in values:
                key = candidate.source_id or candidate.url
                if key in seen:
                    continue
                seen.add(key)
                candidates.append(candidate)
        candidates.sort(key=_published_key, reverse=True)

    require(bool(candidates), "HealthIA scientific radar returned no real source candidates")
    tier_priority = {
        "guideline": 7,
        "systematic_review": 6,
        "randomized_trial": 5,
        "regulatory_update": 5,
        "clinical_trial": 4,
        "observational": 3,
        "case_series": 2,
        "preprint": 1,
        "unknown": 0,
    }
    candidate = max(
        candidates,
        key=lambda item: (
            tier_priority.get(str(getattr(item.evidence_tier, "value", item.evidence_tier)), 0),
            _published_key(item),
            bool(item.abstract),
        ),
    )
    discovery = candidate_to_discovery(
        topic,
        candidate,
        relevance_score=0.8,
        interrupt_score=0.45,
    )
    comparison = therapeutic_comparison(state, discovery)
    return {
        "topic": topic.model_dump(mode="json"),
        "candidate_count": len(candidates),
        "source_errors": source_errors,
        "discovery": discovery.model_dump(mode="json"),
        "comparison": comparison,
        "retrieval_model_spend": 0,
        "sources": sorted({str(item.source_name) for item in candidates}),
    }


def show_science_view(page, bundle: dict) -> None:
    page.evaluate(
        """bundle => {
          document.querySelector('#v6ScienceLive')?.remove();
          const esc = value => String(value ?? '').replace(/[&<>'\"]/g, ch => ({'&':'&amp;','<':'&lt;','>':'&gt;',"'":'&#39;','\"':'&quot;'}[ch]));
          const d=bundle.discovery||{}; const s=d.source||{}; const c=bundle.comparison||{};
          const meds=(c.current_medications||[]).map(m=>`${m.name||''} ${m.strength||''} · ${m.schedule||''}`.trim()).filter(Boolean);
          const published=s.published_at ? new Date(s.published_at).toLocaleDateString('en-US',{year:'numeric',month:'short',day:'numeric'}) : 'Date not provided';
          const summary=String(d.summary||'').slice(0,1050);
          const limitations=(d.limitations||[]).slice(0,2).map(x=>`<li>${esc(x)}</li>`).join('');
          const host=document.querySelector('.conversation-column')||document.querySelector('main')||document.body;
          const panel=document.createElement('section');
          panel.id='v6ScienceLive';
          panel.style.cssText='position:absolute;inset:62px 18px 18px 18px;z-index:8000;background:var(--background,#f6f8fb);border:1px solid var(--border,#d8dee8);border-radius:22px;padding:24px;overflow:auto;box-shadow:0 18px 50px rgba(21,38,63,.18)';
          panel.innerHTML=`
            <div style="display:flex;justify-content:space-between;gap:20px;align-items:flex-start;margin-bottom:16px">
              <div><div class="page-kicker">SCIENTIFIC RADAR · LIVE PUBLIC SOURCES</div><h1 style="margin:5px 0 7px;font-size:30px">New evidence compared with the living twin</h1><p style="margin:0;max-width:820px;color:var(--muted,#657085)">HealthIA queried its scientific source connectors now, then compared the selected evidence item with the treatment already recorded for this synthetic patient.</p></div>
              <div style="text-align:right"><span class="health-status">${esc(String(s.evidence_tier||'unknown').replaceAll('_',' '))}</span><div style="font-size:12px;color:var(--muted,#657085);margin-top:8px">${esc(bundle.candidate_count)} candidates · 0 retrieval LLM calls</div></div>
            </div>
            <div style="display:grid;grid-template-columns:1.15fr .85fr;gap:16px">
              <article class="opportunity-card" style="margin:0">
                <div class="opportunity-card-head"><span class="opportunity-kind scientific">Scientific evidence</span><span class="opportunity-source">${esc(s.publisher||'Public scientific source')}</span></div>
                <h3>${esc(d.title||'Evidence item')}</h3>
                <p style="line-height:1.55">${esc(summary)}</p>
                <div class="opportunity-meta"><span>${esc(published)}</span><span>${esc(s.source_id||'')}</span></div>
                <div class="opportunity-actions">${s.url?`<a class="opportunity-button secondary" href="${esc(s.url)}" target="_blank" rel="noopener noreferrer">Open original source ↗</a>`:''}</div>
              </article>
              <article class="opportunity-card" style="margin:0">
                <div class="opportunity-card-head"><span class="opportunity-kind saved">Living twin comparison</span></div>
                <h3>Current recorded treatment</h3>
                <p style="font-size:17px;font-weight:700">${esc(meds.join('; ')||'No active medication confirmed')}</p>
                <p><strong>Condition:</strong> ${esc(c.condition||d.condition||'')}</p>
                <p><strong>Matched medication:</strong> ${(c.matched_medication_ids||[]).length ? 'Yes — linked by condition/source claims' : 'No direct medication match established'}</p>
                <p style="color:var(--muted,#657085)">${esc(c.safety||'')}</p>
              </article>
            </div>
            <div style="margin-top:16px;background:white;border:1px solid var(--border,#d8dee8);border-radius:18px;padding:18px">
              <div class="page-kicker">EVIDENCE TIMELINE · NOT AN OUTCOME PREDICTION</div>
              <div style="display:grid;grid-template-columns:repeat(3,1fr);gap:12px;margin-top:10px">
                <div class="summary-card"><strong>1 · Current twin</strong><p>${esc(meds[0]||'Current treatment recorded')}</p></div>
                <div class="summary-card"><strong>2 · New evidence event</strong><p>${esc(String(d.title||'').slice(0,150))}</p></div>
                <div class="summary-card"><strong>3 · Safe next step</strong><p>Professional review before any treatment change; monitor only as clinically directed.</p></div>
              </div>
              <ul style="margin:14px 0 0;color:var(--muted,#657085)">${limitations}</ul>
            </div>`;
          const style=getComputedStyle(host); if(style.position==='static') host.style.position='relative'; host.appendChild(panel);
        }""",
        bundle,
    )
    page.wait_for_timeout(500)


def close_science_view(page) -> None:
    page.evaluate("document.querySelector('#v6ScienceLive')?.remove()")
    page.wait_for_timeout(250)


def run() -> dict:
    OUT.mkdir(parents=True, exist_ok=True)
    video_dir = OUT / "playwright-video"
    video_dir.mkdir(parents=True, exist_ok=True)
    report = {
        "status": "running",
        "synthetic_only": True,
        "slides_used": False,
        "browser_application_only": True,
        "real_google_places": False,
        "real_scientific_sources": False,
        "checks": [],
    }
    save_report(report)

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True, args=["--no-sandbox"])
        context = browser.new_context(
            locale="en-US",
            viewport={"width": 1600, "height": 900},
            record_video_dir=str(video_dir),
            record_video_size={"width": 1600, "height": 900},
        )
        page = context.new_page()
        wait_server(page)

        page.goto(f"{BASE_URL}/login", wait_until="networkidle", timeout=60000)
        set_english(page)
        micro_note(page, "Real application — not slides", "The demo stays inside the working HealthIA browser product from sign-in through every mission.", 2.5)
        suffix = uuid4().hex[:8]
        if page.locator("#registerTab").count():
            page.locator("#registerTab").click()
            page.locator('#registerForm input[name="display_name"]').fill("Alex Rivera")
            page.locator('#registerForm input[name="email"]').fill(f"v6-demo-{suffix}@example.test")
            page.locator('#registerForm input[name="password"]').fill(f"HealthIA!{suffix}9Aa")
            page.locator('#registerForm button[type="submit"]').click()
            page.wait_for_url(f"{BASE_URL}/", timeout=30000)
        else:
            page.goto(f"{BASE_URL}/", wait_until="networkidle", timeout=30000)
        page.wait_for_load_state("networkidle")
        set_english(page)
        report["checks"].append("real_login_and_browser_application")
        save_report(report)

        seed_synthetic_clinical_context(page)
        page.reload(wait_until="networkidle")
        set_english(page)
        treatment_nav = page.locator('[data-open="treatment"]')
        if treatment_nav.count():
            treatment_nav.last.click()
            page.wait_for_timeout(650)
        micro_note(page, "Living clinical context", "The synthetic patient has hypertension, a professional-confirmed Losartan plan, and an authorized family autism condition in the living record.", 2.8)
        report["checks"].append("living_twin_context_visible")
        save_report(report)

        chat_nav = page.locator('[data-open="chat"]')
        if chat_nav.count():
            chat_nav.last.click()
        page.locator("#chatInput").fill("My child has autism. Find nearby therapy, support groups, foundations, and government or financial assistance in Santiago.")
        page.wait_for_timeout(900)
        micro_note(page, "Patient asks naturally", "This need becomes a bounded resource-navigation workflow around the family condition.", 2.0)
        page.locator("#chatInput").fill("")

        support_mission = create_navigation_mission(
            page,
            condition_or_need="autism support resources community foundations government benefits financial assistance",
            provider_query="autism support resources",
            title="Autism support resources for my family",
            radius_m=18000,
        )
        report["support_mission"] = compact_mission(support_mission)
        report["real_google_places"] = True
        show_resource_view(
            page,
            support_mission,
            title="Autism support near the family",
            subtitle="HealthIA searched real-world care, community, foundation, and government/financial-support resource categories from the same patient mission.",
        )
        support_cards = len(((support_mission.get("tool_outputs") or {}).get("place_candidates") or []))
        micro_note(page, "Nearby + Google Maps", f"The live mission returned {support_cards} Google Places candidates with address, phone, Maps, and website links when available.", 3.8)
        report["checks"].append(f"real_google_places_support_candidates_{support_cards}")
        save_report(report)

        if support_cards >= 2:
            page.evaluate("document.querySelector('#v6ResourceLive .wave4-resource-card:nth-child(2)')?.scrollIntoView({block:'center'})")
            micro_note(page, "“The second one”", "HealthIA keeps the exact second verified result in the durable mission.", 1.8)
            selected_support = select_second_candidate(page, support_mission)
            report["selected_support_place"] = {
                "id": (selected_support.get("selected_place") or {}).get("id"),
                "name": candidate_name(selected_support.get("selected_place") or {}),
            }
            show_resource_view(page, selected_support, title="Exact resource selected", subtitle="The second candidate is now the durable selected place. No substitute result was invented.")
            page.evaluate("document.querySelector('#v6ResourceLive .wave4-resource-card.is-selected')?.scrollIntoView({block:'center'})")
            micro_note(page, "Exact durable selection", "The selected card is highlighted directly from the real mission state.", 2.5)
            report["checks"].append("exact_second_candidate_selected_via_product_api")
            save_report(report)
        close_resource_view(page)

        if chat_nav.count():
            chat_nav.last.click()
        page.locator("#chatInput").fill("What new scientific evidence is there about my hypertension, and how does it compare with my current treatment?")
        page.wait_for_timeout(850)
        micro_note(page, "Scientific radar", "HealthIA now queries its real PubMed, Europe PMC, and ClinicalTrials.gov connectors — no PowerPoint claim and no LLM retrieval call.", 2.6)
        page.locator("#chatInput").fill("")
        science_bundle = run_scientific_radar(page)
        report["scientific_radar"] = science_bundle
        report["real_scientific_sources"] = True
        show_science_view(page, science_bundle)
        micro_note(page, "Evidence compared with the twin", "The source is compared with the professional-confirmed Losartan plan. The timeline shows evidence and review steps, not a fabricated patient-outcome forecast.", 4.2)
        report["checks"].append("real_scientific_sources_retrieved")
        report["checks"].append("evidence_compared_with_recorded_losartan")
        save_report(report)
        close_science_view(page)

        if chat_nav.count():
            chat_nav.last.click()
        page.locator("#chatInput").fill("I still need a creatinine lab before my appointment. Where can I do it nearby?")
        page.wait_for_timeout(800)
        micro_note(page, "A missing study becomes a mission", "Instead of only reminding the patient, HealthIA searches where the needed test can actually be completed.", 2.4)
        page.locator("#chatInput").fill("")
        lab_mission = create_navigation_mission(
            page,
            condition_or_need="creatinine laboratory test needed before follow-up appointment",
            provider_query="laboratory creatinine clinic",
            title="Find a laboratory for creatinine testing",
            radius_m=15000,
        )
        report["lab_mission"] = compact_mission(lab_mission)
        show_resource_view(page, lab_mission, title="Where can I complete the missing lab?", subtitle="HealthIA converted a care gap into a real nearby-resource mission and searched Google Places for laboratories or clinics around the patient.")
        lab_cards = len(((lab_mission.get("tool_outputs") or {}).get("place_candidates") or []))
        micro_note(page, "Real nearby options", f"The live mission returned {lab_cards} verified place candidate(s) with Google Maps navigation when available.", 3.5)
        report["checks"].append(f"missing_lab_real_nearby_candidates_{lab_cards}")
        save_report(report)
        close_resource_view(page)

        timeline_nav = page.locator('[data-open="timeline"]')
        if timeline_nav.count():
            timeline_nav.last.click()
            page.wait_for_timeout(700)
        micro_note(page, "Your health never starts over", "Living twin, real scientific evidence, family support, and real-world care navigation — demonstrated as working product behavior.", 3.5)

        report["status"] = "PASS"
        report["completed_at"] = datetime.now(timezone.utc).isoformat()
        video = page.video
        context.close()
        raw_path = Path(video.path())
        target = OUT / "healthia-v6-functional-live.webm"
        raw_path.replace(target)
        report["raw_video"] = str(target)
        save_report(report)
        browser.close()

    print("HEALTHIA_V6_FUNCTIONAL_DEMO_PASS")
    return report


if __name__ == "__main__":
    run()
