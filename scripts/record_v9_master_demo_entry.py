from __future__ import annotations

import record_v6_functional_demo as core
import record_v9_master_demo as master

# V9 reuses helpers that live in the earlier recorder modules. Bind the canonical
# chat helper and the final scientific-radar implementation explicitly so the
# master demo can exercise the real product paths without copying their logic.
master.base.send_chat = core.send_chat
master.science = master.base

if __name__ == "__main__":
    master.run()
