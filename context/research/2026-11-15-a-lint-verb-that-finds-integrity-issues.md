# A `lint` verb can find most of what can break in a mount with plain, paged reads: the idea it is named for covers a wiki's references only, vfs today serves almost every kind of planted damage as success, and every check but the bytes costs what it returns

Clay asked on 2026-11-15: "I want to have a lint verb that finds integrity issues with vfs. Can you have that apart of research? Comes come karpharys llm wiki idea, but maps nicely into vfs". It followed his ruling of the same day on a damaged file: "I want to make sure an incorrect hash doesn't essentially lock a file. We need a plan to repair it", which is decision 9 of [the kernel rulings spec](../specifications/active/2026-11-15-the-kernels-public-names-and-argument-families-are-ruled.md). Two researchers worked the same day to [the brief](studies/2026-11-15-a-lint-verb-that-finds-integrity-issues/00-brief.md), for about nine and eighteen minutes: one found the named idea's primary source and read how eleven tools check themselves, and one listed the rules vfs holds across rows, broke each on the in-memory store with direct SQL, and costed a check of each. No intention: the question came from one request. The spec that will use the answer is the lint spec, which is not yet written; it would take the place of the `scrub` verb that [spec 175](../specifications/active/175-integrity-verify-on-read-and-scrub/spec.md) plans and has not built.

Labels: EXECUTED means a command ran on 2026-11-15 and the claim reports its output; READ means read in the file or on the page cited; INFERRED means reasoning from the two. Each claim below is from one of the two studies, which give the file and line, the probe, or the page and date: [study 01, the idea and the prior art](studies/2026-11-15-a-lint-verb-that-finds-integrity-issues/01-the-llm-wiki-idea-and-how-other-tools-check-themselves.md) and [study 02, what vfs could check](studies/2026-11-15-a-lint-verb-that-finds-integrity-issues/02-what-vfs-could-check-and-what-each-check-costs.md).

## Sources

Andrej Karpathy's gist `llm-wiki.md`, <https://gist.github.com/karpathy/442a6bf555914893e9891c11519de94f>, created 2026-04-04, its raw text downloaded and read on 2026-11-15. The official documentation of `e2fsck`, `git fsck`, ZFS and btrfs scrub, SQLite's `PRAGMA integrity_check` and `foreign_key_check`, Postgres's `amcheck`, MediaWiki's maintenance reports, a Markdown link checker, ESLint and Ruff, each page by URL in study 01, read the same day. vfs at `08c372af`: `src/vfs/models/rows.py`, and under `src/vfs/storage/backends/database/` the files `maintenance.py`, `segments.py`, `edges.py`, `labels.py`, `trash.py`, `versions.py`, `links.py` and `writes.py`; `tests/storage/database/test_races.py`. Eight probe scripts and their outputs under the studies folder's `experiments/`, run on the in-memory store. No reference clone was opened.

## The answer

The idea maps onto vfs, and wider than its source. Karpathy's lint is a health check a model runs over a wiki's pages and links; it says nothing about stored bytes or structure. vfs has two more layers under the content that a lint can check, and today almost nothing checks them: the schema has no foreign key, every rule across rows is kept by the verbs alone, and of eighteen kinds of damage planted with direct SQL nearly all were served as success (EXECUTED). Every check except the bytes is a plain read that seeks an index, pages by a key and takes no lock, so a lint of one folder costs the rows in that folder and a lint of the whole reference mount is about 11,000 statements once a day (EXECUTED on a small store, INFERRED at scale). The bytes check alone must read every body, which is why every tool read keeps it apart or off by default. Finding and repairing are two acts in every tool read, and none of them locks a damaged thing as its answer.

## 1. What the named idea says

READ, the gist. It names three operations on a wiki a model maintains: ingest, query and lint. The whole of its lint is one paragraph: "Periodically, ask the LLM to health-check the wiki. Look for: contradictions between pages, stale claims that newer sources have superseded, orphan pages with no inbound links, important concepts mentioned but lacking their own page, missing cross-references, data gaps that could be filled with a web search." It says nothing about bytes, hashes, severity, a finding's shape, repair as a separate step, or who may run it; its store is "just a git repo of markdown files".

Three of the six checks have a form that needs no model (INFERRED): a page nothing links to, a link to a page that does not exist, and a link with no link back. The other three, contradictions, stale claims and gaps, need a model or a person. So a verb that works from rows can do the mechanical half and hand its findings to the agent, which does the rest in the same session.

## 2. What vfs holds, and what notices when it breaks

EXECUTED unless a line says READ, study 02's sections 3 to 7. Seventeen rules hold across rows. What notices a broken one today:

| Layer | A broken rule | What happens today |
|---|---|---|
| Bytes | a body that does not match its hash, or is missing | `read` serves it; `copy` duplicates it; `edit` writes it back under a fresh matching hash, with a healthy-looking version row |
| Bytes | a wrong size or line count | `stat` and `read` report the wrong numbers until the next write |
| Structure | a path that disagrees with its parent and name; a parent that is missing or deleted | nothing in `src/`; only the tests' own audit checks it |
| Structure | a missing parent | `rebuild` makes it worse: each run mints an edge to nowhere and the next deletes and mints it again |
| Structure | wrong segment postings, a wrong parent-child edge, an edge to a missing row | `rebuild` finds and repairs each, with a warning: it is already a lint with repair for these three |
| History | an entry's version number below its own version rows | every later overwrite fails with the database's raw constraint text, so the file is locked against writing |
| Rights | a stored label that differs from the standing posture | `read` still refuses, but an anonymous `glob` lists the file and an anonymous `grep` returns it; `rebuild` and `refresh` do not fix labels, and `rebuild_labels` has no caller |
| Rights | a relabel mark with no posture row | every call by a named or anonymous caller raises an unclassified `KeyError` until any `posture` call clears it |
| Rights | a grant on a path whose file was purged | it applies to the next file written at that path; a grant is a prefix, and nothing removes it |
| Index | a row marked indexed that the index does not hold | `grep` misses the file for good, across `refresh` and `rebuild` |
| References | a document's extracted links after the tree changed around it | the edges go stale; links are not extracted again when a missing target appears |

The one whole-store audit that exists is `_audit` in `tests/storage/database/test_races.py`. It checks four things and runs on the server legs only (READ).

Two of these are the lock Clay ruled against, in other forms: the version number that refuses every overwrite, and the mark that makes every call raise.

## 3. What other tools do

READ, study 01's sections 2 and 3.

Names sort by layer. "Scrub" (ZFS, btrfs) is always stored bytes against checksums. "fsck" and "check" are structure. "Lint", "report" and "link check" are content. Only `git fsck` covers all three under one name, with a flag that leaves the byte layer out. The nearest prior art to the gist's lint is MediaWiki's maintenance reports: pages nothing links to, pages wanted and missing, broken and double redirects.

Finding is the default, and repair is asked for apart and in grades: `e2fsck -p` against `-y`, Ruff's `--fix` against `--unsafe-fixes`, btrfs's repair filed as dangerous. Only the scrubs repair unasked, and only from a second copy they have verified. git and `amcheck` do not repair at all. No tool read makes a damaged object unusable as its response: it names the object and leaves the decision to the operator.

One finding has the same five parts everywhere: a rule's code, a severity or a safe-to-fix class, a location, a message with what was found and what was expected, and a fix as data where one exists.

Large stores are bounded six ways: a scope argument, a cursor to resume from, a cap on findings, a cheap mode that drops the costly layer, a rate limit, and a cached report a batch job refreshes.

One page speaks to who may run a check: `amcheck` warns that a caller who can run it and cause damage "might be able to infer something of the data itself".

## 4. What each check costs

EXECUTED on a store of 20,806 rows with each statement's plan read, study 02's section 9; the last column multiplies and is INFERRED.

| Check | Shape | One folder or subtree | The whole reference mount |
|---|---|---|---|
| Structure: parent, path, kind, live under deleted, the parent-child edge | one statement a page of 1,000, by a key, each row seeking its parent | one statement for a folder's children; a range on the path index for a subtree | about 11,000 statements and 11 million row visits |
| Label against posture | one seek per posture region and level on a covering index | the same, clipped | follows the number of posture rows, not the corpus; returns only wrong rows |
| A row marked indexed with no chunk rows | file rows by key, one covering seek each | under a path range | 10 million seeks |
| A body, version or chunk row with no entry | the dependent table by its own key | cannot be scoped by path: such a row has none | 10 million body rows, 100 million chunk rows |
| An edge with a missing end; a link to a deleted file | edges by key, two seeks | from one source, by an index | at least 11 million edges |
| A grant on a path with no row | one seek per grant | by prefix | one seek per grant row |
| A file nothing links to | one covering seek per file on the reverse edge index | under a path range | 10 million seeks; most files match on a corpus that is not a wiki |
| Two files with one hash | one ordered walk of the hash index | each file seeks the hash index | one pass over a 10-million-entry index |
| Bytes: body against hash | every body crosses the wire and is hashed in the caller | the bodies in scope | about 40 GB if text only, 3 to 7 TB with binary bodies |

None takes a lock another caller waits on. Each page should be its own short transaction, so a rival's commit between two pages can look like damage; a finding is believed only when a second read agrees, the rule spec 175 already states (INFERRED).

The structure checks can ride the daily `rebuild`, which already reads every entry row twice (EXECUTED); the bytes check rides nothing, because `rebuild` reads a body only when a write flagged it (EXECUTED).

## 5. What the rows cannot answer

EXECUTED and READ, study 02's section 10. From rows alone vfs can find a link to a deleted file, a file nothing links to, and two files with one hash. It cannot find a link to a path that never existed, because the link extractor only counts those and keeps no row for them, and it cannot find link text made stale by a move. Contradictions, stale claims and gaps are the model's half (section 1).

## 6. Who may run it, and what a finding may say

INFERRED from the rights rules READ in `src/vfs/ops.py` and the probes of study 02's section 11. Today a row a caller cannot see and a row that does not exist answer alike. A lint keeps that only under two rules. A finding that would name a row its caller cannot see reports it as absent: a broken link to a hidden target reads as a link to nothing, a hidden twin is not counted, or the lint becomes a way to learn that a hidden file exists or what it holds. And the checks with no path to judge (rows with no entry), with the ones whose finding is itself a rights fact (labels, grants), are for the system actor.

## 7. Finding and repairing

INFERRED from sections 2 and 3. The rules split by whether the right answer can be computed. Where the broken thing is derived and its source is whole, a repair is a recomputation and is safe to ask for: a path from parent and name, segment postings, the parent-child edge, a label, a size, an index mark, extracted links. `rebuild` already does three of these. Where the source itself is damaged, there is nothing to compute from and a person chooses: a body that fails its hash, a parent that names nothing, a version row with no entry. The missing-parent loop in section 2 is what a recomputing repair does when it runs against damaged truth without checking it first.

That gives the shape the prior art has: the lint reports and changes nothing; each finding says whether its fix is computable; a caller asks for the computable fixes apart; and for the rest the finding names the ways out, which for a damaged body are the ones decision 9 of the kernel rulings spec lists.

## What this memo does not settle

- Whether the byte layer is a mode of `lint`, off by default, or stays a verb of its own. The experiment: none settles it; it is a naming ruling, informed by section 3, where one tool of eleven puts all three layers under one name and gives it a flag to drop the bytes.
- Whether each plan holds on Postgres, MariaDB, SQL Server and Oracle as it did on SQLite. The experiment: study 02's probe p05 on the four engine legs with each engine's plan recorded.
- How a whole-mount lint's findings are kept between runs: returned page by page to the caller, or written to a report the daily pass refreshes. The experiment: the row count and the write cost of a findings table on a store with one finding in a thousand rows planted, at 1,000,000 rows.
- What a concurrent write does to a page-by-page walk in practice: how many findings a second read withdraws. The experiment: the structure walk run beside the label experiment's sixteen writers on one engine leg, counting findings before and after the second read.
- Whether the link extractor should keep a row for a link to a path that does not exist, so "a wanted page" can be found from rows. The experiment: the count of such links in the repository's own `context/` tree and the rows they would add.

## One line

A `lint` over structure, rights marks, the index's cover and references is cheap, lock-free and scoped by path, the byte pass is the one costly layer and stays opt-in, a finding never names a row its caller cannot see, and repair is a separate ask that is automatic only where the answer can be recomputed.
