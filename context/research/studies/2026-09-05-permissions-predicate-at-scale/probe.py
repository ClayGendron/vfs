"""The permissions-predicate probe: every shape in the brief on one engine.

    uv run --no-sync python probe.py --engine sqlite --files 75000
    uv run --no-sync python probe.py --engine postgres --files 800000 --reps 3

Loads the deterministic corpus into a fresh `vfs_s1_<hex>` namespace,
measures the read predicate under four query shapes (listing, glob,
grep, ranked join-back), the write point check, the materialised
visibility table, the groups encodings and the subject-set predicate,
then writes `runs/<engine>-<rows>.md` and `.json` and drops every table.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import random
import statistics
import time
from typing import Any

from vfs.storage.backends.database.dialects import chunked

import corpus as C
from common import Bench, Timing

HERE = os.path.dirname(os.path.abspath(__file__))
GREP_LO, GREP_HI = 3000, 4000


class Pred:
    """A compiled predicate fragment over alias *e*: sql, params, bind count."""

    def __init__(self, sql: str, params: dict[str, Any], label: str) -> None:
        self.sql, self.params, self.label = sql, params, label

    @property
    def binds(self) -> int:
        return len(self.params)


def p_none() -> Pred:
    return Pred("1 = 1", {}, "none")


def p_exists(b: Bench, p: str, table: str = "grant", e: str = "e", tag: str = "p") -> Pred:
    g = b.t[table].name
    return Pred(
        f"({e}.owner_id = {b.sbind(tag)} OR EXISTS (SELECT 1 FROM {g} g WHERE g.principal_id = {b.sbind(tag)} "
        f"AND ({e}.path = g.path_prefix OR {e}.path LIKE {b.concat('g.path_prefix', chr(39) + '/%' + chr(39))})))",
        {tag: p},
        "exists" if table == "grant" else f"exists[{table}]",
    )


def cover_like(b: Bench, prefixes: list[str], tag: str, e: str = "e") -> tuple[str, dict[str, Any]]:
    arms, params = [], {}
    for i, pf in enumerate(prefixes):
        params[f"{tag}q{i}"] = pf
        params[f"{tag}l{i}"] = pf + "/%"
        arms.append(f"{e}.path = {b.pbind(f'{tag}q{i}')} OR {e}.path LIKE {b.pbind(f'{tag}l{i}')}")
    return ("(" + " OR ".join(arms) + ")") if arms else "1 = 0", params


def cover_range(b: Bench, prefixes: list[str], tag: str, e: str = "e") -> tuple[str, dict[str, Any]]:
    arms, params = [], {}
    for i, pf in enumerate(prefixes):
        params[f"{tag}q{i}"], params[f"{tag}s{i}"], params[f"{tag}z{i}"] = pf, pf + "/", pf + "0"
        arms.append(f"{e}.path = {b.pbind(f'{tag}q{i}')} OR ({e}.path >= {b.pbind(f'{tag}s{i}')} AND {e}.path < {b.pbind(f'{tag}z{i}')})")
    return ("(" + " OR ".join(arms) + ")") if arms else "1 = 0", params


def p_literal(b: Bench, corpus: C.Corpus, p: str, form: str) -> Pred:
    prefixes = C.minimise(corpus.prefixes_of(p))
    sql, params = (cover_like if form == "like" else cover_range)(b, prefixes, "a")
    params["p"] = p
    return Pred(f"(e.owner_id = {b.sbind('p')} OR {sql})", params, f"literal_{form}[{len(prefixes)} prefixes]")


def p_vis(b: Bench, p: str) -> Pred:
    v = b.t["vis"].name
    return Pred(f"(e.owner_id = {b.sbind('p')} OR EXISTS (SELECT 1 FROM {v} v WHERE v.principal_id = {b.sbind('p')} AND v.entry_id = e.id))", {"p": p}, "materialised")


def p_groups_sub(b: Bench, p: str) -> Pred:
    g, m = b.t["grantg"].name, b.t["member"].name
    return Pred(
        f"(e.owner_id = {b.sbind('p')} OR EXISTS (SELECT 1 FROM {g} g WHERE (g.principal_id = {b.sbind('p')} OR g.principal_id IN "
        f"(SELECT m.group_id FROM {m} m WHERE m.principal_id = {b.sbind('p')})) "
        f"AND (e.path = g.path_prefix OR e.path LIKE {b.concat('g.path_prefix', chr(39) + '/%' + chr(39))})))",
        {"p": p},
        "groups_subquery",
    )


def p_groups_literal(b: Bench, corpus: C.Corpus, p: str) -> Pred:
    g = b.t["grantg"].name
    ids = [p, *corpus.groups_of[p]]
    params = {f"g{i}": x for i, x in enumerate(ids)}
    params["p"] = p
    lst = ", ".join(b.sbind(f"g{i}") for i in range(len(ids)))
    return Pred(
        f"(e.owner_id = {b.sbind('p')} OR EXISTS (SELECT 1 FROM {g} g WHERE g.principal_id IN ({lst}) "
        f"AND (e.path = g.path_prefix OR e.path LIKE {b.concat('g.path_prefix', chr(39) + '/%' + chr(39))})))",
        params,
        f"groups_literal[{len(ids)} ids]",
    )


def p_set_and(b: Bench, members: list[str]) -> Pred:
    parts, params = [], {}
    for i, p in enumerate(members):
        pr = p_exists(b, p, tag=f"s{i}")
        parts.append(pr.sql)
        params.update(pr.params)
    return Pred("(" + " AND ".join(parts) + ")", params, f"set_and_exists[n={len(members)}]")


def p_set_having(b: Bench, members: list[str], filt_tpl: str, filt_params: dict[str, Any]) -> Pred:
    """The grouped form, scoped by the same filter (its binds duplicated per copy)."""
    en, g = b.t["entry"].name, b.t["grant"].name
    params = {f"s{i}": p for i, p in enumerate(members)}
    lst = ", ".join(b.sbind(f"s{i}") for i in range(len(members)))
    f2 = filt_tpl.format(e="e2")
    f3 = filt_tpl.format(e="e3")
    for k, v in filt_params.items():
        params[k] = v
    params["n"] = len(members)
    return Pred(
        f"e.id IN (SELECT x.eid FROM (SELECT e2.id AS eid, g.principal_id AS pid FROM {en} e2 JOIN {g} g ON g.principal_id IN ({lst}) "
        f"AND (e2.path = g.path_prefix OR e2.path LIKE {b.concat('g.path_prefix', chr(39) + '/%' + chr(39))}) WHERE {f2} "
        f"UNION SELECT e3.id AS eid, e3.owner_id AS pid FROM {en} e3 WHERE e3.owner_id IN ({lst}) AND {f3}) x "
        f"GROUP BY x.eid HAVING COUNT(DISTINCT x.pid) = :n)",
        params,
        f"set_having[n={len(members)}]",
    )


def p_set_app(b: Bench, corpus: C.Corpus, members: list[str]) -> Pred:
    """App-side intersection of covering prefix sets, shipped as literals (owner disjuncts included)."""
    sets = [C.minimise(corpus.prefixes_of(p)) for p in members]
    inter_all = sets[0]
    for s in sets[1:]:
        inter_all = C.intersect_prefixes(inter_all, s)
    sql_all, params = cover_like(b, inter_all, "i")
    parts = [sql_all]
    for i, p in enumerate(members):
        rest = None
        for j, s in enumerate(sets):
            if j != i:
                rest = s if rest is None else C.intersect_prefixes(rest, s)
        sql_i, prm = cover_like(b, rest or [], f"o{i}")
        params.update(prm)
        params[f"s{i}"] = p
        parts.append(f"(e.owner_id = {b.sbind(f's{i}')} AND {sql_i})")
    return Pred("(" + " OR ".join(parts) + ")", params, f"set_app_prefixes[n={len(members)}, {len(inter_all)} shared]")


# ---------------------------------------------------------------------------
# Filters (the query shapes the predicate rides on)
# ---------------------------------------------------------------------------


def filters(b: Bench, corpus: C.Corpus, rng: random.Random) -> dict[str, tuple[str, dict[str, Any]]]:
    from collections import Counter

    children = Counter(e[1].rsplit("/", 1)[0] for e in corpus.entries)
    list_dir = children.most_common(1)[0][0]
    return {
        "list": (
            "{e}.path LIKE " + b.pbind("f_l") + " AND {e}.path NOT LIKE " + b.pbind("f_ll") + " AND {e}.deleted_at IS NULL",
            {"f_l": list_dir + "/%", "f_ll": list_dir + "/%/%"},
        ),
        "glob": (
            "{e}.ext = :f_x AND {e}.kind = :f_k AND {e}.path LIKE " + b.pbind("f_g") + " AND {e}.deleted_at IS NULL",
            {"f_x": "md", "f_k": "file", "f_g": "/t000/%"},
        ),
        "grep": (
            "{e}.kind = :f_k AND {e}.size_bytes BETWEEN :f_lo AND :f_hi AND {e}.deleted_at IS NULL",
            {"f_k": "file", "f_lo": GREP_LO, "f_hi": GREP_HI},
        ),
    }


def select(b: Bench, filt: str, pred: Pred) -> str:
    return f"SELECT e.id FROM {b.t['entry'].name} e WHERE {filt} AND {pred.sql}"


def joinback(b: Bench, ids: list[int], pred: Pred, form: str, copies: int = 1) -> tuple[list[tuple[str, dict[str, Any]]], int]:
    """Chunked join-back statements for candidate *ids*: (statements, chunk size)."""
    budget = min(b.membership_budget, (b.parameter_budget - 32 - pred.binds) // copies)
    stmts = []
    for chunk in chunked(ids, budget):
        params = {f"c{i}": v for i, v in enumerate(chunk)}
        params.update(pred.params)
        if form == "in":
            lst = ", ".join(f":c{i}" for i in range(len(chunk)))
            sql = f"SELECT e.id FROM {b.t['entry'].name} e WHERE e.id IN ({lst}) AND {pred.sql}"
        else:
            vt = b.values_table(len(chunk), "c")
            if vt is None:
                return [], budget
            frag, col = vt
            sql = f"SELECT e.id FROM {frag} JOIN {b.t['entry'].name} e ON e.id = {col} WHERE {pred.sql}"
        stmts.append((sql, params))
    return stmts, budget


# ---------------------------------------------------------------------------
# The run
# ---------------------------------------------------------------------------


def md_table(headers: list[str], rows: list[list[str]]) -> str:
    out = ["| " + " | ".join(headers) + " |", "|" + "|".join("---" for _ in headers) + "|"]
    out += ["| " + " | ".join(r) + " |" for r in rows]
    return "\n".join(out)


def cell(t: Timing | None) -> str:
    if t is None:
        return "n/a"
    s = f"{t.median_ms:.1f}"
    if t.statements != 1:
        s += f" ({t.statements} stmts)"
    if t.note:
        s += f" [{t.note}]"
    return s


async def run(engine: str, n_files: int, reps: int, plans: bool) -> None:
    t_all = time.perf_counter()
    corpus = C.build(n_files)
    rng = random.Random(7)
    n_rows = len(corpus.entries)
    owners = corpus.owner_rows
    grants_per = {}
    for p, _, _ in corpus.grant_flat:
        grants_per[p] = grants_per.get(p, 0) + 1
    typ = sorted(p for p, k in owners.items() if 100 <= k <= 400 and grants_per.get(p, 0) >= 8)[0]
    heavy = "p00000"
    non_owners = [p for p in corpus.principals if p not in owners]
    sets = {n: rng.sample(non_owners, n) for n in (2, 5, 20)}
    vis_principals = [typ, heavy]
    file_ids = [e[0] for e in corpus.entries if e[3] == "file"]
    cands = {k: sorted(rng.sample(file_ids, k)) for k in (256, 1000, 3000)}
    out: dict[str, Any] = {"engine": engine, "rows": n_rows, "files": n_files, "reps": reps}
    md: list[str] = []

    async with Bench(engine, HERE) as b:
        md.append(f"## {engine} — {n_rows:,} entry rows ({n_files:,} files, {n_rows - n_files:,} directories)\n")
        md.append(
            f"Dialect `{b.dialect.name}`: parameter budget {b.parameter_budget}, in-list budget {b.profile.in_list_budget}, "
            f"membership budget {b.membership_budget}. Grants: flat {len(corpus.grant_flat):,} rows "
            f"({len(corpus.grant_flat) / C.PRINCIPALS:.1f} per principal), groups form {len(corpus.grant_g):,} grant rows + "
            f"{len(corpus.member):,} memberships, groups expanded {len(corpus.grant_gx):,} rows. "
            f"Typical principal `{typ}` owns {owners[typ]} rows, {grants_per[typ]} grants, {len(C.minimise(corpus.prefixes_of(typ)))} minimal prefixes, "
            f"{corpus.visible_count(typ):,} rows visible by grant. Heavy principal `{heavy}` owns {owners[heavy]:,} rows. "
            f"Median over {reps} warm runs, ms, rows fetched to the client.\n"
        )
        print(f"[{engine}] loading {n_rows:,} rows into {b.ns} ...", flush=True)
        load = await b.load(corpus, vis_principals)
        out["load"] = load
        md.append("Load: " + ", ".join(f"{k} {v:.1f}s" if isinstance(v, float) else f"{k} {v:,}" for k, v in load.items()) + "\n")
        print(f"[{engine}] loaded: {load}", flush=True)

        F = filters(b, corpus, rng)
        res: dict[str, Any] = {}

        # -- 1. the read predicate on list / glob / grep, four predicate shapes
        preds = {
            "none": p_none(),
            "exists": p_exists(b, typ),
            "literal_like": p_literal(b, corpus, typ, "like"),
            "literal_range": p_literal(b, corpus, typ, "range"),
            "materialised": p_vis(b, typ),
        }
        rows_md = []
        for fname, (tpl, fp) in F.items():
            row = [fname]
            for pname, pr in preds.items():
                sql = select(b, tpl.format(e="e"), pr)
                t = await b.timeit(sql, {**fp, **pr.params}, reps)
                res[f"read/{fname}/{pname}"] = t.__dict__
                row.append(cell(t) + f" · {t.rows}r")
                print(f"[{engine}] read {fname:5s} {pname:14s} {t}", flush=True)
            rows_md.append(row)
        md.append("### 1(a-c). Read predicate on list / glob / grep (typical principal)\n")
        md.append(md_table(["filter", *[f"{k} ({p.binds} binds)" for k, p in preds.items()]], rows_md) + "\n")

        # heavy principal: exists only, on grep and list
        rows_md = []
        for fname in ("list", "grep"):
            tpl, fp = F[fname]
            row = [fname]
            for pname, pr in (("none", p_none()), ("exists", p_exists(b, heavy)), ("materialised", p_vis(b, heavy))):
                t = await b.timeit(select(b, tpl.format(e="e"), pr), {**fp, **pr.params}, reps)
                res[f"heavy/{fname}/{pname}"] = t.__dict__
                row.append(cell(t) + f" · {t.rows}r")
            rows_md.append(row)
        md.append(f"Heavy principal `{heavy}` ({owners[heavy]:,} owned rows):\n")
        md.append(md_table(["filter", "none", "exists", "materialised"], rows_md) + "\n")

        # -- 1(d). ranked join-back
        rows_md = []
        for k, ids in cands.items():
            for form in ("in", "values"):
                row = [f"K={k} {form.upper()}"]
                for pname, pr in (("none", p_none()), ("exists", p_exists(b, typ)), ("literal_like", preds["literal_like"]), ("materialised", p_vis(b, typ))):
                    stmts, budget = joinback(b, ids, pr, form)
                    if not stmts:
                        row.append("unsupported")
                        continue
                    t = await b.timeit(stmts, reps=reps)
                    res[f"back/{k}/{form}/{pname}"] = {**t.__dict__, "chunk": budget}
                    row.append(cell(t) + f" · {t.rows}r")
                    print(f"[{engine}] back K={k} {form} {pname:14s} {t}", flush=True)
                rows_md.append(row)
        md.append("### 1(d). Ranked join-back: candidate ids filtered by the predicate, chunked by the membership budget\n")
        md.append(md_table(["candidates / form", "none", "exists", "literal_like", "materialised"], rows_md) + "\n")

        # -- 2. write point check
        g = b.t["grant"].name
        paths = [e[1] for e in corpus.entries if e[3] == "file"]
        check_paths = rng.sample(paths, min(10_000, len(paths)))
        singles = []
        for pth in check_paths[:200]:
            anc = C.ancestors(pth)
            params = {f"a{i}": a for i, a in enumerate(anc)}
            params["p"] = typ
            lst = ", ".join(b.pbind(f"a{i}") for i in range(len(anc)))
            t0 = time.perf_counter()
            r = await b.conn.execute(__import__("sqlalchemy").text(f"SELECT path_prefix, lvl FROM {g} WHERE principal_id = {b.sbind('p')} AND path_prefix IN ({lst})"), params)
            r.fetchall()
            singles.append((time.perf_counter() - t0) * 1000)
        await b.conn.rollback()
        single_med = statistics.median(singles)
        all_anc = sorted({a for pth in check_paths for a in C.ancestors(pth)})
        stmts = []
        for chunk in chunked(all_anc, b.membership_budget):
            params = {f"a{i}": a for i, a in enumerate(chunk)}
            params["p"] = typ
            lst = ", ".join(b.pbind(f"a{i}") for i in range(len(chunk)))
            stmts.append((f"SELECT path_prefix, lvl FROM {g} WHERE principal_id = {b.sbind('p')} AND path_prefix IN ({lst})", params))
        t_batch = await b.timeit(stmts, reps=reps)
        t_grants = await b.timeit(f"SELECT path_prefix, lvl FROM {g} WHERE principal_id = {b.sbind('p')}", {"p": typ}, reps)
        gmap = {pf: lv for _, pf, lv in corpus.grant_flat if _ == typ}
        t0 = time.perf_counter()
        levels = [C.resolve_level(pth, gmap) for pth in check_paths]
        app_ms = (time.perf_counter() - t0) * 1000
        res["write"] = {"single_median_ms": single_med, "single_mean_ms": statistics.mean(singles), "batch": t_batch.__dict__, "distinct_prefixes": len(all_anc), "grants_once": t_grants.__dict__, "app_resolve_ms": app_ms, "resolved": sum(1 for x in levels if x)}
        md.append("### 2. Write point check (longest matching prefix)\n")
        md.append(md_table(
            ["form", "cost", "statements", "binds per statement"],
            [
                ["one path: `principal_id = :p AND path_prefix IN (ancestors)`", f"{single_med:.2f} ms median per check (200 distinct paths, mean {statistics.mean(singles):.2f})", "1", "1 + depth (≤ 9)"],
                ["10k paths: distinct ancestors chunked `IN`", f"{t_batch.median_ms:.1f} ms total ({len(all_anc):,} distinct prefixes)", str(t_batch.statements), f"1 + {b.membership_budget}"],
                ["10k paths: fetch the caller's grants once, resolve in app", f"{t_grants.median_ms:.1f} ms query ({t_grants.rows} rows) + {app_ms:.1f} ms app resolve", "1", "1"],
            ],
        ) + "\n")
        print(f"[{engine}] write: single {single_med:.2f}ms, batch {t_batch}, once {t_grants} + app {app_ms:.1f}ms", flush=True)

        # -- 3. materialised: size and maintenance
        en, vt = b.t["entry"].name, b.t["vis"].name
        everyone = {f"/t{r:03d}" for r in C.EVERYONE_TOP_RANKS}
        exhaustive = sum(corpus.subtree_size(pf) for _, pf, _ in corpus.grant_flat)
        direct_only = sum(corpus.subtree_size(pf) for _, pf, _ in corpus.grant_flat if pf not in everyone)
        exhaustive_gx = sum(corpus.subtree_size(pf) for _, pf, _ in corpus.grant_gx)
        direct_prefixes = [pf for p, pf, _ in corpus.grant_flat if p == typ and pf not in everyone]
        small_pf = sorted(direct_prefixes, key=corpus.subtree_size)[len(direct_prefixes) // 2]
        maint = {}
        for label, pf in (("typical direct grant", small_pf), ("wide grant /t000, one principal", "/t000")):
            sql = f"INSERT INTO {vt} (principal_id, entry_id) SELECT {b.sbind('px')}, e.id FROM {en} e WHERE e.path = {b.pbind('q')} OR e.path LIKE {b.pbind('ql')}"
            samples = []
            for _ in range(3):
                t0 = time.perf_counter()
                await b.conn.execute(__import__("sqlalchemy").text(sql), {"px": "pzz999", "q": pf, "ql": pf + "/%"})
                dt = (time.perf_counter() - t0) * 1000
                await b.conn.rollback()
                samples.append(dt)
            maint[label] = (statistics.median(samples), corpus.subtree_size(pf), pf)
        res["materialised"] = {"exhaustive_rows": exhaustive, "direct_only_rows": direct_only, "exhaustive_groups_expanded": exhaustive_gx, "maintenance": maint, "sample_rows": load["vis_rows"]}
        md.append("### 3. Materialised `visible(principal_id, entry_id)`: size and maintenance\n")
        md.append(md_table(
            ["quantity", "value"],
            [
                ["entry rows", f"{n_rows:,}"],
                ["exhaustive visible rows, flat grants (direct + 5 everyone grants)", f"{exhaustive:,} ({exhaustive / n_rows:,.0f}× the entry table)"],
                ["  of which the 5 everyone grants × 10,000 principals", f"{exhaustive - direct_only:,}"],
                ["  direct grants only", f"{direct_only:,} ({direct_only / n_rows:.1f}× the entry table)"],
                ["exhaustive visible rows, groups expanded", f"{exhaustive_gx:,}"],
                ["sample loaded for the read tests (2 principals)", f"{load['vis_rows']:,} rows in {load['vis']:.1f}s"],
                *[[f"insert one grant's rows: {k} (`{v[2]}`)", f"{v[0]:.1f} ms for {v[1]:,} rows"] for k, v in maint.items()],
                ["a new everyone grant on /t000", f"{corpus.subtree_size('/t000'):,} rows × 10,000 principals = {corpus.subtree_size('/t000') * C.PRINCIPALS:,} rows, ≈ {maint['wide grant /t000, one principal'][0] * C.PRINCIPALS / 1000:,.0f} s at the measured per-principal rate"],
            ],
        ) + "\n")
        print(f"[{engine}] materialised: exhaustive {exhaustive:,}, maint {maint}", flush=True)

        # -- 4. groups
        rows_md = []
        gpreds = {"flat expanded (exists over grantgx)": p_exists(b, typ, "grantgx"), "membership subquery": p_groups_sub(b, typ), "groups literal": p_groups_literal(b, corpus, typ)}
        for fname in ("glob", "grep"):
            tpl, fp = F[fname]
            row = [fname]
            for pname, pr in gpreds.items():
                t = await b.timeit(select(b, tpl.format(e="e"), pr), {**fp, **pr.params}, reps)
                res[f"groups/{fname}/{pname}"] = t.__dict__
                row.append(cell(t) + f" · {t.rows}r")
            rows_md.append(row)
        row = ["join-back K=1000 IN"]
        for pname, pr in gpreds.items():
            stmts, _ = joinback(b, cands[1000], pr, "in")
            t = await b.timeit(stmts, reps=reps)
            res[f"groups/back1000/{pname}"] = t.__dict__
            row.append(cell(t) + f" · {t.rows}r")
        rows_md.append(row)
        md.append(f"### 4. Groups: three encodings of the same rights (typical principal, {len(corpus.groups_of[typ])} groups)\n")
        md.append(md_table(["filter", *[f"{k} ({p.binds} binds)" for k, p in gpreds.items()]], rows_md) + "\n")
        print(f"[{engine}] groups done", flush=True)

        # -- 5. subject set
        rows_md = []
        for n, members in sets.items():
            for fname in ("glob", "grep"):
                tpl, fp = F[fname]
                row = [f"n={n} {fname}"]
                for pr in (p_set_and(b, members), p_set_having(b, members, tpl, fp), p_set_app(b, corpus, members)):
                    t = await b.timeit(select(b, tpl.format(e="e"), pr), {**fp, **pr.params}, reps)
                    res[f"set/{n}/{fname}/{pr.label}"] = {**t.__dict__, "binds": pr.binds + len(fp)}
                    row.append(cell(t) + f" · {t.rows}r · {pr.binds + len(fp)}b")
                    print(f"[{engine}] set n={n} {fname} {pr.label:32s} {t}", flush=True)
                rows_md.append(row)
            row = [f"n={n} join-back K=1000"]
            ids = cands[1000]
            for pr, copies in ((p_set_and(b, members), 1), (p_set_having(b, members, "{e}.id IN (" + ", ".join(f":c{i}" for i in range(1000)) + ")", {}), 1), (p_set_app(b, corpus, members), 1)):
                if pr.label.startswith("set_having"):
                    # the grouped form repeats the candidate list three times: chunk to fit
                    budget = min(b.membership_budget, (b.parameter_budget - 32 - len(members) - 1) // 3)
                    stmts = []
                    for chunk in chunked(ids, budget):
                        prh = p_set_having(b, members, "{e}.id IN (" + ", ".join(f":c{i}" for i in range(len(chunk))) + ")", {})
                        params = {f"c{i}": v for i, v in enumerate(chunk)}
                        params.update(prh.params)
                        sql = f"SELECT e.id FROM {b.t['entry'].name} e WHERE e.id IN ({', '.join(f':c{i}' for i in range(len(chunk)))}) AND {prh.sql}"
                        stmts.append((sql, params))
                    binds = 3 * min(budget, len(ids)) + len(members) + 1
                else:
                    stmts, budget = joinback(b, ids, pr, "in", copies)
                    binds = min(budget, len(ids)) + pr.binds
                t = await b.timeit(stmts, reps=reps)
                res[f"set/{n}/back1000/{pr.label}"] = {**t.__dict__, "binds": binds, "chunk": budget}
                row.append(cell(t) + f" · {t.rows}r · {binds}b")
                print(f"[{engine}] set n={n} back1000 {pr.label:32s} {t}", flush=True)
            rows_md.append(row)
        md.append("### 5. Subject set: a right held by every principal in the set (b = binds per statement)\n")
        md.append(md_table(["set / filter", "(a) AND of n EXISTS", "(b) grouped HAVING COUNT(DISTINCT) = n", "(c) app-side prefix intersection, literal"], rows_md) + "\n")

        # -- plans
        if plans:
            tpl, fp = F["grep"]
            tplg, fpg = F["glob"]
            plan_targets = {
                "grep · exists": (select(b, tpl.format(e="e"), preds["exists"]), {**fp, **preds["exists"].params}),
                "glob · exists": (select(b, tplg.format(e="e"), preds["exists"]), {**fpg, **preds["exists"].params}),
                "glob · literal_like": (select(b, tplg.format(e="e"), preds["literal_like"]), {**fpg, **preds["literal_like"].params}),
                "glob · literal_range": (select(b, tplg.format(e="e"), preds["literal_range"]), {**fpg, **preds["literal_range"].params}),
                "grep · materialised": (select(b, tpl.format(e="e"), preds["materialised"]), {**fp, **preds["materialised"].params}),
                "grep · groups subquery": (select(b, tpl.format(e="e"), gpreds["membership subquery"]), {**fp, **gpreds["membership subquery"].params}),
                "glob · set n=5 AND": (select(b, tplg.format(e="e"), p_set_and(b, sets[5])), {**fpg, **p_set_and(b, sets[5]).params}),
                "glob · set n=5 HAVING": (select(b, tplg.format(e="e"), p_set_having(b, sets[5], tplg, fpg)), {**fpg, **p_set_having(b, sets[5], tplg, fpg).params}),
                "glob · set n=5 app": (select(b, tplg.format(e="e"), p_set_app(b, corpus, sets[5])), {**fpg, **p_set_app(b, corpus, sets[5]).params}),
            }
            jb, _ = joinback(b, cands[1000], preds["exists"], "in")
            plan_targets["join-back K=1000 IN · exists"] = jb[0]
            jv, _ = joinback(b, cands[1000], preds["exists"], "values")
            if jv:
                plan_targets["join-back K=1000 VALUES · exists"] = jv[0]
            rows_md = []
            for label, (sql, params) in plan_targets.items():
                pl = await b.plan(sql, params)
                res[f"plan/{label}"] = pl
                res[f"planraw/{label}"] = b.last_plan_raw
                b.last_plan_raw = ""
                rows_md.append([label, "`" + pl.replace("|", "/") + "`"])
                print(f"[{engine}] plan {label}: {pl}", flush=True)
            md.append("### Plan shapes\n")
            md.append(md_table(["query", "plan skeleton"], rows_md) + "\n")

        # -- 6. budgets
        K, n, G = 10_000, 20, max(grants_per.values())
        mb, pb = b.membership_budget, b.parameter_budget
        import math
        rows_md = [
            ["read: owner OR EXISTS", "1", "1", "yes"],
            ["read: literal prefixes (LIKE)", "1 + 2G", f"{1 + 2 * G} (G = {G}, corpus max)", f"yes while 1 + 2G ≤ {pb - 32}; needs a per-principal grant cap or an EXISTS fallback"],
            ["read: literal prefixes (range)", "1 + 3G", f"{1 + 3 * G}", "same"],
            ["join-back IN, EXISTS", "chunk + 1", f"{mb + 1} per statement, {math.ceil(K / mb)} statements at K = 10k", "yes (chunked)"],
            ["join-back VALUES, EXISTS", "chunk + 1", f"{mb + 1}, {math.ceil(K / mb)} statements", "yes (chunked)"],
            ["write check, one path", "1 + depth", "≤ 10", "yes"],
            ["write check, 10k batch as chunked IN", "1 + chunk", f"{1 + mb}, {math.ceil(len(all_anc) / mb)} statements ({len(all_anc):,} distinct ancestors)", "yes (chunked)"],
            ["write check, grants fetched once", "1", "1", "yes; app resolves"],
            ["groups: membership subquery", "1", "1", "yes"],
            ["groups: literal group ids", "1 + |groups(p)|", f"{1 + len(corpus.groups_of[typ])} here", "yes while |groups(p)| ≤ budget"],
            ["set (a) AND of n EXISTS", "n", f"{n}", "yes"],
            ["set (b) HAVING, scoped", "n + 1 + copies × filter", f"{n + 1} + 3 × chunk on join-back → chunk ≤ {(pb - 32 - n - 1) // 3}", "yes only if the candidate list is chunked at a third of the budget"],
            ["set (c) app-side intersection", "≤ 2|∩| + Σ_i (1 + 2|∩_{-i}|)", f"measured: {res[f'set/{n}/glob/' + p_set_app(b, corpus, sets[n]).label]['binds'] - 4} at n = 20", "yes while n × G stays under the budget; worst case (n+1) × 2G"],
        ]
        md.append("### 6. Bind budgets at a 10k batch, n = 20, G = grants per principal\n")
        md.append(md_table(["shape", "binds", "on this engine", "respects membership_budget?"], rows_md) + "\n")

        out["results"] = res
        out["seconds"] = time.perf_counter() - t_all
        md.append(f"Wall clock for this run: {out['seconds'] / 60:.1f} min.\n")

    os.makedirs(os.path.join(HERE, "runs"), exist_ok=True)
    stem = os.path.join(HERE, "runs", f"{engine}-{n_rows}")
    with open(stem + ".json", "w") as f:
        json.dump(out, f, indent=1, default=str)
    with open(stem + ".md", "w") as f:
        f.write("\n".join(md))
    print(f"[{engine}] done in {out['seconds'] / 60:.1f} min → {stem}.md", flush=True)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--engine", required=True, choices=["sqlite", "postgres", "mssql", "oracle", "mariadb"])
    ap.add_argument("--files", type=int, default=75_000)
    ap.add_argument("--reps", type=int, default=5)
    ap.add_argument("--no-plans", action="store_true")
    a = ap.parse_args()
    asyncio.run(run(a.engine, a.files, a.reps, not a.no_plans))
