from __future__ import annotations

import asyncio
import json
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse, RedirectResponse
from pydantic import BaseModel, Field

from healthia_one.agent_fleet_manifest import agent_fleet_manifest
from healthia_one.auth import AccountManager, AuthError, bind_principal, current_principal, reset_principal
from healthia_one.config import Settings
from healthia_one.google_constellation_api import build_google_constellation_router
from healthia_one.google_constellation_singleton import get_google_constellation_service
from healthia_one.google_oauth_web import build_google_oauth_browser_flow, build_google_oauth_router
from healthia_one.language import bind_requested_locale, current_requested_locale, reset_requested_locale
from healthia_one.model_armor import ModelArmorGate
from healthia_one.observability import configure_observability, observability_status, span
from healthia_one.opportunity_api import build_opportunity_router
from healthia_one.service import HealthIAService


class LoginRequest(BaseModel):
    email: str = Field(min_length=3, max_length=254)
    password: str = Field(min_length=1, max_length=256)


class RegisterRequest(LoginRequest):
    display_name: str = Field(min_length=2, max_length=120)


def _header_locale(request: Request) -> str | None:
    value = request.headers.get("accept-language", "").strip()
    if not value:
        return None
    return value.split(",", 1)[0].split(";", 1)[0].strip()


def _detail(es: str, en: str) -> str:
    return es if current_requested_locale() == "es" else en


def install_patient_auth(
    app: FastAPI,
    *,
    service: HealthIAService,
    settings: Settings,
    web_root: Path,
) -> AccountManager:
    manager = AccountManager(settings)
    prompt_gate = ModelArmorGate(
        enabled=settings.model_armor_enabled,
        project_id=settings.google_cloud_project,
        location=settings.model_armor_location,
        template_id=settings.model_armor_template_id,
        fail_closed=settings.model_armor_fail_closed,
    )
    configure_observability(settings)
    app.state.account_manager = manager
    app.state.healthia_service = service
    app.state.model_armor_gate = prompt_gate
    app.state.last_prompt_security_decision = None

    public_exact = {
        "/healthz",
        "/api/readiness",
        "/login",
        "/api/auth/session",
        "/api/auth/login",
        "/api/auth/register",
        "/api/auth/logout",
        "/api/devices/pairing/claim",
        "/api/devices/health-connect/sync",
    }

    @app.middleware("http")
    async def patient_session_boundary(request: Request, call_next):
        token = request.cookies.get(settings.session_cookie_name)
        principal = manager.verify_session(token)
        context_token = bind_principal(principal)
        locale_token = bind_requested_locale(_header_locale(request))
        try:
            path = request.url.path
            # FCM device routes are session-public only because the Android bridge
            # authenticates with its separately signed pairing bearer. The router
            # itself rejects missing/revoked/mismatched device credentials.
            evaluation_public = settings.evaluation_enabled and (
                path == "/living" or path.startswith("/api/evaluation/")
            )
            public = (
                path.startswith("/assets/")
                or path.startswith("/api/devices/fcm/")
                or path in public_exact
                or evaluation_public
            )
            if settings.auth_required and principal is None and not public:
                if path in {"/", "/security"}:
                    return RedirectResponse("/login", status_code=303)
                if path.startswith("/api/"):
                    return JSONResponse(
                        status_code=401,
                        content={
                            "detail": _detail(
                                "Inicia sesión para acceder a los datos del paciente.",
                                "Sign in to access patient data.",
                            )
                        },
                    )

            # Screen only the newest untrusted chat text, not conversation
            # history, system instructions or patient clinical context. The body
            # is restored for FastAPI after inspection.
            if path == "/api/chat" and request.method.upper() == "POST":
                raw_body = await request.body()

                async def replay_body():
                    return {"type": "http.request", "body": raw_body, "more_body": False}

                request._receive = replay_body  # Starlette request replay after security inspection.
                try:
                    parsed = json.loads(raw_body or b"{}")
                    patient_text = str(parsed.get("message", "")) if isinstance(parsed, dict) else ""
                except (TypeError, ValueError, UnicodeDecodeError):
                    patient_text = ""
                if patient_text:
                    decision = await asyncio.to_thread(prompt_gate.screen, patient_text)
                    app.state.last_prompt_security_decision = {
                        "allowed": decision.allowed,
                        "source": decision.source,
                        "reason": decision.reason,
                        "google_checked": decision.google_checked,
                    }
                    if not decision.allowed:
                        return JSONResponse(
                            status_code=400,
                            content={
                                "detail": _detail(
                                    "ONE SAFETY bloqueó el texto antes de enviarlo al modelo porque parece intentar alterar instrucciones, permisos o secretos del sistema.",
                                    "ONE SAFETY blocked the text before model execution because it appears to manipulate system instructions, permissions, or secrets.",
                                ),
                                "security_boundary": "prompt_ingress",
                                "model_called": False,
                            },
                        )

            with span("http.request", method=request.method, path=path):
                response = await call_next(request)
            return response
        finally:
            reset_requested_locale(locale_token)
            reset_principal(context_token)

    @app.get("/login", include_in_schema=False)
    async def login_page(request: Request):
        if current_principal() is not None:
            return RedirectResponse("/", status_code=303)
        return FileResponse(web_root / "login.html")

    @app.get("/api/auth/session")
    async def auth_session() -> dict:
        return manager.public_session(current_principal())

    @app.post("/api/auth/register")
    async def register(payload: RegisterRequest):
        try:
            principal = manager.register(payload.email, payload.password, payload.display_name)
            await service.ensure_patient(principal)
        except AuthError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        response = JSONResponse(manager.public_session(principal), status_code=201)
        response.set_cookie(
            settings.session_cookie_name,
            manager.issue_session(principal),
            max_age=settings.session_hours * 3600,
            httponly=True,
            secure=settings.env != "local",
            samesite="lax",
            path="/",
        )
        return response

    @app.post("/api/auth/login")
    async def login(payload: LoginRequest):
        try:
            principal = manager.authenticate(payload.email, payload.password)
            await service.ensure_patient(principal)
        except AuthError as exc:
            raise HTTPException(status_code=401, detail=str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        response = JSONResponse(manager.public_session(principal))
        response.set_cookie(
            settings.session_cookie_name,
            manager.issue_session(principal),
            max_age=settings.session_hours * 3600,
            httponly=True,
            secure=settings.env != "local",
            samesite="lax",
            path="/",
        )
        return response

    @app.post("/api/auth/logout")
    async def logout():
        response = JSONResponse({"authenticated": False, "logged_out": True})
        response.delete_cookie(settings.session_cookie_name, path="/")
        return response

    # FCM routes are mounted once by app.main so they share the production
    # pairing verifier and registration store with device revocation cleanup.
    # This module only keeps the browser-session middleware exception above.

    # Opportunity and Google Constellation data are mounted after the same
    # patient-session middleware. Neither prefix is public, so Cloud mode always
    # requires an authenticated patient before any mission/grant/receipt read.
    app.include_router(build_opportunity_router(service))
    constellation = get_google_constellation_service(settings)
    app.state.google_constellation = constellation
    app.include_router(build_google_constellation_router(constellation))

    @app.get("/security", include_in_schema=False)
    async def security_console() -> FileResponse:
        return FileResponse(web_root / "operations" / "security.html")

    @app.get("/api/operations/security")
    async def operational_security() -> dict:
        state = await service.snapshot()
        tickets = constellation.runtime.action_ticket_store.recent(state.profile.id, limit=20)
        last_prompt = app.state.last_prompt_security_decision
        return {
            "system": "ONE SAFETY",
            "release_sha": settings.release_sha,
            "safety_kernel": {
                "enabled": True,
                "execution_ticket": "HealthActionTicket",
                "ticket_semantics": "short_lived_one_time_exact_intent",
                "receipt_required_for_completion": True,
            },
            "prompt_ingress": {
                "local_policy": "enabled",
                "google_model_armor": {
                    "enabled": prompt_gate.enabled,
                    "configured": prompt_gate.configured,
                    "location": prompt_gate.location,
                    "fail_closed": prompt_gate.fail_closed,
                },
                "last_decision": last_prompt,
            },
            "observability": observability_status(),
            "agent_fleet": agent_fleet_manifest(),
            "execution_chain": [
                "patient_or_event_intent",
                "deterministic_policy",
                "patient_authorization_when_required",
                "one_safety_kernel",
                "health_action_ticket",
                "real_connector",
                "durable_receipt",
            ],
            "recent_action_tickets": [
                {
                    "id": ticket.id,
                    "mission_id": ticket.mission_id,
                    "action": ticket.action.value,
                    "status": ticket.status,
                    "outcome_status": ticket.outcome_status,
                    "trace_id": ticket.trace_id,
                    "receipt_id": ticket.receipt_id,
                    "receipt_linked": bool(ticket.receipt_id),
                    "trace_correlated": bool(ticket.trace_id),
                    "correlation_complete": bool(ticket.trace_id and ticket.receipt_id),
                    "issued_at": ticket.issued_at.isoformat(),
                    "expires_at": ticket.expires_at.isoformat(),
                }
                for ticket in tickets
            ],
        }

    # OAuth readiness is safe to mount even when credentials have not been
    # provisioned: the flow reports configuration presence and /connect fails
    # closed. Connect/callback/disconnect remain behind the same patient session
    # boundary above; no OAuth route is added to public_exact.
    google_oauth_flow = build_google_oauth_browser_flow(
        settings,
        constellation.runtime.oauth_connection_store,
    )
    app.state.google_oauth_flow = google_oauth_flow
    app.include_router(build_google_oauth_router(google_oauth_flow, settings))

    return manager
