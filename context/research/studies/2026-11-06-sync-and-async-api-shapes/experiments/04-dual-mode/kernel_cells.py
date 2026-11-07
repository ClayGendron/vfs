"""Setting 2 for real: execute cells in an ipykernel through jupyter_client and print each cell's output."""

from __future__ import annotations

import os
from pathlib import Path

from jupyter_client.manager import start_new_kernel

HERE = Path(__file__).parent.resolve()

CELLS = [
    f"import os, sys, asyncio; os.environ['PREFECT_LOGGING_LEVEL']='ERROR'; sys.path.insert(0, {str(HERE)!r})\n"
    "from mechanisms import MECHANISMS\n"
    "try:\n    asyncio.get_running_loop(); print('cell sees a running loop')\n"
    "except RuntimeError:\n    print('cell sees no running loop')",
]
for name in ["detect", "prefect_sync_compatible", "prefect_async_dispatch", "fsspec_sync_flag", "twins",
             "asgiref_plain", "greenback", "lazy_portal", "handle_result"]:
    spell = f"MECHANISMS[{name!r}]().read('a')" + (".result()" if name == "handle_result" else "")
    CELLS.append(
        f"try:\n    r = {spell}\n    print({name!r}, 'sync spelling ->', type(r).__name__, getattr(r, 'thread', 'NO .thread'))\n"
        f"except Exception as e:\n    print({name!r}, 'sync spelling -> RAISED', type(e).__name__, str(e)[:90])"
    )
    if name not in ("greenback", "asgiref_plain", "twins", "fsspec_sync_flag"):
        CELLS.append(f"r = await MECHANISMS[{name!r}]().read('a')\nprint({name!r}, 'await spelling ->', type(r).__name__, r.thread)")
CELLS += [
    "import greenback\nawait greenback.ensure_portal()\nprint('portal made in this cell')",
    "try:\n    r = MECHANISMS['greenback']().read('a')\n    print('greenback next cell, after portal ->', type(r).__name__, r.thread)\n"
    "except Exception as e:\n    print('greenback next cell -> RAISED', type(e).__name__, str(e)[:80])",
    "await greenback.ensure_portal()\nr = MECHANISMS['greenback']().read('a')\nprint('greenback same cell as portal ->', type(r).__name__, r.thread)",
    "import threading\nprint(sorted({t.name.split('_')[0] for t in threading.enumerate()}))",
]

km, kc = start_new_kernel(kernel_name="python3", env={**os.environ, "PYTHONWARNINGS": "always"})
try:
    for code in CELLS:
        msg_id = kc.execute(code)
        while True:
            msg = kc.get_iopub_msg(timeout=30)
            if msg["parent_header"].get("msg_id") != msg_id:
                continue
            kind, content = msg["msg_type"], msg["content"]
            if kind == "stream":
                for line in content["text"].splitlines():
                    if line.strip() and "tracemalloc" not in line:
                        print(f"[{content['name']}] {line[:200]}")
            elif kind == "error":
                print(f"[error] {content['ename']}: {content['evalue'][:160]}")
            elif kind == "status" and content["execution_state"] == "idle":
                break
finally:
    kc.stop_channels()
    km.shutdown_kernel(now=True)
