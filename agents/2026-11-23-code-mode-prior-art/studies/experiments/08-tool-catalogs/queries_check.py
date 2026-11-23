"""Validate the labelled query set and the example file; tag each query named or paraphrase; derive grep key words.

Run: cd /home/user/vfs && uv run python -I agents/2026-11-23-code-mode-prior-art/studies/experiments/08-tool-catalogs/queries_check.py
Runs no retrieval. Writes queries_tagged.json.

A query is "paraphrase" when it shares no word with its target tool's name (name split on _ - and case
change, lowercased, compared as whole words, no stemming). Key words for grep are the query's words
minus a fixed stopword list, at least three characters long.
"""

from __future__ import annotations

import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from catalogs import load_all, load_github  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
STOPWORDS = frozenset(
    "a an the this that these those my our your their me i we you it its is are was be been being am "
    "do does did of in on at to for from by with into as and or but if so not no all any every some "
    "what which who whom whose why how when where can could should would will shall may might must "
    "show get give tell let make please there here up out about over under after before last new "
    "someone anyone else them they his her him she he s has have".split()
)


def words(text):
    parts = re.findall(r"[A-Za-z0-9]+", re.sub(r"([a-z])([A-Z])", r"\1 \2", text))
    return [p.lower() for p in parts]


def key_words(query):
    """Whole words as typed (no camel-case split), lowercased; grep runs case-insensitive."""
    seen = []
    for w in (p.lower() for p in re.findall(r"[A-Za-z0-9]+", query)):
        if len(w) >= 3 and w not in STOPWORDS and w not in seen:
            seen.append(w)
    return seen


def main():
    known = {f"{t['server']}/{t['name']}" for t in load_all()}
    data = json.load(open(os.path.join(HERE, "queries.json"), encoding="utf-8"))
    tagged, problems = [], []
    for q in data["queries"]:
        for label in [q["target"], *q["alternates"]]:
            if label not in known:
                problems.append(f"{q['id']}: unknown tool {label}")
        name_words = set(words(q["target"].split("/", 1)[1]))
        shared = sorted(name_words & set(words(q["query"])))
        tagged.append(dict(q, category="named" if shared else "paraphrase", shared_with_name=shared,
                           grep_words=key_words(q["query"])))
    examples = json.load(open(os.path.join(HERE, "github_examples.json"), encoding="utf-8"))
    names = {t["name"] for t in load_github()}
    missing = sorted(names - set(examples))
    extra = sorted(set(examples) - names - {"_note"})
    bad = sorted(k for k, v in examples.items() if k != "_note" and len(v) != 2)
    if missing or extra or bad:
        problems.append(f"examples: missing={missing} extra={extra} not-two={bad}")
    with open(os.path.join(HERE, "queries_tagged.json"), "w", encoding="utf-8") as fh:
        json.dump(tagged, fh, indent=1)
    cats = {c: sum(1 for t in tagged if t["category"] == c) for c in ("named", "paraphrase")}
    gh = sum(1 for t in tagged if t["target"].startswith("github/"))
    print(f"queries={len(tagged)} github={gh} other={len(tagged) - gh} {cats}")
    print("problems:", problems or "none")
    for t in tagged:
        print(t["id"], t["category"], t["shared_with_name"], t["grep_words"])


if __name__ == "__main__":
    main()
