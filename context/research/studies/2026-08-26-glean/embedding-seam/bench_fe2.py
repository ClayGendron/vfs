import os, time
from corpus import make_chunks
from fastembed import TextEmbedding
chunks = make_chunks()[:200]
m = TextEmbedding("BAAI/bge-small-en-v1.5", threads=os.cpu_count())
print("providers:", getattr(m.model, "model", None) and m.model.model.get_providers() if hasattr(m, "model") else "?")
for bs in (8, 32):
    t = time.perf_counter(); out = list(m.embed(chunks, batch_size=bs)); dt = time.perf_counter() - t
    print(f"fastembed bge-small threads={os.cpu_count()} batch={bs}: {len(chunks)/dt:,.1f} chunks/s ({dt:.1f} s for {len(chunks)})")
short = [c[:400] for c in chunks]
t = time.perf_counter(); out = list(m.embed(short, batch_size=32)); dt = time.perf_counter() - t
print(f"fastembed bge-small ~100-token chunks: {len(short)/dt:,.1f} chunks/s")
