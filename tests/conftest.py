from __future__ import annotations

import os


# Product defaults remain fail-closed. The offline test suite opts into the
# synthetic unauthenticated fixture unless a test supplies its own boundary.
os.environ.setdefault("HEALTHIA_AUTH_REQUIRED", "false")
