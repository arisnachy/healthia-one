from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse, RedirectResponse
from pydantic import BaseModel, Field

from healthia_one.auth import AccountManager, AuthError, bind_principal, current_principal, reset_principal
from healthia_one.config import Settings
from healthia_one.google_constellation_api import build_google_constellation_router
from healthia_one.google_constellation_runtime import build_google_constellation_service
from healthia_one.language import bind_requested_locale, current_requested_locale, reset_requested_locale
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
    app.state.account_manager = manager

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
            public = path.startswith("/assets/") or path in public_exact
            if settings.auth_required and principal is None and not public:
                if path == "/":
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

    # Opportunity and Google Constellation data are mounted after the same
    # patient-session middleware. Neither prefix is public, so Cloud mode always
    # requires an authenticated patient before any mission/grant/receipt read.
    app.include_router(build_opportunity_router(service))
    constellation = build_google_constellation_service(settings)
    app.state.google_constellation = constellation
    app.include_router(build_google_constellation_router(constellation))

    return manager
