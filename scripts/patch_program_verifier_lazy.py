from pathlib import Path

path = Path("healthia_one/program_source_verifier.py")
text = path.read_text("utf-8")

import_anchor = "from healthia_one.google_ai_transport import build_google_ai_client\n"
import_replacement = import_anchor + "from healthia_one.lazy_google_clients import LazyFirestoreClient\n"
if text.count(import_anchor) != 1:
    raise SystemExit("program verifier import anchor mismatch")
text = text.replace(import_anchor, import_replacement, 1)

old = '''class FirestoreProgramVerificationStore:
    COLLECTION = "healthia_program_verifications"

    def __init__(self, project: str | None = None) -> None:
        from google.cloud import firestore
        self.client = firestore.Client(project=project)
'''
new = '''class FirestoreProgramVerificationStore(LazyFirestoreClient):
    COLLECTION = "healthia_program_verifications"

    def __init__(self, project: str | None = None) -> None:
        self._configure_firestore(project)
'''
if text.count(old) != 1:
    raise SystemExit("program verifier constructor anchor mismatch")
text = text.replace(old, new, 1)
path.write_text(text, "utf-8")
print("HEALTHIA_PROGRAM_VERIFIER_LAZY_PATCH_PASS")
