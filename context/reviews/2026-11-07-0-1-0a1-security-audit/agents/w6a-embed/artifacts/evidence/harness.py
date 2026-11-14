"""w6a-embed harness: does one deterministically refused embed batch stop vector indexing store-wide?

Fake provider: implements the EmbeddingProvider protocol, declares the shipped OpenAI caps
(MAX_INPUT_TOKENS=8192, MAX_BATCH_INPUTS=2048, MAX_BATCH_TOKENS=300000) and estimates with vfs's
own estimate_tokens (ceil(len/4)), exactly as OpenAIEmbeddingProvider does, but *enforces* the
caps with a "real" count: 1 token per CJK char, ceil(len/4) for the rest. A cap overrun raises a
400-shaped error with no Retry-After (a deterministic refusal). No network; vectors are hash vectors.

Scenario FULL (unscaled caps, unscaled EMBED_PAGE_ROWS=4096): alice writes 4096 small CJK files
(160 CJK chars each: estimate 40, real 160 tokens); then bob writes ordinary English files.
Scenario CONTROL: FULL with zero alice files (bob alone).
Scenario PARTIAL (batch token cap scaled 300000 -> 3000, i.e. /100; all else unscaled): alice writes
10 CJK files of 300 chars; bob writes 100 English files. Shows neighbour rows riding the poison batch.
"""

from __future__ import annotations

import asyncio
import json
import math
import sys
from types import SimpleNamespace

from sqlalchemy import select

from vfs.authority import Authority, Principal
from vfs.embedding import Embedded, estimate_tokens, hash_embedding
from vfs.embedding import openai as openai_mod
from vfs.models import Entry
from vfs.paths import Path
from vfs.storage.backends.database import DatabaseStorage
from vfs.storage.backends.database import backend as backend_module

SYSTEM = Authority.system()
ALICE = Authority.of(Principal("alice"))
BOB = Authority.of(Principal("bob"))


class BadRequest(Exception):
    """Shaped like openai.BadRequestError: a response whose headers carry no Retry-After."""

    def __init__(self, msg: str) -> None:
        super().__init__(msg)
        self.response = SimpleNamespace(status_code=400, headers={})


def real_tokens(text: str) -> int:
    cjk = sum(1 for ch in text if ord(ch) >= 0x2E80)
    rest = len(text) - cjk
    return max(1, cjk + math.ceil(rest / 4))


class CappedProvider:
    def __init__(self, *, max_batch_tokens: int, dimension: int = 16) -> None:
        self.dimension = dimension
        self.model_id = f"capped/fake@{dimension}"
        self.max_input_tokens = openai_mod.MAX_INPUT_TOKENS
        self.max_batch_inputs = openai_mod.MAX_BATCH_INPUTS
        self.max_batch_tokens = max_batch_tokens
        self.requests = 0
        self.refused = 0
        self.refused_sizes: list[tuple[int, int, int]] = []

    def estimate_tokens(self, text: str) -> int:
        return estimate_tokens(text)

    async def embed_query(self, text: str) -> list[float]:
        return hash_embedding(text, self.dimension)

    async def embed_documents(self, texts):
        self.requests += 1
        texts = list(texts)
        if len(texts) > self.max_batch_inputs:
            raise BadRequest("too many inputs")
        for t in texts:
            if real_tokens(t) > self.max_input_tokens:
                self.refused += 1
                raise BadRequest(f"input of {real_tokens(t)} tokens exceeds {self.max_input_tokens}")
        total = sum(real_tokens(t) for t in texts)
        if total > self.max_batch_tokens:
            self.refused += 1
            self.refused_sizes.append((len(texts), sum(estimate_tokens(t) for t in texts), total))
            raise BadRequest(f"Requested {total} tokens, max {self.max_batch_tokens} tokens per request")
        return Embedded([hash_embedding(t, self.dimension) for t in texts], total)


CJK = "".join(chr(c) for c in range(0x4E00, 0x4E00 + 2000))


def cjk_body(i: int, n: int) -> str:
    # distinct per file so the content_hash cache never lends a vector
    start = (i * 7) % 1500
    head = f"{i:05d} "
    return head + (CJK[start:] + CJK)[: n - len(head)]


def bob_body(i: int) -> str:
    return f"bob quarterly report {i} " + "ordinary english prose about invoices and shipping " * 3 + "\n"


async def chunk_state(storage: DatabaseStorage) -> dict[str, dict[str, int]]:
    host = storage._host
    chunks, entry = host.tables.chunks, host.tables.entry
    out: dict[str, dict[str, int]] = {}
    async with host.engine.connect() as conn:
        rows = await conn.execute(
            select(entry.c.path, chunks.c.embedding).select_from(chunks.join(entry, entry.c.entry_id == chunks.c.entry_id))
        )
        for row in rows:
            who = str(row.path).split("/")[1]
            d = out.setdefault(who, {"chunks": 0, "embedded": 0})
            d["chunks"] += 1
            d["embedded"] += row.embedding is not None
    return out


async def setup(storage: DatabaseStorage) -> None:
    for name in ("alice", "bob"):
        r = await storage.write(entries=[Entry(path=Path(f"/{name}/README.txt"), content=f"{name} home\n")], parents=True, authority=SYSTEM)
        assert r.success, r.errors
        g = await storage.grant(path=Path(f"/{name}"), principal=name, level="read_write", authority=SYSTEM)
        assert g.success, g.errors


def summarize(result) -> dict:
    return {
        "success": result.success,
        "embedding": getattr(result, "embedding", None),
        "errors": [
            {"kind": str(e.kind), "severity": str(e.severity), "retryable": e.retryable, "message": e.message}
            for e in result.errors
        ],
    }


async def run(scenario: str, db: str) -> dict:
    if scenario == "full":
        provider = CappedProvider(max_batch_tokens=openai_mod.MAX_BATCH_TOKENS)
        n_alice, alice_len, n_bob = 4096, 160, 50
    elif scenario == "control":
        provider = CappedProvider(max_batch_tokens=openai_mod.MAX_BATCH_TOKENS)
        n_alice, alice_len, n_bob = 0, 160, 50
    else:
        provider = CappedProvider(max_batch_tokens=3000)
        n_alice, alice_len, n_bob = 10, 300, 100
    storage = DatabaseStorage(url=f"sqlite+aiosqlite:///{db}", embedder=provider)
    await setup(storage)
    # Index the homes first so their (system) chunks are embedded and out of the way.
    pre = await storage.reindex()
    report: dict = {
        "scenario": scenario,
        "caps": {
            "max_input_tokens": provider.max_input_tokens,
            "max_batch_inputs": provider.max_batch_inputs,
            "max_batch_tokens": provider.max_batch_tokens,
            "headroom_budget_estimated": provider.max_batch_tokens * 5 // 6,
            "EMBED_PAGE_ROWS": backend_module.EMBED_PAGE_ROWS,
        },
        "alice_files": n_alice,
        "alice_chars_each": alice_len,
        "alice_estimate_each": estimate_tokens(cjk_body(0, alice_len)),
        "alice_real_each": real_tokens(cjk_body(0, alice_len)),
        "bob_files": n_bob,
        "pre_reindex": summarize(pre),
    }
    alice = [Entry(path=Path(f"/alice/notes/{i:05d}.txt"), content=cjk_body(i, alice_len)) for i in range(n_alice)]
    if alice:
        r = await storage.write(entries=alice, parents=True, authority=ALICE)
        assert r.success, r.errors
    bob = [Entry(path=Path(f"/bob/docs/{i:03d}.txt"), content=bob_body(i)) for i in range(n_bob)]
    r = await storage.write(entries=bob, parents=True, authority=BOB)
    assert r.success, r.errors
    runs = []
    for k in range(3):
        before = provider.requests
        res = await storage.reindex()
        runs.append({
            "run": k + 1,
            "result": summarize(res),
            "provider_requests": provider.requests - before,
            "state": await chunk_state(storage),
        })
    report["reindex_runs"] = runs
    report["refused_batches_inputs_estimate_real"] = provider.refused_sizes[:12]
    g = await storage.glean(query="quarterly invoices shipping", limit=5, authority=BOB)
    report["bob_glean"] = {
        "success": g.success,
        "vector_leg": (getattr(g, "legs", None) or {}).get("vector"),
        "lexical_leg_hits": ((getattr(g, "legs", None) or {}).get("lexical") or {}).get("hits"),
        "top_paths": [str(o.path) for o in g.observations],
        "records": [e.message for e in g.errors],
    }
    await storage.close()
    return report


if __name__ == "__main__":
    scenario, db = sys.argv[1], sys.argv[2]
    print(json.dumps(asyncio.run(run(scenario, db)), indent=1, default=str))
