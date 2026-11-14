"""v19-p3 independent repro: the shipped OpenAIEmbeddingProvider (real estimate_tokens and caps) over a fake
client that enforces 300000 tokens/request with a stand-in counter (1 token per CJK ideograph) and raises a real
openai.BadRequestError (httpx 400, no Retry-After). No network."""
import asyncio, json, math, sys
from types import SimpleNamespace
import httpx, openai
from sqlalchemy import select
from vfs.authority import Authority, Principal
from vfs.embedding import OpenAIEmbeddingProvider, hash_embedding
from vfs.models import Entry
from vfs.paths import Path
from vfs.storage.backends.database import DatabaseStorage

SYSTEM = Authority.system(); ALICE = Authority.of(Principal("alice")); BOB = Authority.of(Principal("bob"))

def toks(t):
    cjk = sum(1 for c in t if 0x4E00 <= ord(c) <= 0x9FFF)
    return cjk + math.ceil((len(t) - cjk) / 4)

class FakeEmbeddings:
    def __init__(self): self.calls = []; 
    async def create(self, *, input, model, encoding_format, dimensions=None):
        total = sum(toks(t) for t in input)
        self.calls.append((len(input), total))
        if total > 300_000:
            req = httpx.Request("POST", "https://api.invalid/v1/embeddings")
            resp = httpx.Response(400, request=req, json={"error": {"message": f"Requested {total} tokens, max 300000 tokens per request"}})
            raise openai.BadRequestError(f"Requested {total} tokens, max 300000 tokens per request", response=resp, body=None)
        data = [SimpleNamespace(index=i, embedding=hash_embedding(t, 256)) for i, t in enumerate(input)]
        return SimpleNamespace(data=data, usage=SimpleNamespace(total_tokens=total))

CJK = "".join(chr(c) for c in range(0x4E00, 0x4E00 + 3000))
def alice_body(i, n=160):
    h = f"{i:05d} "; s = (i * 11) % 2500
    return h + (CJK[s:] + CJK)[: n - len(h)]

async def state(st):
    h = st._host; ch, en = h.tables.chunks, h.tables.entry
    out = {}
    async with h.engine.connect() as c:
        for r in await c.execute(select(en.c.path, ch.c.embedding).select_from(ch.join(en, en.c.entry_id == ch.c.entry_id))):
            d = out.setdefault(str(r.path).split("/")[1], [0, 0]); d[0] += 1; d[1] += r.embedding is not None
    return {k: {"chunks": v[0], "embedded": v[1]} for k, v in out.items()}

async def run(n_alice, db):
    client = SimpleNamespace(embeddings=FakeEmbeddings())
    prov = OpenAIEmbeddingProvider(client, "text-embedding-3-small", dimensions=256)
    st = DatabaseStorage(url=f"sqlite+aiosqlite:///{db}", embedder=prov)
    for n in ("alice", "bob"):
        assert (await st.write(entries=[Entry(path=Path(f"/{n}/README.txt"), content=f"{n} home dir\n")], parents=True, authority=SYSTEM)).success
        assert (await st.grant(path=Path(f"/{n}"), principal=n, level="read_write", authority=SYSTEM)).success
    await st.reindex()
    if n_alice:
        r = await st.write(entries=[Entry(path=Path(f"/alice/n/{i:05d}.txt"), content=alice_body(i)) for i in range(n_alice)], parents=True, authority=ALICE)
        assert r.success, r.errors
    r = await st.write(entries=[Entry(path=Path(f"/bob/d/{i:03d}.txt"), content=f"bob invoice shipping memo {i} about freight and customs\n") for i in range(40)], parents=True, authority=BOB)
    assert r.success, r.errors
    runs = []
    for k in range(2):
        c0 = len(client.embeddings.calls)
        res = await st.reindex()
        runs.append({"run": k + 1, "success": res.success, "embedding": res.embedding,
                     "errors": [{"kind": str(e.kind), "retryable": e.retryable, "message": e.message} for e in res.errors],
                     "provider_calls": client.embeddings.calls[c0:], "state": await state(st)})
    g = await st.glean(query="invoice shipping freight", limit=5, authority=BOB)
    out = {"n_alice": n_alice, "runs": runs, "bob_glean_vector_leg": (g.legs or {}).get("vector")}
    await st.close()
    return out

if __name__ == "__main__":
    print(json.dumps(asyncio.run(run(int(sys.argv[1]), sys.argv[2])), default=str))
