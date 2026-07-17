"""Evidence for story 043 — run with: uv run python context/stories/043-entry-authoring-intent/repro.py

Demonstrates, against models2 at 06cf551, two authoring-boundary defects:

1. Explicit content silently destroyed: an extensionless path off the
   ``EXTENSIONLESS_FILES`` allowlist infers ``kind="directory"``, and the
   directory invariant then nulls the content the caller passed. Same
   construction with an allowlisted leaf (``todo``) keeps its content —
   the caller's data survives or dies on a name lottery.
2. ``model_validate`` mutates the caller's mapping: ``_derive_identity``
   injects ``kind``/``name`` into the dict it was handed.
"""

from __future__ import annotations

from vfs.models2 import Entry

print("-- 1. explicit content silently dropped on inferred kind --")
lost = Entry(path="/notes/journal", content="hello world")
print(f"journal (not allowlisted):  kind={lost.kind!r}  content={lost.content!r}")
kept = Entry(path="/notes/todo", content="hello world")
print(f"todo (allowlisted):         kind={kept.kind!r}  content={kept.content!r}")

print("-- 2. model_validate mutates the caller's dict --")
data = {"path": "/a/b.md"}
Entry.model_validate(data)
print("caller dict after model_validate:", data)
