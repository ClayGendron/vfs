"""The pattern-matching layer — pure authorities over the pattern-search family.

One module per verb language: :mod:`.glob` owns the path-pattern
language (defect gate, compile chokepoint, derived facts, the
structural path gates, the router's composition/residuation algebra),
:mod:`.grep` owns the content-match authority (verifier, per-file
verification). Paths and text in, decisions out — no storage types, no
router types, no sessions. Storage prefilters and router dispatch both
defer to this layer, and nothing in it may ever know where rows come
from: the layer imports only ``vfs.paths``, ``vfs.models``, and the
``vfs.native`` engine seam, and the internal dependency runs one way
(grep uses glob's compiled filters and path gates; glob never looks
back).
"""

from vfs.pattern_matching.glob import (
    GLOB_CHANNEL_LABELS,
    MAX_PATTERN_ARMS,
    DerivedExt,
    GlobFilter,
    compile_filter,
    compile_glob,
    composed_pattern,
    derive_ext,
    effective_pattern,
    escape_glob,
    expand_pattern,
    filter_paths,
    glob_defect,
    passes_filters,
    render_residual,
    residuals,
)
from vfs.pattern_matching.grep import (
    ContentMatcher,
    GrepHit,
    PatternError,
    compile_verifier,
    filter_candidates,
    match_texts,
    split_lines,
    verify,
)

__all__ = [
    "GLOB_CHANNEL_LABELS",
    "MAX_PATTERN_ARMS",
    "ContentMatcher",
    "DerivedExt",
    "GlobFilter",
    "GrepHit",
    "PatternError",
    "compile_filter",
    "compile_glob",
    "compile_verifier",
    "composed_pattern",
    "derive_ext",
    "effective_pattern",
    "escape_glob",
    "expand_pattern",
    "filter_candidates",
    "filter_paths",
    "glob_defect",
    "match_texts",
    "passes_filters",
    "render_residual",
    "residuals",
    "split_lines",
    "verify",
]
