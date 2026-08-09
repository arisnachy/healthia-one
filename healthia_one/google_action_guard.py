from __future__ import annotations

from healthia_one.google_constellation import (
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
)


class GuardedGoogleActionExecutor:
    """Durable authorization boundary around the raw connector executor.

    The raw executor knows whether an action category requires authorization.
    This guard proves that the presented authorization ID exists, belongs to the
    same patient/mission/action, is not expired and, for one-time grants, is not
    already consumed. Replays of an already completed idempotency key return the
    durable receipt before checking a consumed one-time authorization.
    """

    def __init__(
        self,
        *,
        executor: GoogleActionExecutor,
        grant_store: GoogleGrantStore,
        authorization_store: GoogleAuthorizationStore,
        receipt_store: GoogleReceiptStore,
    ) -> None:
        self.executor = executor
        self.grant_store = grant_store
        self.authorization_store = authorization_store
        self.receipt_store = receipt_store
        # Keep the raw executor and guard on one durable receipt source.
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
        ):
            return None
        return authorization

    def execute(self, request: GoogleActionRequest) -> tuple[GoogleActionReceipt, ConnectorResult | None]:
        key = build_idempotency_key(request)
        completed = self.receipt_store.get(request.patient_id, key)
        if completed is not None and completed.status == "completed":
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
                    safe_summary="Presented Google action authorization is missing, expired, consumed, or scoped to another patient/mission/action.",
                )
                self.receipt_store.save(receipt)
                return receipt, None

        grants = self.grant_store.list_for_patient(request.patient_id)
        receipt, outcome = self.executor.execute(request, grants)

        if receipt.status == "completed" and authorization_id:
            authorization = self.authorization_store.get(request.patient_id, authorization_id)
            if authorization is not None and authorization.one_time and authorization.consumed_at is None:
                self.authorization_store.consume(request.patient_id, authorization_id)

        return receipt, outcome
