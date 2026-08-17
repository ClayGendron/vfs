"""Staged grep pipeline, dual-granularity: file-mode vs chunk-mode.

One code path; the mode object supplies the posting source, the doc-id
space, and the candidate fetch. File mode reads the live gram tables and
fetches full bodies (mirroring grep_rows stage by stage); chunk mode
reads the proto chunk-gram tables and fetches only candidate chunk rows.
Both end in the same native matcher and produce (path, line) pairs.
Ground truth: the real storage.grep on the same clone.
"""
from __future__ import annotations

import asyncio
import json
import statistics
import time
from time import monotonic

import numpy as np
from sqlalchemy import text

from vfs.models.code_grams import build_code_gram_query
from vfs.models.postings import decode_postings
from vfs.paths import normalize_ext_channel
from vfs.pattern_matching import compile_filter, compile_verifier
from vfs.results import Severity
from vfs.storage.backends.database import DatabaseStorage
from vfs.storage.backends.database.dialects import chunked, op_execution_options
from vfs.storage.backends.database.grep import (
    CANDIDATE_BUDGET,
    CONTENT_BYTE_BUDGET,
    WALL_TIME_BUDGET,
    PostingMeta,
    _choose_grams,
    _content_batches,
    _content_for_entries,
    _entries_for_docs,
    _entries_for_scan,
    _ladder_defers,
    _passes_gates,
    _plan_groups,
    _posting_blobs,
    _posting_meta,
    _pushdown_terms,
)
from vfs.storage.backends.database.indexing import current_epoch
from vfs.storage.backends.database.pathterms import allow_list_ids, compile_channel
from vfs.storage.backends.database.reads import effective_columns

STORE = "linux-chunk.sqlite"
RUNS = 5

# (key, pattern, kwargs) — 12 scoped rows + 5 unscoped ladder rows.
ROWS = [
    ("scoped-01 EXPORT_SYMBOL_GPL @ drivers/**", "EXPORT_SYMBOL_GPL", {"globs": ("drivers/**",)}),
    ("scoped-02 kzalloc @ drivers/net/**", "kzalloc", {"globs": ("drivers/net/**",)}),
    ("scoped-03 mutex_lock @ drivers/gpu/drm/**", "mutex_lock", {"globs": ("drivers/gpu/drm/**",)}),
    ("scoped-04 copyright -i @ fs/ext4/**", "copyright", {"globs": ("fs/ext4/**",), "case_mode": "insensitive"}),
    ("scoped-05 napi_gro_receive @ drivers/net/**", "napi_gro_receive", {"globs": ("drivers/net/**",)}),
    ("scoped-06 GFP_KERNEL @ mm/**", "GFP_KERNEL", {"globs": ("mm/**",)}),
    ("scoped-07 cgroup_subsys_state ext=h", "cgroup_subsys_state", {"ext": ("h",)}),
    ("scoped-08 cgroup_subsys_state @ *.h", "cgroup_subsys_state", {"globs": ("*.h",)}),
    ("scoped-09 spin_lock @ kernel/**/*.c", "spin_lock", {"globs": ("kernel/**/*.c",)}),
    ("scoped-10 napi_gro_receive NOT drivers/**", "napi_gro_receive", {"globs_not": ("drivers/**",)}),
    ("scoped-11 probe @ spi-*.c", "probe", {"globs": ("spi-*.c",)}),
    ("scoped-12 obj- @ Makefile", "obj-", {"globs": ("Makefile",)}),
    ("unscoped copyright -i", "copyright", {"case_mode": "insensitive"}),
    ("unscoped EXPORT_SYMBOL_GPL", "EXPORT_SYMBOL_GPL", {}),
    ("unscoped kfree -w", "kfree", {"word_regexp": True}),
    ("unscoped randomize_kstack_offset", "randomize_kstack_offset", {}),
    ("unscoped xyzzy_no_such_symbol_42", "xyzzy_no_such_symbol_42", {}),
]


def timed(times, stage):
    class _T:
        def __enter__(self):
            self.t0 = time.perf_counter()
        def __exit__(self, *a):
            times[stage] = times.get(stage, 0.0) + (time.perf_counter() - self.t0)
    return _T()


async def _sql_rows(session, sql):
    return (await session.execute(text(sql))).all()


class FileMode:
    name = "file"

    def __init__(self, host, epoch):
        self.host = host
        self.epoch = epoch

    async def posting_meta(self, session, grams):
        return await _posting_meta(session, self.host.tables, self.host.membership_budget, self.epoch, grams)

    async def posting_blobs(self, session, grams):
        return await _posting_blobs(session, self.host.tables, self.host.membership_budget, self.epoch, grams)

    async def docs_for_entries(self, session, entry_sids):
        return np.asarray(entry_sids, dtype=np.int64)


class ChunkMode:
    name = "chunk"

    def __init__(self, host):
        self.host = host

    async def posting_meta(self, session, grams):
        meta = {}
        for chunk in chunked(list(grams), self.host.membership_budget):
            keys = ",".join(str(int(g)) for g in chunk)
            for gram, dc, bs in await _sql_rows(
                session, f"select gram_key, doc_count, byte_size from proto_chunk_postings where gram_key in ({keys})"
            ):
                meta[gram] = PostingMeta(dc, bs)
        return meta

    async def posting_blobs(self, session, grams):
        blobs = {}
        for chunk in chunked(list(grams), self.host.membership_budget):
            keys = ",".join(str(int(g)) for g in chunk)
            for gram, blob in await _sql_rows(
                session, f"select gram_key, postings from proto_chunk_postings where gram_key in ({keys})"
            ):
                blobs[gram] = blob
        return blobs

    async def docs_for_entries(self, session, entry_sids):
        parts = [np.empty(0, dtype=np.int64)]
        for chunk in chunked(list(entry_sids), self.host.membership_budget):
            keys = ",".join(str(int(s)) for s in chunk)
            for lo, hi in await _sql_rows(
                session, f"select doc_lo, doc_hi from proto_entry_intervals where entry_sid in ({keys})"
            ):
                parts.append(np.arange(lo, hi + 1, dtype=np.int64))
        return np.sort(np.concatenate(parts))


async def staged_run(host, mode, pattern, kwargs, budget, *, overlay=True):
    """One staged pipeline run. Returns (times, metrics, pairs:set[(path,line)])."""
    globs = kwargs.get("globs", ())
    globs_not = kwargs.get("globs_not", ())
    ext = kwargs.get("ext", ())
    case_mode = kwargs.get("case_mode", "sensitive")
    word_regexp = kwargs.get("word_regexp", False)
    tables, profile = host.tables, host.profile
    pbudget, mbudget = host.parameter_budget, host.membership_budget
    times: dict[str, float] = {}
    m: dict[str, object] = {"mode": mode.name, "budget": budget}

    t0 = time.perf_counter()
    async with host.session_factory() as session:
        if opts := op_execution_options(profile, writer=False):
            await session.connection(execution_options=opts)
        times["session_open"] = time.perf_counter() - t0

        with timed(times, "compile"):
            verifier = compile_verifier(pattern, fixed_strings=False, word_regexp=word_regexp, case_mode=case_mode)
            plan = build_code_gram_query(pattern, fixed_strings=False)
            admissions = list(dict.fromkeys(globs))
            exclusions = list(dict.fromkeys(globs_not))
            gates = [compile_filter(g, ()) for g in admissions]
            not_gates = [compile_filter(g, ()) for g in exclusions]
            wanted = normalize_ext_channel(ext)
            unwanted = normalize_ext_channel(())
            channel = compile_channel(admissions)
            gated = bool(gates or not_gates or wanted or unwanted)
            fetched = effective_columns(None, content=False)
        deadline = monotonic() + WALL_TIME_BUDGET

        with timed(times, "epoch_read"):
            epoch = await current_epoch(session, tables)

        with timed(times, "allow_list"):
            allow = await allow_list_ids(session, tables, mbudget, channel)
        m["allow_entries"] = None if allow is None else len(allow)

        # --- ladder (posting meta -> rarest-first choice -> blobs -> intersect)
        truncations = []
        deferred = False
        posting_bytes = 0
        if allow is not None and not allow:
            doc_ids = np.empty(0, dtype=np.int64)
        else:
            with timed(times, "posting_meta"):
                groups = _plan_groups(plan)
                grams = sorted({g for gr in groups for g in gr})
                meta = await mode.posting_meta(session, grams)
                chosen = _choose_grams(groups, meta)
            deferred = allow is not None and _ladder_defers(chosen, meta, len(allow))
            if deferred:
                with timed(times, "allow_map"):
                    doc_ids = await mode.docs_for_entries(session, allow)
            else:
                with timed(times, "posting_blobs"):
                    wanted_grams = sorted({g for gc in chosen if gc for g in gc})
                    blobs = await mode.posting_blobs(session, wanted_grams)
                    posting_bytes = sum(len(b) for b in blobs.values())
                with timed(times, "decode_intersect"):
                    parts = [np.empty(0, dtype=np.int64)]
                    for gc in chosen:
                        if not gc:
                            continue
                        ids = None
                        for gram in gc:
                            decoded = decode_postings(blobs[gram])
                            ids = decoded if ids is None else np.intersect1d(ids, decoded, assume_unique=True)
                            if ids.size == 0:
                                break
                        if ids is not None:
                            parts.append(ids)
                    doc_ids = np.unique(np.concatenate(parts))
                if allow is not None:
                    with timed(times, "allow_map"):
                        allow_docs = await mode.docs_for_entries(session, allow)
                    with timed(times, "allow_intersect"):
                        doc_ids = np.intersect1d(doc_ids, allow_docs, assume_unique=True)
        m["deferred"] = deferred
        m["posting_bytes"] = posting_bytes
        m["laddered_docs"] = int(doc_ids.size)

        if budget is not None and doc_ids.size > budget:
            doc_ids = doc_ids[:budget]
            truncations.append("candidate budget")
        m["budgeted_docs"] = int(doc_ids.size)

        # --- doc ids -> candidate entries (+ chunk map in chunk mode)
        chunk_map = None
        if mode.name == "chunk":
            with timed(times, "chunk_map"):
                chunk_map = []
                for chunk in chunked(doc_ids.tolist(), mbudget):
                    keys = ",".join(str(int(d)) for d in chunk)
                    chunk_map.extend(await _sql_rows(
                        session,
                        "select doc_id, chunk_rowid, entry_sid, path, line_start, nbytes "
                        f"from proto_chunk_map where doc_id in ({keys})",
                    ))
                entry_docs = np.asarray(sorted({r[2] for r in chunk_map}), dtype=np.int64)
        else:
            entry_docs = doc_ids
        m["candidate_entries"] = int(entry_docs.size)

        with timed(times, "entries_fetch"):
            pushdown = _pushdown_terms(tables.entry, profile, mbudget, channel, wanted, hide_meta=not gates)
            entry_rows = await _entries_for_docs(session, tables, mbudget, entry_docs, fetched, pushdown)
        with timed(times, "gate"):
            candidates = {}
            for mapping in entry_rows:
                if not gated or _passes_gates(mapping, gates, not_gates, wanted, unwanted):
                    candidates[mapping["path"]] = mapping
        m["gated_entries"] = len(candidates)

        # --- content fetch + verify
        pairs: set[tuple[str, int]] = set()
        fetch_units = 0
        fetch_bytes = 0
        if mode.name == "chunk":
            surviving = [r for r in chunk_map if r[3] in candidates]
            surviving.sort(key=lambda r: (r[3], r[0]))
            batch, total = [], 0
            batches = []
            for r in surviving:
                if batch and total + r[5] > CONTENT_BYTE_BUDGET:
                    batches.append(batch)
                    batch, total = [], 0
                batch.append(r)
                total += r[5]
            if batch:
                batches.append(batch)
            for batch in batches:
                if monotonic() > deadline:
                    truncations.append("wall-time budget")
                    break
                with timed(times, "content_fetch"):
                    contents = {}
                    for chunk in chunked([r[1] for r in batch], mbudget):
                        keys = ",".join(str(int(c)) for c in chunk)
                        contents.update({
                            rowid: body
                            for rowid, body in await _sql_rows(
                                session, f"select id, content from vfs_chunks where id in ({keys})"
                            )
                        })
                paired = [(r, contents[r[1]]) for r in batch if r[1] in contents]
                fetch_units += len(paired)
                fetch_bytes += sum(r[5] for r, _ in paired)
                texts = [t for _, t in paired]
                with timed(times, "verify"):
                    spans, completed = verifier.hit_lines(
                        texts, before=0, after=0, cap=None, invert=False,
                        budget=max(0.0, deadline - monotonic()),
                    )
                with timed(times, "collect"):
                    for (r, _), row in zip(paired, spans, strict=True):
                        for _s, _e, hit, _ctx in row:
                            pairs.add((r[3], r[4] + hit - 1))
                if not completed:
                    truncations.append("wall-time budget")
                    break
        else:
            ordered = [candidates[p] for p in sorted(candidates)]
            for batch in _content_batches(ordered):
                if monotonic() > deadline:
                    truncations.append("wall-time budget")
                    break
                with timed(times, "content_fetch"):
                    contents = await _content_for_entries(session, tables, mbudget, [x["entry_id"] for x in batch])
                paired = [(x, t) for x in batch if (t := contents.get(x["entry_id"])) is not None]
                fetch_units += len(paired)
                fetch_bytes += sum(x["size_bytes"] or 0 for x, _ in paired)
                texts = [t for _, t in paired]
                with timed(times, "verify"):
                    spans, completed = verifier.hit_lines(
                        texts, before=0, after=0, cap=None, invert=False,
                        budget=max(0.0, deadline - monotonic()),
                    )
                with timed(times, "collect"):
                    for (x, _), row in zip(paired, spans, strict=True):
                        for _s, _e, hit, _ctx in row:
                            pairs.add((x["path"], hit))
                if not completed:
                    truncations.append("wall-time budget")
                    break
        m["fetch_units"] = fetch_units
        m["fetch_bytes"] = fetch_bytes

        # --- scan overlay (NOT-encoded entries; file-shaped in both modes)
        scan_units = scan_bytes = 0
        cand_count = m["budgeted_docs"] if mode.name == "chunk" else len(candidates)
        if overlay and (not truncations or truncations == ["candidate budget"]):
            remaining = (budget if budget is not None else CANDIDATE_BUDGET) - cand_count
            if remaining > 0:
                with timed(times, "scan_overlay"):
                    nominated, _overflow = await _entries_for_scan(
                        session, tables, profile, pbudget, mbudget, gates, wanted,
                        everything=False, fetched=fetched, limit=remaining, deadline=deadline,
                    )
                    scanned = [
                        x for x in nominated
                        if (not gated or _passes_gates(x, gates, not_gates, wanted, unwanted))
                        and x["path"] not in candidates
                    ]
                    for batch in _content_batches(scanned):
                        contents = await _content_for_entries(
                            session, tables, mbudget, [x["entry_id"] for x in batch]
                        )
                        paired = [(x, t) for x in batch if (t := contents.get(x["entry_id"])) is not None]
                        scan_units += len(paired)
                        scan_bytes += sum(x["size_bytes"] or 0 for x, _ in paired)
                        spans, _c = verifier.hit_lines(
                            [t for _, t in paired], before=0, after=0, cap=None, invert=False,
                            budget=max(0.0, deadline - monotonic()),
                        )
                        for (x, _), row in zip(paired, spans, strict=True):
                            for _s, _e, hit, _ctx in row:
                                pairs.add((x["path"], hit))
        m["scan_units"] = scan_units
        m["scan_bytes"] = scan_bytes
        m["truncations"] = truncations
    return times, m, pairs


async def real_grep(storage, pattern, kwargs):
    times = []
    pairs = set()
    truncated = False
    for _ in range(RUNS):
        t0 = time.perf_counter()
        result = await storage.grep(pattern=pattern, **kwargs)
        times.append((time.perf_counter() - t0) * 1000)
        assert result.success is True, (pattern, result.errors)
        pairs = {(str(o.path), mt.start) for o in result.observations for mt in (o.matches or ())}
        truncated = any(e.severity is Severity.warning for e in result.errors)
    return statistics.median(times), pairs, truncated


async def measure(host, mode, pattern, kwargs, budget):
    runs = []
    metrics = {}
    pairs = set()
    for _ in range(RUNS):
        times, metrics, pairs = await staged_run(host, mode, pattern, kwargs, budget)
        runs.append(times)
    stages = sorted({s for r in runs for s in r})
    med = {s: statistics.median([r.get(s, 0.0) * 1000 for r in runs]) for s in stages}
    total = statistics.median([sum(r.values()) * 1000 for r in runs])
    return {"total_ms": total, "stages_ms": med, "metrics": metrics, "n_pairs": len(pairs)}, pairs


async def main():
    storage = DatabaseStorage(url=f"sqlite+aiosqlite:///{STORE}")
    refusal = await storage._host.ensure_ready()
    assert refusal is None, refusal
    host = storage._host
    await storage.grep(pattern="kzalloc", globs=("drivers/net/**",))  # warm-up

    async with host.session_factory() as session:
        epoch = await current_epoch(session, host.tables)
    fmode = FileMode(host, epoch)
    cmode = ChunkMode(host)

    out = []
    for key, pattern, kwargs in ROWS:
        real_ms, real_pairs, real_trunc = await real_grep(storage, pattern, kwargs)
        f_res, f_pairs = await measure(host, fmode, pattern, kwargs, CANDIDATE_BUDGET)
        c25_res, c25_pairs = await measure(host, cmode, pattern, kwargs, CANDIDATE_BUDGET)
        cun_res, cun_pairs = await measure(host, cmode, pattern, kwargs, None)
        row = {
            "key": key, "pattern": pattern, "kwargs": {k: list(v) if isinstance(v, tuple) else v for k, v in kwargs.items()},
            "real_ms": real_ms, "real_lines": len(real_pairs), "real_truncated": real_trunc,
            "file": f_res, "chunk_25k": c25_res, "chunk_unbounded": cun_res,
            "recall": {
                "file_vs_real": sorted_diff(f_pairs, real_pairs),
                "chunk25_vs_real": sorted_diff(c25_pairs, real_pairs),
                "chunkun_vs_real": sorted_diff(cun_pairs, real_pairs),
                "chunkun_vs_file": sorted_diff(cun_pairs, f_pairs),
            },
        }
        out.append(row)
        speed = f_res["total_ms"] / cun_res["total_ms"] if cun_res["total_ms"] else float("inf")
        print(
            f"{key:44s} real {real_ms:7.1f}  file {f_res['total_ms']:7.1f}  "
            f"chunk25 {c25_res['total_ms']:7.1f}  chunkUn {cun_res['total_ms']:7.1f}  "
            f"x{speed:5.2f}  lines r/f/c25/cU {len(real_pairs)}/{len(f_pairs)}/{len(c25_pairs)}/{len(cun_pairs)}",
            flush=True,
        )
    json.dump(out, open("results.json", "w"), indent=2)
    print("written results.json")
    await storage.close()


def sorted_diff(a, b):
    return {
        "equal": a == b,
        "only_a": sorted(a - b)[:20],
        "only_b": sorted(b - a)[:20],
        "n_only_a": len(a - b),
        "n_only_b": len(b - a),
    }


if __name__ == "__main__":
    asyncio.run(main())
