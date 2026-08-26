"""Prototype: query-biased line-window preview over a chunk already in hand.

Stdlib only (plus read-only calls into the live vfs library for the fold and
the chunk splitter). Run from the repo root:

    uv run python context/research/studies/2026-08-26-glean/preview-and-snippets/preview_proto.py

Algorithm (Turpin/Tombros sentence scoring adapted to lines):
  1. Fold the query with the gram index's fold (Turkic-i pre-fold + casefold)
     and tokenize into identifier-ish terms; drop 1-char terms; dedupe.
  2. For each chunk line, build a folded copy with an index map back to the
     original string (folding can change length), find every term occurrence
     (substring), and score the line: sum over DISTINCT terms present of
     w(term) * (1.0 whole-word | 0.5 partial), + 0.25 per extra occurrence,
     capped, + a run bonus for adjacent terms. w(term) = log2(1 + len(term)).
  3. Slide a W-line window; window score = sum of line scores + a
     distinct-term coverage bonus across the window. Best window wins; ties
     go to the earliest window (Lucene's position norm, cheaper here).
  4. Bold every occurrence in the chosen lines with **...** (ranges merged,
     tantivy-style), trim each line to a char cap, cap the whole preview.
  5. No terms / no hits -> head of the chunk, W lines, same caps.
"""

from __future__ import annotations

import math
import re
import statistics
import sys
import time
from dataclasses import dataclass
from pathlib import Path as FsPath

from vfs.models.chunk import Chunk
from vfs.models.code_grams import fold_content
from vfs.paths import Path

WINDOW_LINES = 4
LINE_CHAR_CAP = 160
PREVIEW_CHAR_CAP = 480
MAX_EXTRA_OCCURRENCE_BONUS = 1.0
PARTIAL_WORD_FACTOR = 0.5
RUN_BONUS = 0.5

_TOKEN_RE = re.compile(r"[^\W_]+(?:_[^\W_]+)*|_+", re.UNICODE)
_WORD_CHAR_RE = re.compile(r"[\w]", re.UNICODE)


def query_terms(query: str) -> list[str]:
    """Folded, deduped identifier-ish terms of the query, longest first."""
    folded = fold_content(query)
    seen: dict[str, None] = {}
    for tok in re.findall(r"[^\W]+", folded):
        if len(tok) >= 2:
            seen.setdefault(tok, None)
    return sorted(seen, key=len, reverse=True)


def fold_with_map(line: str) -> tuple[str, list[int]]:
    """Folded line plus folded-index -> original-index map (length may change)."""
    if line.isascii():
        return line.lower(), list(range(len(line) + 1))
    out: list[str] = []
    idx: list[int] = []
    for i, ch in enumerate(line):
        f = fold_content(ch)
        out.append(f)
        idx.extend([i] * len(f))
    idx.append(len(line))
    return "".join(out), idx


@dataclass(slots=True)
class LineHits:
    score: float
    spans: list[tuple[int, int]]  # original-string char ranges to bold
    terms: frozenset[str]


_NO_HITS = LineHits(0.0, [], frozenset())


def score_line(line: str, folded: str, terms: list[str], weights: dict[str, float]) -> LineHits:
    """Score one line given its already-folded twin; the index map is built lazily."""
    if not line or not any(t in folded for t in terms):
        return _NO_HITS
    if line.isascii():
        imap: list[int] | range = range(len(line) + 1)
    else:
        folded, imap = fold_with_map(line)
    spans: list[tuple[int, int]] = []
    present: set[str] = set()
    score = 0.0
    positions: list[int] = []
    for term in terms:
        start = 0
        count = 0
        best = 0.0
        while True:
            at = folded.find(term, start)
            if at < 0:
                break
            end = at + len(term)
            whole = (at == 0 or not _WORD_CHAR_RE.match(folded[at - 1])) and (
                end >= len(folded) or not _WORD_CHAR_RE.match(folded[end])
            )
            best = max(best, 1.0 if whole else PARTIAL_WORD_FACTOR)
            spans.append((imap[at], imap[end]))
            positions.append(at)
            count += 1
            start = end
        if count:
            present.add(term)
            score += weights[term] * best + min(0.25 * (count - 1), MAX_EXTRA_OCCURRENCE_BONUS)
    if len(present) >= 2:
        # Run bonus: distinct terms adjacent (within 2 chars) in the folded line.
        positions.sort()
        runs = sum(1 for a, b in zip(positions, positions[1:]) if b - a <= max(len(t) for t in terms) + 2)
        score += RUN_BONUS * min(runs, len(present) - 1)
    return LineHits(score, spans, frozenset(present))


def merge_spans(spans: list[tuple[int, int]]) -> list[tuple[int, int]]:
    if not spans:
        return []
    spans = sorted(spans)
    out = [spans[0]]
    for s, e in spans[1:]:
        ps, pe = out[-1]
        if s <= pe:
            out[-1] = (ps, max(pe, e))
        else:
            out.append((s, e))
    return out


def bold(line: str, spans: list[tuple[int, int]]) -> str:
    if not spans:
        return line
    pieces: list[str] = []
    cursor = 0
    for s, e in merge_spans(spans):
        pieces.append(line[cursor:s])
        pieces.append(f"**{line[s:e]}**")
        cursor = e
    pieces.append(line[cursor:])
    return "".join(pieces)


def trim_line(rendered: str, cap: int = LINE_CHAR_CAP) -> str:
    if len(rendered) <= cap:
        return rendered
    # Keep the first bolded span in view when the line is long.
    first = rendered.find("**")
    if first > cap // 2:
        lead = max(0, first - cap // 3)
        return "…" + rendered[lead : lead + cap] + "…"
    return rendered[:cap] + "…"


@dataclass(slots=True)
class Preview:
    line_start: int  # 1-indexed, absolute in the file
    line_end: int
    text: str
    score: float
    keyword: bool  # False -> head-of-chunk fallback


def preview(chunk_text: str, chunk_line_start: int, terms: list[str], *, window: int = WINDOW_LINES) -> Preview:
    lines = chunk_text.split("\n")
    if lines and lines[-1] == "":
        lines.pop()
    if not lines:
        return Preview(chunk_line_start, chunk_line_start, "", 0.0, False)
    weights = {t: math.log2(1 + len(t)) for t in terms}
    hits: list[LineHits] = []
    # One C-level fold of the whole chunk; newlines survive folding, so the
    # folded and original line lists align. Whole-chunk miss -> head fallback.
    if terms:
        folded_all = fold_content(chunk_text)
        if any(t in folded_all for t in terms):
            folded_lines = folded_all.split("\n")
            hits = [score_line(ln, fl, terms, weights) for ln, fl in zip(lines, folded_lines)]
    best_i, best_score = 0, 0.0
    if hits:
        n = len(lines)
        w = min(window, n)
        for i in range(0, n - w + 1):
            seg = hits[i : i + w]
            s = sum(h.score for h in seg)
            if s <= 0.0:
                continue
            covered = frozenset().union(*(h.terms for h in seg))
            s += 0.5 * len(covered)
            if s > best_score:
                best_i, best_score = i, s
    keyword = best_score > 0.0
    w = min(window, len(lines))
    chosen = range(best_i, best_i + w)
    rendered: list[str] = []
    total = 0
    last = best_i
    for i in chosen:
        text = trim_line(bold(lines[i], hits[i].spans) if keyword else lines[i])
        if total + len(text) > PREVIEW_CHAR_CAP and rendered:
            break
        rendered.append(text)
        total += len(text) + 1
        last = i
    return Preview(chunk_line_start + best_i, chunk_line_start + last, "\n".join(rendered), best_score, keyword)


# ---------------------------------------------------------------------------
# Measurement
# ---------------------------------------------------------------------------


def corpus_chunks(root: FsPath, subdirs: tuple[str, ...], want: int) -> list[Chunk]:
    files: list[tuple[Path, str, str | None]] = []
    for sub in subdirs:
        for p in sorted((root / sub).rglob("*")):
            if not p.is_file() or "__pycache__" in p.parts or p.suffix in {".so", ".pyc", ".json"}:
                continue
            try:
                text = p.read_text(encoding="utf-8")
            except (UnicodeDecodeError, OSError):
                continue
            if "\x00" in text or not text.strip():
                continue
            ext = p.suffix.lstrip(".") or None
            files.append((Path("/" + p.relative_to(root).as_posix()), text, ext))
    out: list[Chunk] = []
    for group in Chunk.split_batch(files):
        out.extend(group)
    # Cycle to reach the target count if the tree is smaller than `want`.
    while len(out) < want:
        out.extend(out[: want - len(out)])
    return out[:want]


def bench(chunks: list[Chunk], query: str, reps: int = 3) -> dict[str, float]:
    terms = query_terms(query)
    best: list[float] = []
    for _ in range(reps):
        t0 = time.perf_counter()
        for c in chunks:
            preview(c.content, c.line_start, terms)
        best.append(time.perf_counter() - t0)
    total = min(best)
    return {"terms": len(terms), "total_s": total, "us_per_chunk": total / len(chunks) * 1e6}


def main() -> None:
    root = FsPath(__file__).resolve().parents[5]
    chunks = corpus_chunks(root, ("src", "context", "tests"), 10_000)
    sizes = [len(c.content) for c in chunks]
    lines = [c.line_end - c.line_start + 1 for c in chunks]
    print(f"chunks: {len(chunks)}  mean chars {statistics.mean(sizes):.0f}  median {statistics.median(sizes):.0f}  max {max(sizes)}")
    print(f"lines/chunk: mean {statistics.mean(lines):.1f}  median {statistics.median(lines):.0f}  max {max(lines)}")

    queries = {
        "1 term": "embedding",
        "3 terms": "chunk line_start embedding",
        "6 terms": "reindex lease heartbeat epoch postings publish",
        "no lexical hit (vector-only shape)": "zzqx",
        "empty (vector-only)": "",
    }
    results = {}
    for label, q in queries.items():
        r = bench(chunks, q)
        results[label] = r
        print(f"{label:38s} terms={r['terms']}  {r['us_per_chunk']:8.2f} us/chunk   10k total {r['total_s']*1000:7.1f} ms")

    # A 10-entry x 3-chunk result page.
    page = chunks[:30]
    terms = query_terms(queries["3 terms"])
    t0 = time.perf_counter()
    for _ in range(100):
        for c in page:
            preview(c.content, c.line_start, terms)
    per_page = (time.perf_counter() - t0) / 100
    print(f"10 entries x 3 chunks (30 previews, 3-term query): {per_page*1e6:.0f} us per result page")

    # Examples: pick chunks with keyword hits for the 3-term query.
    print("\n=== examples ===")
    shown = 0
    for c in chunks:
        p = preview(c.content, c.line_start, terms)
        if p.keyword and p.score > 6 and shown < 2:
            shown += 1
            print(f"\n{c.file}:{p.line_start}-{p.line_end}  (chunk {c.line_start}-{c.line_end}, score {p.score:.2f})")
            print(p.text)
    terms6 = query_terms(queries["6 terms"])
    for c in chunks:
        p = preview(c.content, c.line_start, terms6)
        if p.keyword and p.score > 12:
            print(f"\n{c.file}:{p.line_start}-{p.line_end}  (chunk {c.line_start}-{c.line_end}, score {p.score:.2f}, 6-term query)")
            print(p.text)
            break
    # A vector-only preview: head of the chunk.
    c = next(x for x in chunks if x.line_end - x.line_start >= 8)
    p = preview(c.content, c.line_start, [])
    print(f"\n{c.file}:{p.line_start}-{p.line_end}  (chunk {c.line_start}-{c.line_end}, vector-only head)")
    print(p.text)


if __name__ == "__main__":
    sys.exit(main())
