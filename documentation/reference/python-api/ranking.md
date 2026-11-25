# Ranking

How `search` orders its results. The `ranking` module holds what a storage backend is told about ranking, and the `rerank` module holds what a file system does to the results of several mounts.

## Ranking in a Storage Backend

A `Ranker` is what `DatabaseStorage` takes as `ranker`. It names the signals a mount keeps and how the scores of a search are joined.

```python
from vfs import ranking

links = ranking.Signal("links", ranking.InDegree())
ranker = ranking.Ranker(signals=(links,))
```

::: vfs.ranking

## Reranking in a File System

A `Reranker` is one step a file system runs over the results from all its mounts. A file system takes a list of them as `rerankers`.

```python
from vfs import rerank
```

::: vfs.rerank
