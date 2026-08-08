from __future__ import annotations

from threading import Lock
from typing import Any


class CostGuardBlocked(RuntimeError):
    """Raised before a billable AI request when the local hard guard blocks it."""


class CostGuard:
    """Process-local request ceiling for explicitly enabled Google AI calls.

    This guard is deliberately independent from Cloud Billing budgets. It does not
    estimate dollars; it prevents this process from issuing more than a configured
    number of model requests and can be switched off immediately.
    """

    VALID_MODES = {"local", "guarded", "cloud_demo"}

    def __init__(
        self,
        *,
        mode: str = "local",
        request_limit: int = 0,
        start_enabled: bool = False,
        max_output_tokens: int = 700,
    ) -> None:
        normalized = str(mode or "local").strip().lower()
        if normalized not in self.VALID_MODES:
            raise ValueError(f"Unsupported cost mode: {mode}")
        self.mode = normalized
        self.request_limit = max(0, int(request_limit))
        self.max_output_tokens = max(64, min(int(max_output_tokens), 4096))
        self._enabled = bool(start_enabled and self.can_enable)
        self._used = 0
        self._blocked = 0
        self._last_purpose = ""
        self._lock = Lock()

    @property
    def can_enable(self) -> bool:
        return self.mode in {"guarded", "cloud_demo"} and self.request_limit > 0

    @property
    def mutable(self) -> bool:
        return self.mode == "guarded"

    @property
    def enabled(self) -> bool:
        with self._lock:
            return self._enabled

    def set_enabled(self, enabled: bool) -> dict[str, Any]:
        with self._lock:
            desired = bool(enabled)
            if not self.mutable:
                if desired != self._enabled:
                    raise CostGuardBlocked("El modo actual no permite cambiar el interruptor desde la interfaz.")
                return self._snapshot_unlocked()
            if desired and not self.can_enable:
                raise CostGuardBlocked("No existe un límite de solicitudes válido para activar Google AI.")
            self._enabled = desired
            return self._snapshot_unlocked()

    def authorize_many(self, purpose: str, count: int) -> tuple[int, int]:
        """Atomically reserve a worst-case number of model calls before execution.

        Reserving the complete upper bound prevents an agent/tool loop from
        starting when only part of its model-call budget remains. The reservation
        is intentionally conservative: unused reserved calls are not returned,
        which favors the user's hard spend ceiling over utilization.
        """
        requested = max(1, int(count))
        with self._lock:
            if not self._enabled:
                self._blocked += requested
                raise CostGuardBlocked("Google AI está apagado por el control de costos.")
            if self._used + requested > self.request_limit:
                self._enabled = False
                self._blocked += requested
                raise CostGuardBlocked("No queda presupuesto suficiente para reservar todas las llamadas de esta operación.")
            first = self._used + 1
            self._used += requested
            self._last_purpose = str(purpose or "model_request")[:120]
            if self._used >= self.request_limit:
                self._enabled = False
            return first, self._used

    def authorize(self, purpose: str) -> int:
        """Reserve one request before contacting a billable model endpoint."""
        _, last = self.authorize_many(purpose, 1)
        return last

    def _snapshot_unlocked(self) -> dict[str, Any]:
        remaining = max(0, self.request_limit - self._used)
        return {
            "mode": self.mode,
            "enabled": self._enabled,
            "can_enable": self.can_enable,
            "mutable": self.mutable,
            "request_limit": self.request_limit,
            "requests_used": self._used,
            "requests_remaining": remaining,
            "blocked_requests": self._blocked,
            "max_output_tokens": self.max_output_tokens,
            "last_purpose": self._last_purpose,
            "hard_limit_kind": "model_requests_per_process",
            "estimated_spend_usd": None,
            "truth_boundary": (
                "Este límite controla solicitudes de este proceso; no sustituye presupuestos, spend caps, cuotas ni la consola de facturación."
            ),
        }

    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            return self._snapshot_unlocked()
