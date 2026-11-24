"""Part C: tools as searchable files in vfs, measured with vfs's own search and grep.

Run: cd /home/user/vfs && uv run python -I agents/2026-11-23-code-mode-prior-art/studies/experiments/08-tool-catalogs/retrieval.py [--quick]
Reads queries_tagged.json (written by queries_check.py before any retrieval). Writes per_query.jsonl,
retrieval_summary.json and retrieval_bytes.json beside this file.

One manifest file per tool at /tools/<server>/<tool>.md. Variants:
  V1  name, server line, description
  V2  V1 + one line per parameter: name, type, required or optional, enum members, description
  V3  V2 + two example requests (GitHub tools only; github_examples.json, written before measurement)
Backends (every one a DatabaseStorage on a private in-memory SQLite, through the public constructors):
  mem-overlay   InMemoryStorage(), files written, no rebuild: what search answers right after a write
  lexical       DatabaseStorage(url=memory, embedder=None), rebuilt: the BM25 postings leg alone
  hash-vector   DatabaseStorage(url=memory, embedder=HashEmbeddingProvider(), vector-only Convex), rebuilt
  mem-fused     InMemoryStorage(), rebuilt: its default hash embedder fused 0.5/0.5 with lexical
grep: one case-insensitive fixed-string grep per key word over /tools, files ranked by how many distinct
key words they contain; ties share their expected rank (the mean of the tied positions).
"""

from __future__ import annotations

import asyncio
import json
import os
import statistics
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from catalogs import load_all, nbytes  # noqa: E402
from census import normalize  # noqa: E402

from vfs import AsyncVirtualFileSystem, DatabaseStorage, Entry, InMemoryStorage  # noqa: E402
from vfs.embedding.hashing import HashEmbeddingProvider  # noqa: E402
from vfs.storage.ranking import Convex, Ranker  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
MEMORY_URL = "sqlite+aiosqlite:///:memory:"
LIMIT = 10
EXAMPLES = json.load(open(os.path.join(HERE, "github_examples.json"), encoding="utf-8"))


def param_lines(schema):
    if not schema:
        return []
    required = set(schema.get("required") or [])
    lines = []
    for name, prop in (schema.get("properties") or {}).items():
        if not isinstance(prop, dict):
            continue
        p = normalize(prop, schema)
        kind = p.get("type", "any")
        if isinstance(kind, list):
            kind = "|".join(k for k in kind if k != "null")
        if "enum" in p:
            kind = "one of " + ", ".join(str(m) for m in p["enum"])
        elif kind == "array" and isinstance(p.get("items"), dict):
            kind = f"array of {normalize(p['items'], schema).get('type', 'any')}"
        need = "required" if name in required else "optional"
        desc = " ".join(str(p.get("description", "")).split())
        lines.append(f"- {name} ({kind}, {need}){': ' + desc if desc else ''}")
    return lines


def manifest(tool, variant):
    out = [f"# {tool['name']}", "", f"server: {tool['server']}", "", tool["description"].strip(), ""]
    if variant in ("V2", "V3"):
        params = param_lines(tool["input_schema"])
        out += ["## Parameters", "", *(params or ["(none)"]), ""]
    if variant == "V3" and tool["server"] == "github":
        out += ["## Example requests", "", *(f"- {e}" for e in EXAMPLES[tool["name"]]), ""]
    return "\n".join(out)


def path_of(tool):
    return f"/tools/{tool['server']}/{tool['name']}.md"


def label_of(path):
    server, leaf = path[len("/tools/") :].split("/", 1)
    return f"{server}/{leaf[: -len('.md')]}"


def make_storage(backend):
    if backend in ("mem-overlay", "mem-fused"):
        return InMemoryStorage()
    if backend == "lexical":
        return DatabaseStorage(url=MEMORY_URL, embedder=None)
    if backend == "hash-vector":
        return DatabaseStorage(url=MEMORY_URL, embedder=HashEmbeddingProvider(),
                               ranker=Ranker(fusion=Convex({"vector": 1.0})))
    raise ValueError(backend)


async def build(tools, variant, backend):
    storage = make_storage(backend)
    fs = AsyncVirtualFileSystem(storage=storage)
    entries = [Entry(path=path_of(t), content=manifest(t, variant)) for t in tools]
    written = await fs.write(entries, parents=True)
    assert written.success, written.error_message
    if backend != "mem-overlay":
        rebuilt = await storage.rebuild()
        assert rebuilt.success, rebuilt.error_message
    return fs


def rank_of(labels, accept):
    for i, label in enumerate(labels, 1):
        if label in accept:
            return float(i)
    return None


async def run_search(fs, q):
    result = await fs.search(q["query"], limit=LIMIT)
    labels = [label_of(o.path) for o in result.observations if str(o.path).startswith("/tools/")]
    return labels, result


async def run_grep(fs, q):
    counts = {}
    rendered = 0
    for word in q["grep_words"]:
        result = await fs.grep(word, paths=("/tools",), case_mode="insensitive", fixed_strings=True, output_mode="files")
        rendered += nbytes(str(result))
        for o in result.observations:
            counts[label_of(str(o.path))] = counts.get(label_of(str(o.path)), 0) + 1
    return counts, rendered


def grep_rank(counts, accept):
    """Expected rank of the best acceptable file: files with more key words first, ties share the mean position."""
    best = None
    for label in accept:
        if label not in counts:
            continue
        score = counts[label]
        better = sum(1 for s in counts.values() if s > score)
        tied = sum(1 for s in counts.values() if s == score)
        r = better + (tied + 1) / 2
        best = r if best is None or r < best else best
    return best


def metrics(ranks):
    n = len(ranks)
    def hit(k):
        return sum(1 for r in ranks if r is not None and r <= k) / n
    mrr = sum(1 / r for r in ranks if r is not None and r <= LIMIT) / n
    return {"n": n, "hit@1": round(hit(1), 3), "hit@3": round(hit(3), 3), "hit@5": round(hit(5), 3),
            "hit@10": round(hit(10), 3), "mrr@10": round(mrr, 3)}


async def main():
    quick = "--quick" in sys.argv
    queries = json.load(open(os.path.join(HERE, "queries_tagged.json"), encoding="utf-8"))
    everything = load_all()
    github = [t for t in everything if t["server"] == "github"]
    corpora = {"combined": (everything, ["V1", "V2"], queries),
               "github": (github, ["V1", "V2", "V3"], [q for q in queries if q["target"].startswith("github/")])}
    backends = ["lexical"] if quick else ["mem-overlay", "lexical", "hash-vector", "mem-fused"]
    rows, summary, byte_samples = [], {}, {}
    for corpus, (tools, variants, qs) in corpora.items():
        for variant in variants:
            for backend in backends:
                t0 = time.monotonic()
                fs = await build(tools, variant, backend)
                built = time.monotonic() - t0
                ranks, by_cat = [], {"named": [], "paraphrase": []}
                search_bytes = []
                for q in qs:
                    accept = {q["target"], *q["alternates"]}
                    labels, result = await run_search(fs, q)
                    r = rank_of(labels, accept)
                    ranks.append(r)
                    by_cat[q["category"]].append(r)
                    top5 = await fs.search(q["query"], limit=5)
                    search_bytes.append(nbytes(str(top5)))
                    rows.append({"corpus": corpus, "variant": variant, "method": f"search:{backend}", "id": q["id"],
                                 "category": q["category"], "rank": r, "top5": labels[:5]})
                key = f"{corpus}/{variant}/search:{backend}"
                summary[key] = {"all": metrics(ranks), **{c: metrics(v) for c, v in by_cat.items() if v},
                                "build_seconds": round(built, 1)}
                byte_samples[key] = {"search_top5_bytes_median": statistics.median(search_bytes),
                                     "search_top5_bytes_max": max(search_bytes)}
                if backend == backends[0]:
                    ranks, by_cat, grep_bytes, cands = [], {"named": [], "paraphrase": []}, [], []
                    for q in qs:
                        accept = {q["target"], *q["alternates"]}
                        counts, rendered = await run_grep(fs, q)
                        r = grep_rank(counts, accept)
                        ranks.append(r)
                        by_cat[q["category"]].append(r)
                        grep_bytes.append(rendered)
                        cands.append(len(counts))
                        top = sorted(counts.items(), key=lambda kv: (-kv[1], kv[0]))[:5]
                        rows.append({"corpus": corpus, "variant": variant, "method": "grep", "id": q["id"],
                                     "category": q["category"], "rank": r, "top5": [k for k, _ in top],
                                     "candidates": len(counts)})
                    gkey = f"{corpus}/{variant}/grep"
                    summary[gkey] = {"all": metrics(ranks), **{c: metrics(v) for c, v in by_cat.items() if v},
                                     "candidates_median": statistics.median(cands)}
                    byte_samples[gkey] = {"grep_output_bytes_median": statistics.median(grep_bytes),
                                          "grep_output_bytes_max": max(grep_bytes)}
                    listing = await fs.ls("/tools")
                    byte_samples[f"{corpus}/{variant}/ls /tools"] = nbytes(str(listing))
                    if corpus == "combined":
                        one = await fs.ls("/tools/github")
                        byte_samples[f"{corpus}/{variant}/ls /tools/github"] = nbytes(str(one))
                        sizes = sorted(nbytes(manifest(t, variant)) for t in tools)
                        byte_samples[f"{corpus}/{variant}/manifest_bytes"] = {
                            "median": statistics.median(sizes), "p90": sizes[int(0.9 * len(sizes))], "max": sizes[-1]}
                await fs.close()
                print(f"{key}: {summary[key]['all']} built in {built:.1f}s", flush=True)
                if backend == backends[0]:
                    print(f"{corpus}/{variant}/grep: {summary[corpus + '/' + variant + '/grep']['all']}", flush=True)
    suffix = "_quick" if quick else ""
    with open(os.path.join(HERE, f"per_query{suffix}.jsonl"), "w", encoding="utf-8") as fh:
        for row in rows:
            fh.write(json.dumps(row) + "\n")
    with open(os.path.join(HERE, f"retrieval_summary{suffix}.json"), "w", encoding="utf-8") as fh:
        json.dump(summary, fh, indent=1)
    with open(os.path.join(HERE, f"retrieval_bytes{suffix}.json"), "w", encoding="utf-8") as fh:
        json.dump(byte_samples, fh, indent=1)


if __name__ == "__main__":
    asyncio.run(main())
