"""Pure-Python reference implementations that referee the Rust engine.

Nothing here ships. Each module is a readable, deliberately simple
twin of one engine surface — the posting builder and codec, the
tokenizer, lexical builder and BM25 scorer, the gram gate, the
matcher — kept only where a parity test reads it. The oracles import
the product's data model (``ScoreBlock``, ``fold_content`` …) but
never ``vfs.native``: an oracle that dispatched to the engine would
referee nothing.

The tokenizer oracle takes its character classes from the running
interpreter, so on an interpreter whose Unicode tables differ from
the engine's generated ones it can legitimately disagree on a handful
of code points; parity tests that would see that drift skip off the
generating interpreter.
"""
