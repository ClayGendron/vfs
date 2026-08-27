# Rustworkx Graph Provider

This is my thoughts and ideas of how to implement the rustworkx graph provider. Please see /Users/claygendron/Git/Repos/grover/research/graph-memory-and-meeting-subgraph.md for more context.

## Minimal In-Memory Data

I want to update our Rustworkx Graph to not be stored as a graph in memory. Instead, we will store the data as a list of nodes and list of edges as pure python objects. The lists only contain the path references, no other metadata.

When we need to use the graph, we build a new version of it, use it, and then dispose of it (or let python garbage collect it).

We need to do this so there is not one global graph in the async use case as that could slow things down.

```python
class RustworkxGraph:
    def __init__(self) -> None:
        self.nodes: set[str] # or Ref
        self.edges: set[(str, str)] # or Ref
        
    def graph(self) -> rx.PyDiGraph:
      ...

```

## Support For FileSearchResult Chaining

When calling graph operations, we 