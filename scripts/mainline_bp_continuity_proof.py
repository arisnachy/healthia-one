from __future__ import annotations

import asyncio
import sys
from pathlib import Path

from google.cloud import firestore

# The production image intentionally excludes scripts/.  The ephemeral proof
# overlay copies this directory as plain files, not as an installed Python
# package.  Import the already-proven harness from the wrapper's own directory
# so no __init__.py or production package surface is required.
SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from guardian_wave14_stitch_proof import (  # noqa: E402
    await_email as proven_await_email,
    client,
    proof_ref,
    reply as proven_reply,
    require_identity,
    restore as proven_restore,
    setup as proven_setup,
    verify as proven_verify,
)


async def setup() -> None:
    """Run the proven setup path and stamp its no-chat origin durably."""
    require_identity()
    await proven_setup()
    proof_ref(client()).set(
        {
            "no_chat_prompt_used": True,
            "trigger_origin": "deterministic_bp_followup_reconciliation",
            "trigger_model_calls": 0,
            "trigger_network_calls": 0,
            "mainline_scope": "explicitly_opted_in_bp_followup_only",
            "no_prompt_evidence_at": firestore.SERVER_TIMESTAMP,
        },
        merge=True,
    )


async def await_email() -> None:
    await proven_await_email()


async def reply() -> None:
    await proven_reply()


async def verify() -> None:
    await proven_verify()


async def restore() -> None:
    await proven_restore()


async def main() -> None:
    phases = {"setup", "await_email", "reply", "verify", "restore"}
    if len(sys.argv) != 2 or sys.argv[1] not in phases:
        raise SystemExit("usage: mainline_bp_continuity_proof.py setup|await_email|reply|verify|restore")
    await globals()[sys.argv[1]]()


if __name__ == "__main__":
    asyncio.run(main())
