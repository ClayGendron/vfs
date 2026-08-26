import sys, time, os, subprocess
from corpus import make_chunks

which = sys.argv[1]
chunks = make_chunks()
n = len(chunks)
tot_chars = sum(len(c) for c in chunks)
print(f"corpus: {n} chunks, {tot_chars/n:.0f} chars/chunk avg")

def import_time(mod):
    t = subprocess.run([sys.executable, "-c", f"import time; t=time.perf_counter(); import {mod}; print(time.perf_counter()-t)"],
                       capture_output=True, text=True)
    return float(t.stdout.strip())

if which == "hash":
    from hash_embed import embed_batch
    t = time.perf_counter(); out = embed_batch(chunks, 256); dt = time.perf_counter() - t
    print(f"hash import: ~0 s (stdlib only)")
    print(f"hash dim=256: {n/dt:,.0f} chunks/s ({dt:.2f} s for {n})")
    t = time.perf_counter(); out = embed_batch(chunks, 1536); dt = time.perf_counter() - t
    print(f"hash dim=1536: {n/dt:,.0f} chunks/s ({dt:.2f} s for {n})")
elif which == "model2vec":
    print(f"model2vec import: {import_time('model2vec'):.3f} s")
    from model2vec import StaticModel
    t = time.perf_counter(); m = StaticModel.from_pretrained("minishlab/potion-base-8M"); print(f"load: {time.perf_counter()-t:.3f} s, dim={m.dim}")
    # tokens per chunk via the model's own tokenizer
    ids = m.tokenize(chunks[:200]); print(f"tokens/chunk (model tokenizer): {sum(map(len, ids))/200:.0f}")
    for mp in (False, True):
        t = time.perf_counter(); out = m.encode(chunks, use_multiprocessing=mp, show_progress_bar=False); dt = time.perf_counter() - t
        print(f"model2vec use_multiprocessing={mp}: {n/dt:,.0f} chunks/s ({dt:.2f} s for {n}); shape={out.shape}")
    t = time.perf_counter(); [m.encode(c) for c in chunks[:1000]]; dt = time.perf_counter() - t
    print(f"model2vec single-call latency: {dt/1000*1000:.2f} ms/chunk")
elif which == "fastembed":
    print(f"fastembed import: {import_time('fastembed'):.3f} s")
    from fastembed import TextEmbedding
    t = time.perf_counter(); m = TextEmbedding("BAAI/bge-small-en-v1.5"); print(f"load: {time.perf_counter()-t:.3f} s")
    sub = chunks[:1000]
    t = time.perf_counter(); out = list(m.embed(sub, batch_size=64)); dt = time.perf_counter() - t
    print(f"fastembed bge-small (1000 chunks, threads default): {len(sub)/dt:,.0f} chunks/s ({dt:.2f} s); dim={len(out[0])}")
