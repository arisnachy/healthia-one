from __future__ import annotations

from pathlib import Path


def replace_once(text: str, old: str, new: str, label: str) -> str:
    count = text.count(old)
    if count != 1:
        raise SystemExit(f"{label}: expected 1 anchor, found {count}")
    return text.replace(old, new, 1)


path = Path("healthia_one/google_mission_runtime.py")
text = path.read_text("utf-8")
text = replace_once(
    text,
    "from healthia_one.google_mission_actions import (\n",
    "from healthia_one.lazy_google_clients import LazyFirestoreClient\n\nfrom healthia_one.google_mission_actions import (\n",
    "lazy import",
)
text = replace_once(
    text,
    'class FirestoreMissionStore:\n    COLLECTION = "healthia_google_missions"\n\n    def __init__(self, project: str | None = None) -> None:\n        from google.cloud import firestore\n\n        self.client = firestore.Client(project=project)\n',
    'class FirestoreMissionStore(LazyFirestoreClient):\n    COLLECTION = "healthia_google_missions"\n\n    def __init__(self, project: str | None = None) -> None:\n        self._configure_firestore(project)\n',
    "mission constructor",
)
path.write_text(text, "utf-8")
print("HEALTHIA_LAZY_MISSION_STORE_PATCH_PASS")
