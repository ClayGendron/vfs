"""Interface of the compiled Rust engine module (crates/vfs-core, pyo3).

The implementation lives in crates/vfs-core/src/python.rs; this stub is
the typed surface the seam (vfs/native.py) programs against.
"""

PROTOCOL_VERSION: int

def distinct_gram_count(data: bytes, cap: int) -> int: ...

class PostingsBuilder:
    def add_docs(self, docs: list[tuple[int, bytes]]) -> None: ...
    def next_batch(self, byte_cap: int) -> list[tuple[int, bytes, int]] | None: ...
