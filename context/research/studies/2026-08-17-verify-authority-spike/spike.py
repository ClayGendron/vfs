"""Verify-authority spike: race four verify-stage strategies at linux scale.

Slice C of spec 103 rewrites grep's verify stage. The open design
question (Clay, 2026-08-17): does the verify *authority* itself move to
Rust's regex crate for the translatable pattern subset, or does Python
``re`` stay the sole authority behind a Rust literal prefilter? This
spike puts numbers on the candidate shapes over the 25 recorded
benchmark rows (93,760 files / 1.59 GB):

- **S0 current** — the live ``pattern_matching.grep.verify``: split
  every candidate body into lines, Python ``re`` per line.
- **S1 whole-text re** — Python ``re.finditer`` over the un-split body
  (``re.MULTILINE`` so ``^`` keeps the per-line law), enclosing lines
  recovered around match spans. Pure Python, authority unchanged.
- **S2 prefilter + line re** — spec 103 §3's shape in pure Python:
  ``str.find`` on the row's longest guaranteed literal (folded stream
  for case-insensitive rows), line recovery per hit, Confirmed hits
  skip ``re`` entirely, Candidate lines pass through the authority.
- **S3 Rust** (the ``rust/`` crate) — regex-crate scan over raw bytes
  with line recovery, single- and multi-threaded, plus a
  memmem-prefilter variant: the full-Rust-authority candidate.

Candidate sets are reproduced faithfully in memory rather than from a
rebuilt 5 GB store: the production planner (``build_code_gram_query``),
the production gate (``_indexable``), the production engine
(``vfs.native`` postings builder), and a replica of the ladder's
rarest-``_INTERSECT_GRAMS``/byte-budget selection, candidate cap, and
overlay-consultation rule. Known simplification: no wall-clock deadline
(no benchmark row tripped it during candidate assembly). Sanity anchors
(corpus size, overlay count, wildcard candidate count) print against
the recorded 2026-08-16 numbers.

Phases (``CACHE`` must point at a scratch dir; ``LINUX`` defaults to
``~/Git/Repos/linux``)::

    CACHE=/scratch uv run python spike.py candidates
    CACHE=/scratch RUNS=3 uv run python spike.py bench
    (cd rust && cargo run --release -- $CACHE/rust_manifest.json \
        > $CACHE/rust_results.json)

``bench`` writes ``py_results.json`` plus the rust manifest, and
cross-checks every strategy's hit counts against S0 (the authority);
divergences print loudly. Match-model construction is excluded from
S1/S2/S3 timings (it is per-hit, identical across strategies) but is
included in S0, which calls the live function unmodified.
"""

from __future__ import annotations

import json
import os
import re
import statistics
import sys
import time
from pathlib import Path as OsPath
from typing import NamedTuple

import numpy as np

from vfs.models.code_grams import GramOr, GramQuery, build_code_gram_query, fold_content
from vfs.models.postings import decode_postings
from vfs.native import active_core, folded_bytes, postings_builder
from vfs.pattern_matching import compile_verifier, verify
from vfs.storage.backends.database.grep import CANDIDATE_BUDGET, POSTING_BYTE_BUDGET, _INTERSECT_GRAMS
from vfs.storage.backends.database.indexing import _indexable

LINUX = OsPath(os.environ.get("LINUX", str(OsPath.home() / "Git/Repos/linux")))
CACHE = OsPath(os.environ["CACHE"])
RUNS = int(os.environ.get("RUNS", "3"))
FEED_BATCH = 512
DRAIN_CAP = 1 << 26

# Characters the regex crate treats as meta — its own escaping law, not
# re.escape's (which also escapes space, &, ~, # — rejected by the crate).
_RUST_META = frozenset("\\.^$|?*+()[]{}")


class SpikeQuery(NamedTuple):
    """One benchmark row plus the spike's hand-derived prefilter facts.

    ``literal`` is the longest guaranteed literal a slice-C planner
    extraction would surface (every match must contain it); ``confirmed``
    marks rows where a literal hit already decides the line (the literal
    IS the effective pattern after stripping leading/trailing ``.*``).
    ``no_newline_pattern`` respells ``\\s`` without ``\\n`` for whole-text
    scanning — the rg transform the authority's per-line law implies.
    """

    label: str
    pattern: str
    fixed: bool = False
    word: bool = False
    ci: bool = False
    literal: str | None = None
    confirmed: bool = False
    multiline: bool = False
    no_newline_pattern: str | None = None


QUERIES: tuple[SpikeQuery, ...] = (
    SpikeQuery("zero-hit", "xyzzy_no_such_symbol_42", literal="xyzzy_no_such_symbol_42", confirmed=True),
    SpikeQuery("rare literal", "randomize_kstack_offset", literal="randomize_kstack_offset", confirmed=True),
    SpikeQuery("medium literal", "raw_spin_lock_irqsave", literal="raw_spin_lock_irqsave", confirmed=True),
    SpikeQuery("medium literal 2", "napi_gro_receive", literal="napi_gro_receive", confirmed=True),
    SpikeQuery("medium literal 3", "cgroup_subsys_state", literal="cgroup_subsys_state", confirmed=True),
    SpikeQuery("hot literal", "EXPORT_SYMBOL_GPL", literal="EXPORT_SYMBOL_GPL", confirmed=True),
    SpikeQuery("hot literal 2", "kmalloc", literal="kmalloc", confirmed=True),
    SpikeQuery("ultra-hot literal", "GFP_KERNEL", literal="GFP_KERNEL", confirmed=True),
    SpikeQuery("phrase", "static int __init", literal="static int __init", confirmed=True),
    SpikeQuery("fixed string", "!= NULL", fixed=True, literal="!= NULL", confirmed=True),
    SpikeQuery("fixed string 2", "if (ret < 0)", fixed=True, literal="if (ret < 0)", confirmed=True),
    SpikeQuery("escaped call", r"mutex_lock\(&", literal="mutex_lock(&", confirmed=True),
    SpikeQuery(
        "regex classes",
        r"static\s+int\s+\w+_probe",
        literal="_probe",
        no_newline_pattern=r"static[ \t\r\f\v]+int[ \t\r\f\v]+\w+_probe",
    ),
    SpikeQuery("wrapped wildcard", ".*alloc_page.*", literal="alloc_page", confirmed=True),
    SpikeQuery("folded", "copyright", ci=True, literal="copyright", confirmed=True),
    SpikeQuery("folded 2", "deadlock", ci=True, literal="deadlock", confirmed=True),
    SpikeQuery("word", "kfree", word=True, literal="kfree"),
    SpikeQuery("word 2", "pr_debug", word=True, literal="pr_debug"),
    SpikeQuery("alternation", "TODO|FIXME"),
    SpikeQuery("factored alternation", "kzalloc|kcalloc", literal="alloc"),
    SpikeQuery("group alternation", "devm_(kzalloc|kmalloc)", literal="devm_k"),
    SpikeQuery("anchored group", "^(EXPORT_SYMBOL|MODULE_LICENSE)", multiline=True),
    SpikeQuery(
        "anchored literal", "^#include <linux/module.h>", literal="#include <linux/module.h>", multiline=True
    ),
    SpikeQuery("small class", "ext[234]", literal="ext"),
    SpikeQuery("rescued class", "-O[0-3]", literal="-O"),
)


# ---------------------------------------------------------------------------
# Corpus and candidate assembly
# ---------------------------------------------------------------------------


def load_corpus(root: OsPath) -> list[tuple[str, str]]:
    """The benchmark's corpus law: UTF-8 text files, sorted path order."""
    docs: list[tuple[str, str]] = []
    for src in sorted(root.rglob("*")):
        if ".git" in src.parts or src.is_symlink() or not src.is_file():
            continue
        data = src.read_bytes()
        try:
            text = data.decode("utf-8")
        except UnicodeDecodeError:
            continue
        docs.append((str(src.relative_to(root)), text))
    return docs


def needed_grams(plans: dict[str, GramQuery]) -> set[int]:
    """Every gram any query's ladder could price or fetch."""
    out: set[int] = set()
    for plan in plans.values():
        for node in walk_nodes(plan):
            out |= node.required_grams()
    return out


def walk_nodes(plan: GramQuery):
    """Yield the AND-shaped leaves of *plan* (OR branches recursed)."""
    if isinstance(plan, GramOr):
        for branch in plan.branches:
            yield from walk_nodes(branch)
    else:
        yield plan


def build_needed_index(docs: list[tuple[str, str]], indexed: list[int], needed: set[int]) -> dict:
    """Feed the production engine; keep (count, blob_size, ids) for needed grams."""
    builder = postings_builder()
    batch: list[tuple[int, bytes]] = []
    for doc_id in indexed:
        batch.append((doc_id, folded_bytes(docs[doc_id - 1][1])))
        if len(batch) >= FEED_BATCH:
            builder.add_docs(batch)
            batch = []
    if batch:
        builder.add_docs(batch)
    index: dict[int, tuple[int, int, np.ndarray]] = {}
    while (rows := builder.next_batch(DRAIN_CAP)) is not None:
        for gram, blob, count in rows:
            if gram in needed:
                index[gram] = (count, len(blob), decode_postings(blob))
    return index


def plan_doc_ids(plan: GramQuery, index: dict, budget: list[int]) -> np.ndarray:
    """The ladder replica: OR unions branches, AND intersects rarest grams."""
    if isinstance(plan, GramOr):
        parts = [np.empty(0, dtype=np.int64)]
        for branch in plan.branches:
            parts.append(plan_doc_ids(branch, index, budget))
        return np.unique(np.concatenate(parts))
    grams = sorted(plan.required_grams())
    metas = {gram: index[gram] for gram in grams if gram in index}
    if len(metas) < len(grams):
        return np.empty(0, dtype=np.int64)
    chosen: list[int] = []
    for gram in sorted(metas, key=lambda g: metas[g][0]):
        size = metas[gram][1]
        if chosen and (len(chosen) >= _INTERSECT_GRAMS or size > budget[0]):
            break
        chosen.append(gram)
        budget[0] -= size
    ids: np.ndarray | None = None
    for gram in chosen:
        arr = metas[gram][2]
        ids = arr if ids is None else np.intersect1d(ids, arr, assume_unique=True)
        if ids.size == 0:
            break
    return ids if ids is not None else np.empty(0, dtype=np.int64)


def candidates_phase() -> None:
    t0 = time.perf_counter()
    print(f"engine: {active_core()}; corpus: {LINUX}", flush=True)
    docs = load_corpus(LINUX)
    total_bytes = sum(len(t) for _, t in docs)
    print(f"corpus: {len(docs)} files / {total_bytes / 1e9:.2f} GB (recorded: 93,760 / 1.59 GB)", flush=True)
    indexed = [i + 1 for i, (_, text) in enumerate(docs) if _indexable(text)]
    indexed_set = set(indexed)
    overlay = [docs[i][0] for i in range(len(docs)) if i + 1 not in indexed_set]
    print(f"gate: {len(indexed)} indexed, {len(overlay)} overlay (recorded overlay: ~96 over-cap)", flush=True)
    plans = {q.label: build_code_gram_query(q.pattern, fixed_strings=q.fixed) for q in QUERIES}
    index = build_needed_index(docs, indexed, needed_grams(plans))
    print(f"index: {len(index)} needed grams priced in {time.perf_counter() - t0:.0f}s", flush=True)

    out: dict = {"root": str(LINUX), "overlay": overlay, "queries": []}
    for q in QUERIES:
        budget = [POSTING_BYTE_BUDGET]
        ids = plan_doc_ids(plans[q.label], index, budget)
        truncated = bool(ids.size > CANDIDATE_BUDGET)
        if truncated:
            ids = ids[:CANDIDATE_BUDGET]
        paths = [docs[i - 1][0] for i in ids.tolist()]
        overlay_consulted = CANDIDATE_BUDGET - len(paths) > 0
        out["queries"].append(
            {
                "label": q.label,
                "candidates": paths,
                "truncated": truncated,
                "overlay_consulted": overlay_consulted,
            }
        )
        print(f"  {q.label:<22} candidates {len(paths):>6}{'  (truncated)' if truncated else ''}", flush=True)
    CACHE.mkdir(parents=True, exist_ok=True)
    (CACHE / "candidates.json").write_text(json.dumps(out))
    print(f"candidates written in {time.perf_counter() - t0:.0f}s total", flush=True)


# ---------------------------------------------------------------------------
# Python strategies — S0 current, S1 whole-text, S2 prefilter
# ---------------------------------------------------------------------------


def s0_current(texts: list[str], verifier) -> tuple[int, int]:
    """The live verify: files-with-hits and matched-line totals."""
    files = lines = 0
    for text in texts:
        verified = verify(text, verifier, invert=False, before=0, after=0, mode="lines", cap=None)
        if verified is not None:
            files += 1
            lines += len(verified[0])
    return files, lines


def s1_whole_text(texts: list[str], rx) -> tuple[int, int]:
    """finditer over the un-split body; enclosing lines recovered per span.

    Hit lines are sliced out (the ``lines``-mode deliverable) so the
    timing is output-comparable with S0, minus Match-model construction.
    """
    files = lines = 0
    for text in texts:
        hits: list[str] = []
        last_start = -1
        for m in rx.finditer(text):
            start = text.rfind("\n", 0, m.start()) + 1
            if start == last_start:
                continue
            last_start = start
            end = text.find("\n", m.end())
            hits.append(text[start:] if end == -1 else text[start:end])
        if hits:
            files += 1
            lines += len(hits)
    return files, lines


def s2_prefilter(texts: list[str], q: SpikeQuery, verifier) -> tuple[int, int]:
    """Literal scan (folded stream when ci), authority only on candidate lines."""
    files = lines = 0
    literal = q.literal or ""
    for text in texts:
        hay = fold_content(text) if q.ci else text
        hits: list[str] = []
        pos = 0
        while (i := hay.find(literal, pos)) != -1:
            start = hay.rfind("\n", 0, i) + 1
            end = hay.find("\n", i + len(literal))
            if end == -1:
                end = len(hay)
            line = hay[start:end]
            if q.confirmed or verifier.search(line) is not None:
                hits.append(line)
            pos = end + 1
        if hits:
            files += 1
            lines += len(hits)
    return files, lines


def encode_tax(texts: list[str]) -> tuple[float, int]:
    """The str->bytes boundary cost a Rust verify pays per call."""
    t0 = time.perf_counter()
    total = 0
    for text in texts:
        total += len(text.encode("utf-8"))
    return (time.perf_counter() - t0) * 1000, total


def timed(fn, runs: int) -> tuple[float, tuple[int, int]]:
    """Median wall ms over *runs*, plus the (files, lines) counts."""
    samples = []
    counts = (0, 0)
    for _ in range(runs):
        t0 = time.perf_counter()
        counts = fn()
        samples.append((time.perf_counter() - t0) * 1000)
    return statistics.median(samples), counts


def rust_pattern(q: SpikeQuery) -> str:
    """The regex-crate spelling of the authority's compiled pattern."""
    text = "".join("\\" + ch if ch in _RUST_META else ch for ch in q.pattern) if q.fixed else q.pattern
    if q.no_newline_pattern is not None:
        text = q.no_newline_pattern.replace(r"\f", "\\x0C").replace(r"\v", "\\x0B")
    if q.word:
        text = rf"\b(?:{text})\b"
    return text


def bench_phase() -> None:
    cache = json.loads((CACHE / "candidates.json").read_text())
    root = OsPath(cache["root"])
    wanted: set[str] = set(cache["overlay"])
    for entry in cache["queries"]:
        wanted.update(entry["candidates"])
    t0 = time.perf_counter()
    contents = {path: (root / path).read_bytes().decode("utf-8") for path in sorted(wanted)}
    print(f"preload: {len(contents)} files in {time.perf_counter() - t0:.0f}s", flush=True)

    by_label = {q.label: q for q in QUERIES}
    results: dict = {}
    manifest: dict = {"root": str(root), "runs": RUNS, "queries": []}
    for entry in cache["queries"]:
        q = by_label[entry["label"]]
        paths = list(entry["candidates"])
        if entry["overlay_consulted"]:
            paths += cache["overlay"]
        texts = [contents[p] for p in paths]
        verifier = compile_verifier(
            q.pattern,
            fixed_strings=q.fixed,
            word_regexp=q.word,
            case_mode="insensitive" if q.ci else "sensitive",
        )
        s1_source = q.no_newline_pattern if q.no_newline_pattern is not None else verifier.pattern
        s1_rx = re.compile(s1_source, verifier.flags | re.MULTILINE)

        row: dict = {"candidates": len(texts)}
        ms, counts = timed(lambda t=texts, v=verifier: s0_current(t, v), RUNS)
        row["s0"] = {"ms": ms, "files": counts[0], "lines": counts[1]}
        ms, counts = timed(lambda t=texts, r=s1_rx: s1_whole_text(t, r), RUNS)
        row["s1"] = {"ms": ms, "files": counts[0], "lines": counts[1]}
        if q.literal is not None:
            ms, counts = timed(lambda t=texts, qq=q, v=verifier: s2_prefilter(t, qq, v), RUNS)
            row["s2"] = {"ms": ms, "files": counts[0], "lines": counts[1]}
        tax_ms, tax_bytes = encode_tax(texts)
        row["encode_tax"] = {"ms": tax_ms, "bytes": tax_bytes}
        results[q.label] = row
        flags = [k for k in ("s1", "s2") if k in row and (row[k]["files"], row[k]["lines"]) != (row["s0"]["files"], row["s0"]["lines"])]
        note = f"  DIVERGES: {flags}" if flags else ""
        s2_ms = f"{row['s2']['ms']:8.1f}" if "s2" in row else "       -"
        print(
            f"  {q.label:<22} n={len(texts):>6}  s0 {row['s0']['ms']:8.1f}ms  s1 {row['s1']['ms']:8.1f}ms  "
            f"s2 {s2_ms}ms  lines {row['s0']['lines']}{note}",
            flush=True,
        )
        manifest["queries"].append(
            {
                "label": q.label,
                "pattern": rust_pattern(q),
                "ci": q.ci,
                "multiline": q.multiline,
                "literal": None if q.ci else q.literal,
                "confirmed": q.confirmed,
                "files": paths,
            }
        )
    (CACHE / "py_results.json").write_text(json.dumps(results, indent=1))
    (CACHE / "rust_manifest.json").write_text(json.dumps(manifest))
    print("py_results.json and rust_manifest.json written", flush=True)


if __name__ == "__main__":
    phase = sys.argv[1] if len(sys.argv) > 1 else ""
    if phase == "candidates":
        candidates_phase()
    elif phase == "bench":
        bench_phase()
    else:
        sys.exit("usage: spike.py candidates|bench")
