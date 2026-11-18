# Embedding

An embedding provider turns text into vectors, which is what `search` compares. The `embedding` module holds the providers and the type every provider follows.

```python
from vfs import embedding
```

`DatabaseStorage` takes an `embedding.EmbeddingProvider` as `embedder` and an `embedding.NativeEmbeddingConfig` as `native_embedding`.

::: vfs.embedding
