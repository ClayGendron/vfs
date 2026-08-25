# Fixture document

A markdown fixture with heading hierarchy, lists, and a code block, so
the heading-hierarchical grammar has real boundaries to cut on.

## First section

Prose paragraph one, long enough to matter. It continues across a
second line and a third to give the walker a paragraph-sized node.

- one list item
- another list item
- a third, slightly longer list item to widen the node

## Second section

Another paragraph sits here between the sections, holding the middle of
the document together with unremarkable but honest filler text.

```python
def sample(n):
    return n * 2
```

### Nested subsection

Deeper heading, shorter body.

## Third section

The closing section carries the final paragraph, and one more sentence
so the last node does not end flush with the heading above it.
