from __future__ import annotations

import record_v6_functional_demo as core
import record_v9_master_demo as master

# V9 reuses the final V6/V8 product recorder module, whose public re-export list
# intentionally omitted send_chat. Bind the original working helper explicitly.
master.base.send_chat = core.send_chat

if __name__ == "__main__":
    master.run()
