"""The pattern-matching layer — pure authorities over the pattern-search family.

One module per verb language: :mod:`.glob` owns the path-pattern
language (defect gate, compile chokepoint, derived facts, the router's
composition/residuation algebra), :mod:`.grep` owns the content-match
authority (verifier, per-file verification, structural path gates).
Paths and text in, decisions out — no storage types, no router types,
no sessions. Storage prefilters and router dispatch both defer to this
layer, and nothing in it may ever know where rows come from: the layer
imports only ``vfs.paths`` and ``vfs.models``, and the internal
dependency runs one way (grep uses glob's compiled filters for its
path gates; glob never looks back).
"""

from vfs.pattern_matching.glob import (
    MAX_PATTERN_ARMS,
    DerivedExt,
    GlobFilter,
    compile_filter,
    compile_glob,
    composed_pattern,
    derive_ext,
    effective_pattern,
    expand_pattern,
    filter_paths,
    glob_defect,
    render_residual,
    residuals,
)
from vfs.pattern_matching.grep import (
    GrepHit,
    compile_verifier,
    filter_candidates,
    match_texts,
    passes_filters,
    verify,
)

__all__ = [
    "MAX_PATTERN_ARMS",
    "DerivedExt",
    "GlobFilter",
    "GrepHit",
    "compile_filter",
    "compile_glob",
    "compile_verifier",
    "composed_pattern",
    "derive_ext",
    "effective_pattern",
    "expand_pattern",
    "filter_candidates",
    "filter_paths",
    "glob_defect",
    "match_texts",
    "passes_filters",
    "render_residual",
    "residuals",
    "verify",
]
