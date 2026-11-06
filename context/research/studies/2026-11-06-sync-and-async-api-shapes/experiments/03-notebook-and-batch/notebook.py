"""Run each API shape inside a real ipykernel, the way a data engineer's notebook runs it.

Builds a notebook in memory, executes it with nbclient against the python3
kernel, and prints every cell's source and output. Run from /home/user/vfs:
uv run --with polars --with nbclient --with nbformat python <this file>
"""

import nbformat
from nbclient import NotebookClient

CELLS = [
    # 1. Is a loop running on the kernel's main thread while a cell runs?
    "import asyncio, threading\nloop = asyncio.get_running_loop()\nprint('running loop:', type(loop).__name__, loop.is_running(), threading.current_thread().name)",
    # 2. asyncio.run from a cell
    "try:\n    asyncio.run(asyncio.sleep(0))\nexcept RuntimeError as e:\n    print('asyncio.run ->', type(e).__name__, e)",
    # 3. top-level await of the async router
    "from vfs.base import VirtualFileSystem\nfrom vfs.storage.backends.memory import InMemoryStorage\nafs = VirtualFileSystem(storage=InMemoryStorage())\nr = await afs.write(path='/a.txt', content='x')\nprint('await write ok:', r.success, '| await read:', (await afs.read('/a.txt')).one().content)",
    # 4. forgotten await
    "r = afs.read('/a.txt')\nprint('forgotten await gives:', type(r).__name__)\ntry:\n    r.one()\nexcept AttributeError as e:\n    print('next line ->', type(e).__name__, e)\nr.close()",
    # 5. the sync facade in a cell, 10,000 entries as a list, then a generator
    "from vfs.sync import SyncVirtualFileSystem\nfrom vfs.models import Entry\nfrom vfs.paths import Path\nfs = SyncVirtualFileSystem(storage=InMemoryStorage())\nrows = [Entry(path=Path(f'/d{i % 100}/f{i}.txt'), content=f'row {i}') for i in range(10_000)]\nr = fs.write(entries=rows, parents=True)\nprint('sync write list:', r.success, len(r))\ngen = (Entry(path=Path(f'/g/f{i}.txt'), content='g') for i in range(10_000))\nr = fs.write(entries=gen, parents=True)\nprint('sync write generator:', r.success, len(r), [e.detail for e in r.errors][:1])\nprint('sync read:', fs.read('/d1/f1.txt').one().content)",
    # 6. a blocking call starves the kernel loop: count loop ticks during one sync call
    "ticks = [0]\ndef tick():\n    ticks[0] += 1\n    loop.call_soon(tick)\nloop.call_soon(tick)\nbefore = ticks[0]\nfs.write(entries=[Entry(path=Path(f'/b/f{i}.txt'), content='b') for i in range(10_000)], parents=True)\nprint('kernel-loop ticks during the blocking call:', ticks[0] - before)\nawait asyncio.sleep(0.01)\nprint('ticks after yielding once:', ticks[0] - before > 0)\nticks.append('stop')\ntick = lambda: None",
    # 7. fsspec's sync() from inside the running kernel loop
    "import fsspec.asyn\nasync def answer():\n    return threading.current_thread().name\nprint('fsspec.asyn.sync ran on thread:', fsspec.asyn.sync(fsspec.asyn.get_loop(), answer))",
    # 8. pandas to_sql of 10,000 rows with chunksize, statements counted
    "import pandas as pd, sqlalchemy as sa\nfrom sqlalchemy import event\neng = sa.create_engine('sqlite://')\ncount = {'stmts': 0}\n@event.listens_for(eng, 'before_cursor_execute')\ndef _c(*a):\n    count['stmts'] += 1\ndf = pd.DataFrame({'path': [f'/f{i}' for i in range(10_000)], 'body': ['x'] * 10_000})\nfor cs, m in ((None, None), (1000, None), (1000, 'multi')):\n    count['stmts'] = 0\n    n = df.to_sql('t', eng, if_exists='replace', index=False, chunksize=cs, method=m)\n    print(f'to_sql chunksize={cs} method={m}: rows={n} cursor executes={count[\"stmts\"]}')\nit = pd.read_sql('select * from t', eng, chunksize=2500)\nprint('read_sql chunksize returns:', type(it).__name__, [len(c) for c in it])",
    # 9. pandas over an async engine
    "from sqlalchemy.ext.asyncio import create_async_engine\naeng = create_async_engine('sqlite+aiosqlite://')\nimport warnings\nwith warnings.catch_warnings(record=True) as w:\n    warnings.simplefilter('always')\n    try:\n        pd.read_sql('select 1 as x', aeng)\n    except Exception as e:\n        print('pandas read_sql(AsyncEngine) ->', type(e).__name__, str(e)[:120])\n    print('warnings:', [str(x.message)[:90] for x in w])",
    # 10. polars over an async engine, then what asyncio.run does afterwards
    "import polars as pl\nprint('polars', pl.__version__, 'read_database(AsyncEngine) ->', pl.read_database('select 1 as x', aeng).to_dicts())\nprint('loop patched by nest_asyncio:', hasattr(asyncio, '_nest_patched'))\ntry:\n    print('asyncio.run after polars ->', asyncio.run(asyncio.sleep(0, result='now allowed')))\nexcept RuntimeError as e:\n    print('asyncio.run after polars ->', type(e).__name__, e)",
    # 11. a worker thread from a cell: does the sync facade work from a ThreadPoolExecutor
    "from concurrent.futures import ThreadPoolExecutor\nwith ThreadPoolExecutor(8) as pool:\n    out = list(pool.map(lambda i: fs.read(f'/d{i % 100}/f{i}.txt').one().content, range(200)))\nprint('200 reads from 8 threads:', len(out), out[:2])\nfs.close()",
]

nb = nbformat.v4.new_notebook()
nb.cells = [nbformat.v4.new_code_cell(src) for src in CELLS]
NotebookClient(nb, kernel_name="python3", timeout=300, allow_errors=True).execute()
for i, cell in enumerate(nb.cells, 1):
    print(f"--- cell {i}")
    for out in cell.outputs:
        if out.output_type == "stream":
            print(out.text.rstrip())
        elif out.output_type == "error":
            print("ERROR", out.ename, out.evalue[:200])
