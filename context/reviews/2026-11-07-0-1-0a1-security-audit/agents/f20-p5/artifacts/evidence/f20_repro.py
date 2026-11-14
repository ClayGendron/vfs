"""f20-p5 independent repro: shipped OpenAIEmbeddingProvider over an offline fake client enforcing 300000
tokens/request (stand-in: 1 token per CJK ideograph), raising a real openai.BadRequestError (400, no Retry-After).
Modes: attack (alice 4096 CJK rows then bob 40), control (no alice rows), fixed (attack with byte-length estimate)."""
import asyncio, json, math, sys
from types import SimpleNamespace
import httpx, openai
from sqlalchemy import func, select
from vfs.authority import Authority, Principal
from vfs.embedding import OpenAIEmbeddingProvider, hash_embedding
from vfs.models import Entry
from vfs.paths import Path
from vfs.storage.backends.database import DatabaseStorage

SYS = Authority.system()

def real_tokens(text):
    cjk = sum(1 for ch in text if 0x4E00 <= ord(ch) <= 0x9FFF)
    return cjk + math.ceil((len(text) - cjk) / 4)

class Client:
    def __init__(self):
        self.calls = []
        self.embeddings = self
    async def create(self, *, input, model, encoding_format, dimensions=None):
        total = sum(real_tokens(t) for t in input)
        self.calls.append([len(input), total])
        if total > 300_000:
            rq = httpx.Request("POST", "https://offline.invalid/v1/embeddings")
            rs = httpx.Response(400, request=rq, json={"error": {"message": "too many tokens"}})
            raise openai.BadRequestError(f"Requested {total} tokens, max 300000 tokens per request", response=rs, body=None)
        return SimpleNamespace(data=[SimpleNamespace(index=i, embedding=hash_embedding(t, 64)) for i, t in enumerate(input)],
                               usage=SimpleNamespace(total_tokens=total))

def cjk_body(i):
    head = f"a{i:04d} "
    return head + "".join(chr(0x4E00 + (i * 7 + k) % 6000) for k in range(160 - len(head)))

async def per_dir(st):
    t = st._host.tables
    out = {}
    async with st._host.engine.connect() as c:
        rows = await c.execute(select(t.entry.c.path, t.chunks.c.embedding).select_from(t.chunks.join(t.entry, t.entry.c.entry_id == t.chunks.c.entry_id)))
        for r in rows:
            d = out.setdefault(str(r.path).split("/")[1], [0, 0]); d[0] += 1; d[1] += r.embedding is not None
    return out

async def main(mode, db):
    client = Client()
    prov = OpenAIEmbeddingProvider(client, "text-embedding-3-small", dimensions=64)
    if mode == "fixed":
        prov.estimate_tokens = lambda text: max(1, len(text.encode("utf-8")))
    st = DatabaseStorage(url=f"sqlite+aiosqlite:///{db}", embedder=prov)
    for who in ("alice", "bob"):
        assert (await st.write(entries=[Entry(path=Path(f"/{who}/home.txt"), content=f"{who} home directory\n")], parents=True, authority=SYS)).success
        assert (await st.grant(path=Path(f"/{who}"), principal=who, level="read_write", authority=SYS)).success
    await st.reindex()
    alice = Authority.of(Principal("alice")); bob = Authority.of(Principal("bob"))
    if mode != "control":
        r = await st.write(entries=[Entry(path=Path(f"/alice/x/{i:04d}.txt"), content=cjk_body(i)) for i in range(4096)], parents=True, authority=alice)
        assert r.success, r.errors
    # bob cannot touch alice's rows
    denied = await st.write(entries=[Entry(path=Path("/alice/x/0000.txt"), content="bob overwrite")], authority=bob)
    r = await st.write(entries=[Entry(path=Path(f"/bob/d/{i:02d}.txt"), content=f"quarterly freight invoice number {i} customs clearance\n") for i in range(40)], parents=True, authority=bob)
    assert r.success, r.errors
    runs = []
    for k in range(3):
        c0 = len(client.calls)
        res = await st.reindex()
        runs.append({"run": k + 1, "success": res.success, "embedding": res.embedding,
                     "errors": [[str(e.kind), e.retryable, e.message] for e in res.errors],
                     "calls": client.calls[c0:] if len(client.calls[c0:]) <= 6 else f"{len(client.calls[c0:])} calls, max tokens {max(c[1] for c in client.calls[c0:])}",
                     "chunks_total_embedded": await per_dir(st)})
    g = await st.glean(query="freight invoice customs", limit=5, authority=bob)
    print(json.dumps({"mode": mode, "bob_write_into_alice_success": denied.success, "runs": runs,
                      "bob_vector_leg": (g.legs or {}).get("vector")}, default=str))
    await st.close()

asyncio.run(main(sys.argv[1], sys.argv[2]))
