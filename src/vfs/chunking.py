"""Recursive text splitter — region-aware rfind walker.

LangChain-compatible split: try each separator in priority order; oversized
pieces recurse into the next separator. Boundaries match the OLD ``str.split``
baseline for typical text/code at the bench config (2048/256). Pathological
char-fallback inputs (long runs without any separator) chunk with sliding
overlap rather than OLD's interleaved overlap-tail emissions.
"""
from __future__ import annotations

from bisect import bisect_left, bisect_right

DEFAULT_SEPARATORS: tuple[str, ...] = ("\n\n", "\n", " ", "")


def recursive_text_split(
    content: str,
    *,
    chunk_size: int = 2048,
    overlap: int = 256,
    separators: tuple[str, ...] = DEFAULT_SEPARATORS,
) -> list[str]:
    """Split *content* into pieces no larger than *chunk_size* characters."""
    offsets = _chunk_offsets(content, chunk_size=chunk_size, overlap=overlap, separators=separators)
    return [content[s:e] for s, e in offsets]


def split_with_line_ranges(
    content: str,
    *,
    chunk_size: int = 2048,
    overlap: int = 256,
    separators: tuple[str, ...] = DEFAULT_SEPARATORS,
) -> list[tuple[str, int, int]]:
    """Return ``(chunk_text, line_start, line_end)`` for each emitted chunk.

    Lines are 1-indexed; ``line_end`` is the line containing the chunk's last
    character. A chunk that lives entirely inside a single oversized line has
    ``line_start == line_end``.
    """
    offsets = _chunk_offsets(content, chunk_size=chunk_size, overlap=overlap, separators=separators)
    if not offsets:
        return []
    newlines: list[int] = []
    nl_append = newlines.append
    for i, c in enumerate(content):
        if c == "\n":
            nl_append(i)
    bisect = bisect_left
    out: list[tuple[str, int, int]] = []
    for s, e in offsets:
        line_start = bisect(newlines, s) + 1
        line_end = bisect(newlines, e - 1) + 1 if e > s else line_start
        out.append((content[s:e], line_start, line_end))
    return out


def _chunk_offsets(
    content: str,
    *,
    chunk_size: int,
    overlap: int,
    separators: tuple[str, ...],
) -> list[tuple[int, int]]:
    """Return the ``(start, end)`` offset pairs the splitter would emit.

    ``recursive_text_split`` slices ``content`` once per pair; callers that
    need positional metadata (line numbers, byte offsets) consume the pairs
    directly to avoid re-locating chunks.
    """
    if chunk_size <= 0:
        raise ValueError(f"chunk_size must be positive, got {chunk_size}")
    if overlap < 0 or overlap >= chunk_size:
        raise ValueError(f"overlap must be in [0, chunk_size); got {overlap}")
    if not separators:
        raise ValueError("separators must not be empty")
    n = len(content)
    if n <= chunk_size:
        return []

    # Drop seps not present in content; avoids per-chunk rfind for absent seps.
    seps_non_empty: list[str] = [s for s in separators if s != "" and s in content]

    # Per separator level, the active regions are oversized pieces of the prior
    # level. Sep 0 is active everywhere; sep i (i>0) is active only inside an
    # oversized sep-(i-1) piece. Bisect on starts gives O(log) "is active here".
    region_starts: list[tuple[int, ...]] = [()]
    region_ends: list[tuple[int, ...]] = [()]
    prev_regions: list[tuple[int, int]] = [(0, n)]
    for sep in seps_non_empty[:-1]:
        new_regions: list[tuple[int, int]] = []
        for s, e in prev_regions:
            new_regions.extend(_find_oversized(content, s, e, sep, chunk_size))
        if new_regions:
            starts, ends = zip(*new_regions, strict=True)
            region_starts.append(starts)
            region_ends.append(ends)
        else:
            region_starts.append(())
            region_ends.append(())
        prev_regions = new_regions

    # Drop trailing seps with no active region — they can never produce a cut.
    while len(seps_non_empty) > 1 and not region_starts[-1]:
        seps_non_empty.pop()
        region_starts.pop()
        region_ends.pop()

    n_seps = len(seps_non_empty)
    sep_lens = [len(s) for s in seps_non_empty]

    offsets: list[tuple[int, int]] = []
    offsets_append = offsets.append
    if n_seps == 0:
        base = 0
        step = chunk_size - overlap
        while True:
            target = base + chunk_size
            if target >= n:
                offsets_append((base, n))
                break
            offsets_append((base, target))
            base += step
        return offsets

    if n_seps == 1:
        sep = seps_non_empty[0]
        sep_len = sep_lens[0]
        repeat_char = sep[0] if sep_len > 1 and sep[0] == sep[1] else ""
        base = 0
        last_cut = -1
        rfind = str.rfind
        if not repeat_char:
            while True:
                target = base + chunk_size
                if target >= n:
                    offsets_append((base, n))
                    break
                lo = last_cut + 1 if last_cut >= base else base + 1
                cut = rfind(content, sep, lo, target + sep_len)
                if cut == -1:
                    cut = target
                offsets_append((base, cut))
                last_cut = cut
                base = cut - overlap if overlap > 0 and cut > overlap else cut
            return offsets

        while True:
            target = base + chunk_size
            if target >= n:
                offsets_append((base, n))
                break
            lo = last_cut + 1 if last_cut >= base else base + 1
            cut = rfind(content, sep, lo, target + sep_len)
            if cut != -1 and repeat_char:
                run_start = cut
                while run_start > 0 and content[run_start - 1] == repeat_char:
                    run_start -= 1
                cut = run_start + (cut - run_start) // sep_len * sep_len
                if cut < lo:
                    cut = -1
            if cut == -1:
                cut = target
            offsets_append((base, cut))
            last_cut = cut
            base = cut - overlap if overlap > 0 and cut > overlap else cut
        return offsets

    base = 0
    last_cut = -1
    rfind = str.rfind
    bisect = bisect_right
    repeat_chars = [s[0] if len(s) > 1 and s[0] == s[1] else "" for s in seps_non_empty]
    while True:
        target = base + chunk_size
        if target >= n:
            offsets_append((base, n))
            break
        lo = last_cut + 1 if last_cut >= base else base + 1
        cut = -1
        for sep_idx in range(n_seps):
            sep = seps_non_empty[sep_idx]
            sep_len = sep_lens[sep_idx]
            p = rfind(content, sep, lo, target + sep_len)
            if p == -1 or p <= cut:
                continue
            repeat_char = repeat_chars[sep_idx]
            if repeat_char:
                # rfind gives rightmost match; greedy str.split skips ahead by
                # sep_len after each hit, so adjust to the earliest aligned start
                # within the current run of identical chars.
                run_start = p
                while run_start > 0 and content[run_start - 1] == repeat_char:
                    run_start -= 1
                p = run_start + (p - run_start) // sep_len * sep_len
                if p < lo or p <= cut:
                    continue
            if sep_idx == 0:
                cut = p
                continue
            starts = region_starts[sep_idx]
            if not starts:
                continue
            j = bisect(starts, p) - 1
            if j >= 0 and p < region_ends[sep_idx][j]:
                cut = p
        if cut == -1:
            cut = target
        offsets_append((base, cut))
        last_cut = cut
        base = cut - overlap if overlap > 0 and cut > overlap else cut
    return offsets


def _find_oversized(
    content: str, start: int, end: int, sep: str, chunk_size: int
) -> list[tuple[int, int]]:
    """Return ranges of *sep*-bounded pieces in [start, end] exceeding chunk_size."""
    sep_len = len(sep)
    out: list[tuple[int, int]] = []
    if sep_len == 1:
        _find_oversized_single_char(content, start, end, sep, chunk_size, out)
        return out

    # Match the old split-based semantics without materializing ``content[start:end]``
    # or the full list of separator-bounded pieces.
    piece_start = start
    search_from = start
    find = str.find

    while True:
        sep_start = find(content, sep, search_from, end)
        if sep_start == -1:
            break

        piece_end = sep_start
        plen = piece_end - piece_start
        if plen > chunk_size:
            out.append((piece_start, piece_end))

        piece_start = sep_start
        search_from = sep_start + sep_len

    plen = end - piece_start
    if plen > chunk_size:
        out.append((piece_start, end))
    return out


def _find_oversized_single_char(
    content: str,
    start: int,
    end: int,
    sep: str,
    chunk_size: int,
    out: list[tuple[int, int]],
) -> None:
    """Single-character variant that skips separator hits inside small pieces."""
    piece_start = start
    search_from = start
    find = str.find
    rfind = str.rfind

    while search_from < end:
        last_safe = rfind(content, sep, search_from, min(end, piece_start + chunk_size + 1))
        if last_safe != -1:
            piece_start = last_safe
            search_from = last_safe + 1
            continue

        sep_start = find(content, sep, search_from, end)
        if sep_start == -1:
            break
        out.append((piece_start, sep_start))
        piece_start = sep_start
        search_from = sep_start + 1

    if end - piece_start > chunk_size:
        out.append((piece_start, end))


__all__ = ["DEFAULT_SEPARATORS", "recursive_text_split", "split_with_line_ranges"]
