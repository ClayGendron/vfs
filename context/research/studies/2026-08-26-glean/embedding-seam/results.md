# Raw measurements — embedding-seam study (2026-08-26)

Host: Apple M1 Pro, 10 cores, macOS (Darwin 25.5.0), CPython 3.13.11.
Throwaway venvs under the session scratchpad (`uv venv` + `uv pip install`);
the project's pyproject/lockfile were not touched.

Package versions: model2vec 0.9.0, numpy 2.5.2, tokenizers 0.23.1;
fastembed 0.8.0, onnxruntime 1.29.0 (CPUExecutionProvider).

Corpus (`corpus.py`): 10,000 synthetic chunks, 375 words each, 2,322 chars
avg; potion-base-8M's tokenizer counts 464 tokens/chunk.

## hash embedder (`hash_embed.py`, stdlib only)

    hash dim=256:  9,777 chunks/s (1.02 s for 10000)
    hash dim=1536: 5,955 chunks/s (1.68 s for 10000)

## model2vec potion-base-8M (`bench.py model2vec`)

    site-packages: 51 MB, 24 packages, no torch
      (numpy 21M, tokenizers 8.4M, hf_xet 8.1M, huggingface_hub 3.3M,
       joblib 1.3M, safetensors 1.1M, fsspec, yaml, anyio, jinja2, ...)
    import model2vec: 1.005 s cold (first run), 0.087 s warm (min of 3)
    from_pretrained (HF cache warm): 1.037 s, dim=256
    model files: model.safetensors 30,236,760 B; tokenizer.json 683,666 B;
                 vocab.txt 219,690 B  (~31 MB total)
    use_multiprocessing=False: 5,212 chunks/s (1.92 s for 10000)
    use_multiprocessing=True:  6,136 chunks/s (1.63 s for 10000)
    single-call latency: 0.54 ms/chunk

## fastembed BAAI/bge-small-en-v1.5 (`bench.py fastembed`, `bench_fe2.py`)

    site-packages: 141 MB, 30 packages (onnxruntime 75M, PIL 13M, numpy 21M)
    import fastembed: 4.205 s
    TextEmbedding(...) load: 3.449 s; model cache 64 MB (qdrant int8 ONNX)
    1000 chunks, batch_size=64, default threads: 4 chunks/s (237.7 s)
    200 chunks, threads=10, batch 8:  3.8 chunks/s (53.1 s)
    200 chunks, threads=10, batch 32: 3.9 chunks/s (50.6 s)
    200 chunks truncated to 400 chars (~100 tokens): 21.9 chunks/s
    -> 10^5 chunks of ~500 tokens: ~7 h on this CPU
