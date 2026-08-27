"""The gram gate's oracle: count distinct trigrams, stop past the cap."""

from __future__ import annotations

from vfs.models.code_grams import GramKey, iter_byte_trigrams


def distinct_gram_count(data: bytes, cap: int) -> int:
    """Distinct trigrams of *data*, early-exiting past *cap* (any value over cap means "over cap")."""
    seen: set[GramKey] = set()
    for gram in iter_byte_trigrams(data):
        seen.add(gram)
        if len(seen) > cap:
            break
    return len(seen)
