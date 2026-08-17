from __future__ import annotations

from healthia_one.google_constellation import (
    ACTION_POLICIES,
    GoogleActionReceipt,
    GoogleActionRequest,
    build_google_receipt,
    build_idempotency_key,
)
from healthia_one.google_connector_runtime import ConnectorResult, GoogleActionExecutor
from healthia_one.google_constellation_store import (
    GoogleActionAuthorization,
    GoogleAuthorizationStore,
    GoogleGrantStore,
    GoogleReceiptStore,
    build_action_intent_key,
)
from healthia_one.observability import span
from healthia_one.safety_kernel import HealthIASafetyKernel, MemoryHealthActionTicketStore


def _trace_id_hex(current_span) -> str:
    try:
        context = current_span.get_span_context()
        if not getattr(context, "is_valid", False):
            return ""
        return f"{int(context.trace_id):032x}"
    except Exception:
        return ""


def _set_span_attribute(current_span, key: str, value: object) -> None:
    try:
        if current_span is not None and value is not None and isinstance(value, (str, bool, int, float)):
            current_span.set_attribute(f"healthia.{key}", value)
    except Exception:
        pass


class GuardedGoogleActionExecutor:
    """Durable authorization + one-time execution boundary around connectors.

    Patient authorization is bound to patient + mission + action + exact
    material payload. Immediately before a connector call, ONE SAFETY issues
    and atomically consumes a short-lived HealthActionTicket bound to the same
    intent and idempotency key. A ticket is authority to *attempt* one call;
    only the durable connector receipt proves the external action completed.
    """

    def __init__(
        self,
        *,
        executor: GoogleActionExecutor,
        grant_store: GoogleGrantStore,
        authorization_store: GoogleAuthorizationStore,
        receipt_store: GoogleReceiptStore,
        safety_kernel: HealthIASafetyKernel | None = None,
    ) -> None:
        self.executor = executor
        self.grant_store = grant_store
        self.authorization_store = authorization_store
        self.receipt_store = receipt_store
        self.safety_kernel = safety_kernel or HealthIASafetyKernel(MemoryHealthActionTicketStore())
        self.executor.receipt_store = receipt_store

    def _authorization_id(self, request: GoogleActionRequest) -> str:
        return (request.explicit_authorization_id or request.standing_authorization_id).strip()

    def _validated_authorization(self, request: GoogleActionRequest) -> GoogleActionAuthorization | None:
        authorization_id = self._authorization_id(request)
        if not authorization_id:
            return None
        authorization = self.authorization_store.get(request.patient_id, authorization_id)
        if authorization is None:
            return None
        if not authorization.usable_for(
            patient_id=request.patient_id,
            mission_id=request.mission_id,
            action=request.action,
            intent_key=build_action_intent_key(request),
        ):
            return None
        return authorization

    def execute(self, request: GoogleActionRequest) -> tuple[GoogleActionReceipt, ConnectorResult | None]:
        # Trace attributes are deliberately limited to non-PHI operational facts.
        with span(
            "google.action.guarded_execute",
            action=request.action.value,
            service=request.service.value,
            external_mutation=ACTION_POLICIES[request.action].mutates_external_state,
        ) as current_span:
            return self._execute_guarded(request, current_span=current_span)

    def _execute_guarded(
        self,
        request: GoogleActionRequest,
        *,
        current_span=None,
    ) -> tuple[GoogleActionReceipt, ConnectorResult | None]:
        key = build_idempotency_key(request)
        completed = self.receipt_store.get(request.patient_id, key)
        if completed is not None and completed.status == "completed":
            _set_span_attribute(current_span, "receipt_id", completed.id)
            _set_span_attribute(current_span, "outcome_status", completed.status)
            _set_span_attribute(current_span, "idempotent_replay", True)
            return completed, ConnectorResult(
                resource_id=completed.resource_id,
                safe_summary=completed.safe_summary,
                recovered_existing=True,
            )

        authorization_id = self._authorization_id(request)
        if authorization_id:
            authorization = self._validated_authorization(request)
            if authorization is None:
                receipt = build_google_receipt(
                    request,
                    status="blocked",
                    safe_summary=(
                        "Presented Google action authorization is missing, expired, consumed, scoped elsewhere, "
                        "or does not match the exact action payload the patient authorized."
                    ),
                )
                self.receipt_store.save(receipt)
                _set_span_attribute(current_span, "receipt_id", receipt.id)
                _set_span_attribute(current_span, "outcome_status", receipt.status)
                return receipt, None

        trace_id = _trace_id_hex(current_span)
        try:
            ticket = self.safety_kernel.issue(
                request,
                authorization_id=authorization_id,
                idempotency_key=key,
                trace_id=trace_id,
            )
            _set_span_attribute(current_span, "ticket_id", ticket.id)
            _set_span_attribute(current_span, "trace_correlated", bool(ticket.trace_id))
            self.safety_kernel.consume(ticket, request, idempotency_key=key)
        except (KeyError, PermissionError, ValueError) as exc:
            receipt = build_google_receipt(
                request,
                status="blocked",
                safe_summary=f"ONE SAFETY blocked connector execution: {exc}",
            )
            self.receipt_store.save(receipt)
            _set_span_attribute(current_span, "receipt_id", receipt.id)
            _set_span_attribute(current_span, "outcome_status", receipt.status)
            return receipt, None

        grants = self.grant_store.list_for_patient(request.patient_id)
        receipt, outcome = self.executor.execute(request, grants)
        self.safety_kernel.record_outcome(ticket, receipt_id=receipt.id, status=receipt.status)
        _set_span_attribute(current_span, "receipt_id", receipt.id)
        _set_span_attribute(current_span, "outcome_status", receipt.status)

        if receipt.status == "completed" and authorization_id:
            authorization = self.authorization_store.get(request.patient_id, authorization_id)
            if authorization is not None and authorization.one_time and authorization.consumed_at is None:
                self.authorization_store.consume(request.patient_id, authorization_id)

        return receipt, outcome


class GuardedMissionExecutorAdapter:
    """Mission-coordinator adapter that makes durable policy non-bypassable."""

    def __init__(self, guard: GuardedGoogleActionExecutor) -> None:
        self.guard = guard

    def execute(self, request: GoogleActionRequest, _untrusted_grants=None):
        return self.guard.execute(request)
