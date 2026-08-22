from __future__ import annotations

from pathlib import Path


PATCHES: dict[str, list[tuple[str, str]]] = {
    "healthia_one/autopilot_claims.py": [
        (
            'class FirestoreEventClaimStore:\n    COLLECTION = "healthia_autopilot_claims"\n\n    def __init__(self, project: str | None = None) -> None:\n        from google.cloud import firestore\n\n        self.firestore = firestore\n        self.client = firestore.Client(project=project)\n',
            'class FirestoreEventClaimStore(LazyFirestoreClient):\n    COLLECTION = "healthia_autopilot_claims"\n\n    def __init__(self, project: str | None = None) -> None:\n        self._configure_firestore(project)\n',
        ),
    ],
    "healthia_one/autopilot_events.py": [
        (
            'class FirestoreEventOutboxStore:\n    """Top-level collection intentionally shaped for a direct Eventarc trigger."""\n\n    COLLECTION = "healthia_autopilot_events"\n\n    def __init__(self, project: str | None = None) -> None:\n        from google.cloud import firestore\n\n        self.client = firestore.Client(project=project)\n',
            'class FirestoreEventOutboxStore(LazyFirestoreClient):\n    """Top-level collection intentionally shaped for a direct Eventarc trigger."""\n\n    COLLECTION = "healthia_autopilot_events"\n\n    def __init__(self, project: str | None = None) -> None:\n        self._configure_firestore(project)\n',
        ),
    ],
    "healthia_one/autopilot_receipts.py": [
        (
            'class FirestoreAutopilotReceiptStore:\n    COLLECTION = "healthia_autopilot_receipts"\n\n    def __init__(self, project: str | None = None) -> None:\n        from google.cloud import firestore\n\n        self.client = firestore.Client(project=project)\n',
            'class FirestoreAutopilotReceiptStore(LazyFirestoreClient):\n    COLLECTION = "healthia_autopilot_receipts"\n\n    def __init__(self, project: str | None = None) -> None:\n        self._configure_firestore(project)\n',
        ),
    ],
    "healthia_one/gmail_mission_events.py": [
        (
            'class FirestoreGmailWatchStore:\n    COLLECTION = "healthia_gmail_watch_state"\n\n    def __init__(self, project: str | None = None) -> None:\n        from google.cloud import firestore\n        self.client = firestore.Client(project=project)\n',
            'class FirestoreGmailWatchStore(LazyFirestoreClient):\n    COLLECTION = "healthia_gmail_watch_state"\n\n    def __init__(self, project: str | None = None) -> None:\n        self._configure_firestore(project)\n',
        ),
        (
            'class FirestoreMissionResolver:\n    COLLECTION = "healthia_google_missions"\n\n    def __init__(self, project: str | None = None) -> None:\n        from google.cloud import firestore\n        self.client = firestore.Client(project=project)\n',
            'class FirestoreMissionResolver(LazyFirestoreClient):\n    COLLECTION = "healthia_google_missions"\n\n    def __init__(self, project: str | None = None) -> None:\n        self._configure_firestore(project)\n',
        ),
    ],
    "healthia_one/guardian_email_reply.py": [
        (
            'class FirestoreGuardianEmailThreadStore:\n    COLLECTION = "healthia_guardian_email_threads"\n\n    def __init__(self, project: str | None = None) -> None:\n        from google.cloud import firestore\n        self.client = firestore.Client(project=project)\n',
            'class FirestoreGuardianEmailThreadStore(LazyFirestoreClient):\n    COLLECTION = "healthia_guardian_email_threads"\n\n    def __init__(self, project: str | None = None) -> None:\n        self._configure_firestore(project)\n',
        ),
    ],
    "healthia_one/opportunity_permissions.py": [
        (
            'class FirestoreRadarPermissionStore:\n    COLLECTION = "healthia_opportunity_permissions"\n\n    def __init__(self, project: str | None = None) -> None:\n        from google.cloud import firestore\n\n        self.client = firestore.Client(project=project)\n',
            'class FirestoreRadarPermissionStore(LazyFirestoreClient):\n    COLLECTION = "healthia_opportunity_permissions"\n\n    def __init__(self, project: str | None = None) -> None:\n        self._configure_firestore(project)\n',
        ),
    ],
    "healthia_one/opportunity_store.py": [
        (
            'class FirestoreOpportunityStore:\n    COLLECTION = "healthia_opportunity_vaults"\n\n    def __init__(self, project: str | None = None) -> None:\n        from google.cloud import firestore\n\n        self.client = firestore.Client(project=project)\n',
            'class FirestoreOpportunityStore(LazyFirestoreClient):\n    COLLECTION = "healthia_opportunity_vaults"\n\n    def __init__(self, project: str | None = None) -> None:\n        self._configure_firestore(project)\n',
        ),
    ],
    "healthia_one/program_source_verifier.py": [
        (
            'class FirestoreProgramVerificationStore:\n    COLLECTION = "healthia_program_verifications"\n\n    def __init__(self, project: str | None = None) -> None:\n        from google.cloud import firestore\n        self.client = firestore.Client(project=project)\n',
            'class FirestoreProgramVerificationStore(LazyFirestoreClient):\n    COLLECTION = "healthia_program_verifications"\n\n    def __init__(self, project: str | None = None) -> None:\n        self._configure_firestore(project)\n',
        ),
    ],
}


for filename, replacements in PATCHES.items():
    path = Path(filename)
    text = path.read_text("utf-8")
    if "from healthia_one.lazy_google_clients import LazyFirestoreClient" not in text:
        anchor = "\nfrom healthia_one."
        if anchor not in text:
            raise SystemExit(f"{filename}: healthia_one import anchor missing")
        text = text.replace(
            anchor,
            "\nfrom healthia_one.lazy_google_clients import LazyFirestoreClient\nfrom healthia_one.",
            1,
        )
    for old, new in replacements:
        count = text.count(old)
        if count != 1:
            raise SystemExit(f"{filename}: expected exact constructor anchor once, got {count}")
        text = text.replace(old, new, 1)
    path.write_text(text, "utf-8")

print("HEALTHIA_REMAINING_LAZY_FIRESTORE_PATCH_PASS")
