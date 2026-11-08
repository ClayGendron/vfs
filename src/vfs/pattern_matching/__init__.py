"""The pattern-matching layer — pure authorities over the pattern-search family.

One module per verb language: :mod:`.glob` owns the path-pattern
language (defect gate, compile chokepoint, derived facts, the call's
gates over native verdicts, the router's composition/residuation algebra),
:mod:`.grep` owns the content-match authority (verifier, per-file
verification). Paths and text in, decisions out — no storage types, no
router types, no sessions. Storage prefilters and router dispatch both
defer to this layer, and nothing in it may ever know where rows come
from: the layer imports only ``vfs.paths``, ``vfs.models``, and the
``vfs.native`` engine seam, and the internal dependency runs one way
(grep shares glob's refusal type; glob never looks back).
"""

from vfs.pattern_matching.glob import (
    GLOB_CHANNEL_LABELS,
    MAX_PATTERN_ARMS,
    ROW_GATE_FIELDS,
    DerivedExt,
    GlobChannel,
    GlobFilter,
    GlobGates,
    GlobProgram,
    GlobSet,
    PatternError,
    ScopeChannel,
    canonical_pattern,
    compile_filter,
    compile_gates,
    compile_glob,
    composed_pattern,
    derive_ext,
    effective_pattern,
    escape_glob,
    expand_channel,
    expand_pattern,
    glob_defect,
    render_residual,
    residuals,
)
from vfs.pattern_matching.grep import (
    Body,
    ContentMatcher,
    GrepHit,
    compile_verifier,
    match_texts,
    split_lines,
    verify,
)

__all__ = [
    "GLOB_CHANNEL_LABELS",
    "MAX_PATTERN_ARMS",
    "ROW_GATE_FIELDS",
    "Body",
    "ContentMatcher",
    "DerivedExt",
    "GlobChannel",
    "GlobFilter",
    "GlobGates",
    "GlobProgram",
    "GlobSet",
    "GrepHit",
    "PatternError",
    "ScopeChannel",
    "canonical_pattern",
    "compile_filter",
    "compile_gates",
    "compile_glob",
    "compile_verifier",
    "composed_pattern",
    "derive_ext",
    "effective_pattern",
    "escape_glob",
    "expand_channel",
    "expand_pattern",
    "glob_defect",
    "match_texts",
    "render_residual",
    "residuals",
    "split_lines",
    "verify",
]
