"""The vector floor on MySQL 9 community: pull N 384-dim vectors and score them client-side.

Two storage encodings are measured for each N in (1k, 10k, 50k):
  json  -- TEXT column holding a JSON array (vfs's portable VectorType today)
  bin   -- native VECTOR(384) column, shipped as TO_BASE64(vb): pymysql cannot decode the raw
           VECTOR wire type (UnicodeDecodeError, verified), so base64 is the cheapest text-safe transport
Phases timed separately: fetch (SQL round trip + driver decode), parse
(json.loads / numpy.frombuffer), score (numpy cosine over the matrix), total.
"""

from __future__ import annotations

import asyncio
import json
from base64 import b64decode
import random
import sys
import time

import numpy as np
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

sys.path.insert(0, __file__.rsplit("/", 1)[0])
from probe_common import URLS, dump  # noqa: E402

DIMS = 384
SIZES = (1_000, 10_000, 50_000)
BATCH = 500


def rand_vec(rng: random.Random) -> list[float]:
    return [rng.uniform(-1, 1) for _ in range(DIMS)]


async def main():
    eng = create_async_engine(URLS["mysql9"])
    rng = random.Random(11)
    results = {}
    async with eng.begin() as conn:
        await conn.execute(text("drop table if exists floor_vec"))
        await conn.execute(text("create table floor_vec (id int primary key, vj text, vb vector(384)) engine=innodb"))
    # Insert incrementally so each size is a superset of the previous.
    have = 0
    q = np.array(rand_vec(rng), dtype=np.float32)
    qn = q / np.linalg.norm(q)
    for n in SIZES:
        t0 = time.perf_counter()
        async with eng.begin() as conn:
            while have < n:
                rows = []
                for i in range(have, min(n, have + BATCH)):
                    v = rand_vec(rng)
                    rows.append({"id": i, "vj": json.dumps(v), "vb": json.dumps(v)})
                await conn.execute(
                    text("insert into floor_vec (id, vj, vb) values (:id, :vj, string_to_vector(:vb))"), rows
                )
                have += len(rows)
        ins = time.perf_counter() - t0
        size = {"insert_s": round(ins, 2)}
        async with eng.connect() as conn:
            row = (await conn.execute(text(
                "select avg(length(vj)), avg(length(vb)) from floor_vec"))).one()
            size["avg_json_bytes"] = float(row[0])
            size["avg_bin_bytes"] = float(row[1])
            for enc, col in (("json", "vj"), ("bin", "to_base64(vb)")):
                best = None
                for _ in range(3):
                    t0 = time.perf_counter()
                    res = await conn.execute(text(f"select id, {col} from floor_vec"))
                    rows = res.fetchall()
                    t1 = time.perf_counter()
                    ids = np.fromiter((r[0] for r in rows), dtype=np.int64, count=len(rows))
                    if enc == "json":
                        mat = np.array([json.loads(r[1]) for r in rows], dtype=np.float32)
                    else:
                        mat = np.frombuffer(b"".join(b64decode(r[1]) for r in rows), dtype="<f4").reshape(len(rows), DIMS)
                    t2 = time.perf_counter()
                    norms = np.linalg.norm(mat, axis=1)
                    sims = (mat @ qn) / norms
                    top = np.argpartition(-sims, 10)[:10]
                    top_ids = ids[top[np.argsort(-sims[top])]].tolist()
                    t3 = time.perf_counter()
                    cur = {"fetch_s": round(t1 - t0, 3), "parse_s": round(t2 - t1, 3),
                           "score_s": round(t3 - t2, 4), "total_s": round(t3 - t0, 3), "top1": top_ids[0]}
                    if best is None or cur["total_s"] < best["total_s"]:
                        best = cur
                size[enc] = best
                print(f"N={n:>6} {enc:4} fetch={best['fetch_s']:.3f}s parse={best['parse_s']:.3f}s "
                      f"score={best['score_s']:.4f}s total={best['total_s']:.3f}s (best of 3)", flush=True)
        results[str(n)] = size
        print(f"N={n} insert={ins:.1f}s json_bytes={size['avg_json_bytes']:.0f} bin_bytes={size['avg_bin_bytes']:.0f}", flush=True)
    async with eng.begin() as conn:
        await conn.execute(text("drop table floor_vec"))
    await eng.dispose()
    dump(__file__.rsplit("/", 1)[0] + "/results_floor_mysql.json", results)


asyncio.run(main())
