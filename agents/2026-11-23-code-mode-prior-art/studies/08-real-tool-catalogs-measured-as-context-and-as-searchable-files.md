# 08 — Real tool catalogs, measured as context and as searchable files

## The question as this study received it

Take real MCP tool definitions that projects check into their repositories as JSON (GitHub's `__toolsnaps__` and two or three more sources, 100+ tools in all) and measure three things. Part A, a census: tools per server, bytes and estimated tokens of each catalog as a model receives it, properties per tool by JSON Schema type, required against optional, read-only and destructive annotations, and how many properties and tools map onto spec 170's flag table (§2) and how many need its `--json` fallback; spec 170 names this census as work to do before it is built. Part B, the cost of each disclosure level for the combined catalog: every full schema preloaded, names only, name plus first sentence, an `ls`-style listing of `/.vfs/mcp/<server>/…`, one tool's full manifest. Part C, tools as searchable files in vfs: one manifest per tool at `/tools/<server>/<tool>.md`, a labelled query set written before any retrieval, hit@1, hit@3, hit@5 and MRR for vfs `search` (lexical leg, and a vector leg if one runs offline) and for `grep`, with three manifest contents compared. Then: what the numbers mean for how a vfs code mode should write tool manifests and at which disclosure level it should start the model.

## Sources

Clones (shallow, read as data only; nothing in them was built, installed or executed):

| Clone | URL | Branch | Commit | Commit date | Licence |
|---|---|---|---|---|---|
| `/home/user/github-mcp-server` | https://github.com/github/github-mcp-server | main | `9a72d8d38fec18c207cd924b33aa0eb3e186252c` | 2026-11-20 | MIT (`LICENSE`) |
| `/home/user/alibabacloud-devops-mcp-server` | https://github.com/aliyun/alibabacloud-devops-mcp-server | master | `526d85c510f3b0557a8d20a53520432dcb8a8304` | 2026-11-06 | Apache-2.0 (`LICENSE`) |
| `/home/user/mcp-registry` | https://github.com/docker/mcp-registry | main | `7acac061940d9b3d6bbfc7dd26b1e9c2ee17b15c` | 2026-11-19 | MIT (`LICENSE`) |
| `/home/user/simulink-agentic-toolkit` | https://github.com/matlab/simulink-agentic-toolkit | main | `bdfaf9ac37876dc38276325a6b2919fa522b33c7` | 2026-11-19 | MathWorks BSD-style licence restricted to use with MathWorks products (`LICENSE.md`); cloned, licence read, **not used as data** because the use restriction makes reuse in an unrelated measurement doubtful |

All four lines are appended to `studies/refresh.log` and `studies/licenses.log`, dated 2026-11-23.

How the sources were found (EXECUTED, 2026-11-23): `gh search code --filename tools.json "inputSchema"`, `gh search code --filename tools.json --owner docker`, `gh search code "readOnlyHint" --filename tools.json`, and `gh search code "inputSchema" --filename "*.snap"`. The last returned no repository other than GitHub's that checks in `.snap` tool snapshots; most `tools.json` hits were single-author hobby servers, and the vendor-maintained ones chosen were Alibaba Cloud's and Docker's registry (which holds tool lists contributed by vendors such as Okta, Stripe, Buildkite, SonarQube and Zscaler).

What each source is (READ):

- GitHub: `pkg/github/__toolsnaps__/*.snap`, 157 files, one JSON object per tool with `name`, `description`, `inputSchema`, `annotations` and often `outputSchema`. `docs/testing.md:22-27` says the snapshots are compared to the live schema in every test run and CI fails on a missing snapshot, so they are the shipped schemas. Eight `_output.snap` files carry no description and repeat a tool already present, and one tool (`get_job_logs`) has two variants; deduplicated by name, 149 tools remain. `README.md:444` says of the `--toolsets` flag: "Enabling only the toolsets that you need can help the LLM with tool choice and reduce the context size." The default toolset is five groups (`README.md:549-558`), so a default install shows fewer than 149.
- Alibaba Cloud DevOps (Yunxiao): `tools.json`, 203 tools, written by `export-tools.mjs:1-30`, which maps the server's registered tools (TypeScript, zod-derived schemas) to `{name, description, inputSchema}`. 50 of the 203 descriptions contain Chinese text.
- Docker MCP registry: `servers/*/tools.json`, 84 files, 56 of them `[]`. `CONTRIBUTING.md:164-166` says a `tools.json` is provided when a server "needs to be configured before listing tools", so the build reads the file instead of running the server. 28 non-empty files hold 755 tools in three shapes: 143 with a full `inputSchema` (Okta 108, Vectra 25, Alfresco 10); 310 in Docker's flat `arguments` list (`name`, `type`, `desc`, `optional`), which has no enums and no nested shapes; 302 (Zscaler) with name and description only.
- vfs at commit `0ed462f`: `context/specifications/active/170-tools-and-mcp-servers-as-views/spec.md` (§2 the flag table, §3.2 the entries, §6 the manifest and search rules); `src/vfs/models/lexical.py:145-155` (`tokenize`); `src/vfs/embedding/hashing.py:1-15`; `src/vfs/embedding/model2vec.py:1-12`; `src/vfs/storage/backends/memory.py:32-60`.

The experiment lives in `studies/experiments/08-tool-catalogs/`: `catalogs.py` (loader), `census.py`, `disclosure.py`, `queries.json` and `github_examples.json` (the labels, written before retrieval), `queries_check.py`, `retrieval.py`, `analysis.py`, and every output (`census.json`, `census.out.md`, `disclosure.json`, `disclosure.out.md`, `queries_tagged.json`, `per_query.jsonl` with 1,340 rows, `retrieval_summary.json`, `retrieval_bytes.json`, `retrieval.out.txt`, `analysis.json`, `analysis.out.md`). The scripts use the standard library and vfs only; the catalogs are read from the clones at the commits above and are not copied into the repository.

Commands, in the order run (EXECUTED; `uv run python -I` with each script adding its own folder to `sys.path`, so nothing is imported from the working directory):

```bash
cd /home/user/vfs
uv run python -I agents/2026-11-23-code-mode-prior-art/studies/experiments/08-tool-catalogs/census.py      # ~5 s
uv run python -I agents/2026-11-23-code-mode-prior-art/studies/experiments/08-tool-catalogs/disclosure.py  # ~3 s
uv run python -I agents/2026-11-23-code-mode-prior-art/studies/experiments/08-tool-catalogs/queries_check.py  # no retrieval; freezes queries_tagged.json
uv run python -I agents/2026-11-23-code-mode-prior-art/studies/experiments/08-tool-catalogs/retrieval.py --quick  # lexical only, a smoke run; outputs deleted
uv run python -I agents/2026-11-23-code-mode-prior-art/studies/experiments/08-tool-catalogs/retrieval.py   # ~4 min, every backend
uv run python -I agents/2026-11-23-code-mode-prior-art/studies/experiments/08-tool-catalogs/analysis.py    # post hoc
```

The labels were frozen before the first retrieval call at 17:07 UTC: `queries.json` sha256 `58f39077…ba67`, `github_examples.json` `535b863f…2d02`, `queries_tagged.json` `6478600f…74d6`. One change was made after the first `queries_check.py` run and before any retrieval: key words for `grep` stopped splitting camel case (`GitHub` was becoming `git`, `hub`) and `has`, `have` joined the stopword list.

## Findings

### Part A — the census

**F1. The corpus is 1,107 tools on 30 servers; 495 carry a full JSON Schema.** (EXECUTED, `census.py`) GitHub 149, Alibaba 203, and 28 Docker-registry servers with 755. By schema fidelity: 495 full schemas (149 GitHub, 203 Alibaba, 143 Docker `inputSchema`), 310 Docker flat argument lists turned into schemas by the loader (lossy), 302 Zscaler tools with no argument data. The full-schema census below uses only the 495. Description length over all 1,107: median 58 bytes, p90 216, max 3,050.

**F2. A catalog costs tens of thousands of tokens per large server.** (EXECUTED) The catalog is the compact JSON list of `{name, description, inputSchema}`, the shape a client puts in front of a model. Tokens are chars/4, an estimate.

| Server | Tools | Catalog bytes | Est. tokens | Bytes with `annotations` and `outputSchema` |
|---|---|---|---|---|
| alibaba-devops | 203 | 172,142 | 38,899 | 172,142 |
| github | 149 | 155,201 | 38,795 | 335,860 |
| okta-mcp-server | 108 | 79,586 | 19,860 | 79,586 |
| zscaler-mcp-server (no schemas) | 302 | 34,725 | 8,682 | 34,725 |
| keboola-mcp | 33 | 30,442 | 7,610 | 30,442 |
| buildkite | 24 | 14,281 | 3,571 | 15,687 |
| maestro-mcp-server | 35 | 14,137 | 3,534 | 14,137 |
| all 30 servers | 1,107 | 577,934 | 140,303 | 759,999 |

GitHub's `outputSchema` more than doubles its catalog (162,129 bytes of output schemas against 124,443 of input schemas). Inside GitHub's input schemas, property descriptions are 52,677 bytes, 42% of them; tool descriptions are 21,123 bytes and names 3,025 (`disclosure.json`, "split").

**F3. Properties are overwhelmingly scalar; 97% take a plain word on a command line.** (EXECUTED) 2,241 top-level properties across the 495 full-schema tools, each normalised as spec 170 §2 says (local `$ref` one level; an `anyOf`/`oneOf` with one non-null arm or `type: [T, "null"]` becomes `T`) and placed in one row of the flag table:

| Flag-table row | Properties | Required | Optional | Share | Flag form |
|---|---|---|---|---|---|
| string | 1,471 | 970 | 501 | 65.6% | plain word |
| string with `contentEncoding: base64` | 0 | 0 | 0 | 0.0% | stdin or `@path` |
| integer | 121 | 19 | 102 | 5.4% | plain word |
| number | 181 | 71 | 110 | 8.1% | plain word |
| boolean | 78 | 2 | 76 | 3.5% | `--x` / `--no-x` |
| enum or const | 173 | 52 | 121 | 7.7% | plain word (all 173 have string members) |
| array of scalars | 63 | 6 | 57 | 2.8% | repeated flag |
| union of scalar arms (`["string","number"]`) | 91 | 89 | 2 | 4.1% | JSON row, but a plain word works (below) |
| array of objects | 16 | 7 | 9 | 0.7% | repeated flag, each value JSON |
| array of anything else (no `items`, or `oneOf` items) | 6 | 2 | 4 | 0.3% | repeated flag, each value JSON |
| object, every sub-property scalar | 2 | 0 | 2 | 0.1% | `'<json>'` (a dotted-flag candidate) |
| object with nested sub-objects | 7 | 5 | 2 | 0.3% | `'<json>'` |
| object with no declared properties (a free map) | 28 | 13 | 15 | 1.2% | `'<json>'` |
| union of several non-scalar arms | 4 | 0 | 4 | 0.2% | `'<json>'` |
| no type | 0 | 0 | 0 | 0.0% | `'<json>'` |

Strictly scalar rows: 2,087 properties (93.1%). The 91 scalar unions are Alibaba's `repositoryId`-style fields typed `["string","number"]` (94 of the 95 unions are Alibaba's); spec 170's JSON row says "parsed as JSON; if that fails and a `string` arm exists, the text as a string", so `--repositoryId 2835387` sends a number and `--repositoryId myorg%2Fmyrepo` sends a string. Counting them, 2,178 properties (97.2%) take a plain word. 63 properties (2.8%) need a JSON value.

**F4. By tool: 89% are plain words only, 27 tools need JSON for a required property, and no tool needs `--json`.** (EXECUTED)

| Measure (495 full-schema tools) | Tools | Share |
|---|---|---|
| no properties at all | 7 | 1.4% |
| every property in a strictly scalar row | 392 | 79.2% |
| every property a plain word (scalar rows plus scalar unions) | 443 | 89.5% |
| at least one property needing a JSON value | 52 | 10.5% |
| a required property needing a JSON value | 27 | 5.5% |
| reachable only through `--json` (top level not an object with properties, a property named `help` or `json`, a name that is not a flag word, a kebab alias collision) | 0 | 0% |
| only JSON-valued properties are flat objects (what dotted flags would rescue) | 1 (`github/actions_list`) | 0.2% |

Per server (full schema): Alibaba 203 tools, 184 plain words only, 19 with a JSON-valued property; GitHub 149, 136 and 13; Okta 108, 93 and 15; Vectra 25, 22 and 3; Alfresco 10, 8 and 2. Median 4 properties per tool (max 33, Alibaba's `create_pipeline_from_description` and `generate_pipeline_yaml`), median 2 required, so the median tool takes 2 positionals under spec 170's rule. Every top-level schema is `type: object`; 222 of 495 declare `additionalProperties: false`, the other 273 say nothing, so a misspelled flag would be accepted silently by more than half of these servers unless refused client-side, as spec 170 §2 does. The Docker flat lists (310 tools, 556 properties, lossy) agree: 284 tools plain words only, 26 with a JSON-valued property, 114 with no arguments.

**F5. Three facts for the flag table that the table does not yet say.** (EXECUTED; the consequence is INFERRED)

- *Integers typed `number`.* 155 of GitHub's properties are `number` and are integers in meaning: `perPage` 37, `page` 29, `issue_number` 23, `pullNumber` 19, `comment_id` 8. Spec 170 coerces `number` to a finite float; a float sent as `42.0` where a server expects an ID depends on the server tolerating it.
- *Two naming styles in one server.* Of GitHub's properties 94 are camelCase (`pullNumber`, `perPage`) and 165 snake_case (`issue_number`, `comment_id`); Alibaba is camelCase (779). Spec 170 gives a kebab alias only for snake_case, so on GitHub an agent writes `--pullNumber 5 --issue-number 7` in one session.
- *Free maps.* 28 properties are objects with no declared properties; Alibaba's include `additionalProperties: {"type": "string"}` maps, which have a natural `--x key=value` repeated form that the table does not offer.

**F6. Annotations are sparse outside GitHub.** (EXECUTED) GitHub: all 149 tools carry a `title`; `readOnlyHint` true on 69 and false on 80; `destructiveHint` true on 20 and false on 34; 28 tools that are not read-only carry no `destructiveHint`; `idempotentHint` false on 145. Alibaba: no annotations on any of 203 tools. Docker: 24 of 755 tools carry annotations, 20 of them `readOnlyHint: true`. 20 GitHub tools multiplex several operations behind a `method` enum (`issue_write`, `projects_write`, `pull_request_review_write`, `actions_list` …), so one tool name hides up to six verbs, read-only and writing alike in some (`disclosure.json`, "multiplexed_method_tools").

### Part B — the cost of each disclosure level

**F7. From 140,000 estimated tokens preloaded to about 100 for the first listing.** (EXECUTED, `disclosure.py`; combined catalog, 1,107 tools on 30 servers; `ls` levels use spec 170's projection `/.vfs/mcp/<server>/tools/<tool>`)

| Level | Bytes | Est. tokens | Share of level 1 | Times smaller |
|---|---|---|---|---|
| 1 every full schema preloaded | 577,934 | 140,303 | 100% | 1 |
| 1+ the same with annotations and `outputSchema` | 759,999 | 185,819 | 131.5% | 0.8 |
| 2 names only, one per line | 24,059 | 6,015 | 4.16% | 24 |
| 3 name and first sentence of the description | 90,914 | 22,328 | 15.7% | 6.4 |
| 4a `ls /.vfs/mcp` (30 server names) | 412 | 103 | 0.07% | 1,403 |
| 4b `ls` of one server's tools, median over servers | 212 | 53 | 0.04% | 2,726 |
| 4b `ls` of one server's tools, largest (Zscaler, 302 names) | 7,853 | 1,964 | 1.36% | 74 |
| 4c every path, recursive | 58,482 | 14,621 | 10.1% | 9.9 |
| 5 one tool's JSON manifest, median of the 495 full-schema tools | 612 | 153 | 0.11% | 944 |
| 5 the same, p90 | 1,610 | 403 | 0.28% | 359 |
| 5 the same, max (`github/projects_write`) | 7,240 | 1,810 | 1.25% | 80 |

The 1,107-tool total understates a fully described catalog: 612 of its tools have thin or no schemas (F1). The three full-schema servers alone (GitHub, Alibaba, Okta; 460 tools) are 406,929 bytes.

**F8. vfs's own answers at the search-first level cost about 2 KB.** (EXECUTED, `retrieval_bytes.json`; rendered with `str(result)` as the model would read it) On the combined corpus with parameter-bearing manifests (V2, below): `search` with `limit=5` renders a median of 2,062 bytes (max 3,862); one manifest file is a median of 229 bytes (p90 875, max 4,992); `ls /tools` renders 621 bytes; `ls /tools/github` 5,706 bytes (vfs prints full paths, about twice a basename listing). `grep` on a query's key words, one call per word, renders a median of 4,059 bytes (V1) to 5,377 (V2) and up to 25,193, and returns a median candidate set of 75 to 101 files. A search followed by one read is about 2.3 KB, roughly 600 estimated tokens, against 578 KB for level 1: about 250 times smaller per discovery step (INFERRED arithmetic from the EXECUTED sizes).

### Part C — tools as searchable files

**F9. The setup.** (EXECUTED, `retrieval.py`) Each tool is one file at `/tools/<server>/<tool>.md`, written in one batch `write` on a `VirtualFileSystem`'s async face. Manifest variants: V1 is a heading with the tool name, a `server:` line and the description; V2 adds one line per parameter (name, type, required or optional, enum members, description); V3 adds two example requests per tool, written for GitHub's 149 tools before measurement (`github_examples.json`). Backends, each a `DatabaseStorage` on a private in-memory SQLite through public constructors: `mem-overlay` (`InMemoryStorage()`, files written, no rebuild), `lexical` (`DatabaseStorage(url=…:memory:, embedder=None)`, rebuilt), `hash-vector` (the hashing embedder alone, `Ranker(fusion=Convex({"vector": 1.0}))`, rebuilt), `mem-fused` (`InMemoryStorage()` rebuilt: its default hashing embedder fused 0.5/0.5 with lexical). `grep`: one case-insensitive fixed-string `grep` per key word over `/tools`, `output_mode="files"`, files ranked by how many distinct key words they contain, ties sharing the mean of their positions. The query set is 65 phrasings (46 targeting GitHub, 19 targeting eleven other servers), each with a target and acceptable alternates; 19 are paraphrases that share no word with the target tool's name (computed, not judged). Two corpora: combined (1,107 tools, V1 and V2) and GitHub only (149 tools, V1, V2 and V3, its 46 queries).

**F10. The vector leg that runs offline is not semantic, and model2vec needs a download.** (EXECUTED, READ) `model2vec` is importable in the environment but no model is cached (`~/.cache/huggingface` absent, `HF_HOME` unset), and `model2vec.py:6-9` says the first use of a named model downloads it from the Hub; it was skipped. The hashing provider runs offline; its own docstring says "It cannot rank by meaning and never pretends to" (`hashing.py:6`). It was measured as the only vector leg available, and it is a hashed bag of tokens and bigrams at 64 dimensions.

**F11. Retrieval, combined corpus (1,107 tools, 65 queries).** (EXECUTED)

| Manifest | Method | hit@1 | hit@3 | hit@5 | hit@10 | MRR@10 |
|---|---|---|---|---|---|---|
| V1 name + description | search, lexical | 0.477 | 0.569 | 0.677 | 0.708 | 0.547 |
| V1 | search, overlay (no rebuild) | 0.477 | 0.569 | 0.677 | 0.708 | 0.547 |
| V1 | search, hash vector | 0.092 | 0.185 | 0.200 | 0.262 | 0.147 |
| V1 | search, fused (InMemoryStorage rebuilt) | 0.354 | 0.462 | 0.538 | 0.600 | 0.427 |
| V1 | grep key words | 0.323 | 0.554 | 0.615 | 0.708 | 0.466 |
| V2 + parameters | search, lexical | 0.492 | 0.677 | 0.738 | 0.769 | 0.591 |
| V2 | search, overlay (no rebuild) | 0.492 | 0.692 | 0.723 | 0.769 | 0.594 |
| V2 | search, hash vector | 0.062 | 0.092 | 0.092 | 0.108 | 0.076 |
| V2 | search, fused (InMemoryStorage rebuilt) | 0.369 | 0.477 | 0.508 | 0.600 | 0.440 |
| V2 | grep key words | 0.246 | 0.538 | 0.646 | 0.662 | 0.443 |

**F12. Retrieval, GitHub only (149 tools, 46 queries), with examples.** (EXECUTED)

| Manifest | Method | hit@1 | hit@3 | hit@5 | hit@10 | MRR@10 |
|---|---|---|---|---|---|---|
| V1 | search, lexical | 0.478 | 0.543 | 0.630 | 0.674 | 0.531 |
| V1 | search, fused | 0.457 | 0.543 | 0.565 | 0.587 | 0.504 |
| V1 | search, hash vector | 0.196 | 0.217 | 0.239 | 0.304 | 0.220 |
| V1 | grep | 0.239 | 0.522 | 0.630 | 0.739 | 0.453 |
| V2 | search, lexical | 0.478 | 0.696 | 0.717 | 0.739 | 0.587 |
| V2 | search, fused | 0.435 | 0.652 | 0.674 | 0.717 | 0.548 |
| V2 | search, hash vector | 0.109 | 0.239 | 0.261 | 0.348 | 0.175 |
| V2 | grep | 0.152 | 0.565 | 0.587 | 0.696 | 0.396 |
| V3 + two examples | search, lexical | 0.848 | 0.913 | 0.935 | 0.957 | 0.887 |
| V3 | search, overlay | 0.848 | 0.913 | 0.935 | 1.000 | 0.891 |
| V3 | search, fused | 0.848 | 0.891 | 0.913 | 0.978 | 0.884 |
| V3 | search, hash vector | 0.174 | 0.304 | 0.304 | 0.457 | 0.236 |
| V3 | grep | 0.391 | 0.826 | 0.848 | 0.891 | 0.646 |

**F13. The failure is vocabulary: named phrasings are found, paraphrases mostly are not.** (EXECUTED, `analysis.out.md`)

| Corpus, manifest, method | Named (n) hit@1 / hit@5 | Paraphrase (n) hit@1 / hit@5 |
|---|---|---|
| combined, V1, lexical | (46) 0.609 / 0.804 | (19) 0.158 / 0.368 |
| combined, V2, lexical | (46) 0.630 / 0.848 | (19) 0.158 / 0.474 |
| combined, V2, grep | (46) 0.304 / 0.826 | (19) 0.105 / 0.211 |
| GitHub, V2, lexical | (29) 0.621 / 0.862 | (17) 0.235 / 0.471 |
| GitHub, V3, lexical | (29) 0.828 / 0.931 | (17) 0.882 / 0.941 |

The misses, read from `per_query.jsonl`, are word-form and synonym gaps: "add the bug label" misses `update_issue_labels` (label against labels), "react with a thumbs up" misses `add_issue_reaction` (react against reaction), "bookmark this project" misses `star_repository`, "make my own copy of someone else's repo" lands on `alfresco/copy_node`, "list merge requests in a Codeup repository" lands on GitHub's `merge_pull_request` because Alibaba calls them change requests. `tokenize` splits `list_pull_requests` into its parts (`lexical.py:148-150`) but does no stemming, so plural and verb forms do not meet (INFERRED from the misses and the docstring).

**F14. More servers cost precision for the same queries.** (EXECUTED) The 46 GitHub queries, lexical, hit@1: 0.478 against 149 GitHub tools, 0.370 against all 1,107 tools (V1); 0.478 and 0.413 (V2); hit@5 0.630 to 0.609 (V1), 0.717 to 0.674 (V2). The 19 other-server queries score higher in the combined corpus (V2 hit@1 0.684, hit@5 0.895), because most of them name their service ("in Stripe", "in Okta") and the manifest's `server:` line carries that word.

**F15. Parameter text helps ranked search and hurts grep.** (EXECUTED) V1 to V2, combined, lexical: hit@3 0.569 to 0.677, hit@5 0.677 to 0.738, MRR 0.547 to 0.591, hit@1 almost unchanged. Grep's hit@1 falls 0.323 to 0.246 and its median candidate set grows from 75 to 101 files, because words like `repository`, `owner` and `issue` now occur in most GitHub parameter lists and grep has no term weighting to discount them.

**F16. Examples move the GitHub numbers most, and part of that is leakage.** (EXECUTED, `analysis.py`) V2 to V3, lexical, hit@1 0.478 to 0.848 and paraphrase hit@1 0.235 to 0.882. The examples and the queries were written by one researcher in one sitting. As a control, each GitHub query was put in a bucket by the number of key words it shares with the examples of its acceptable tools:

| Bucket | n | V2 lexical hit@1 / hit@5 | V3 lexical hit@1 / hit@5 |
|---|---|---|---|
| echo (two or more key words shared with an example) | 33 | 0.515 / 0.788 | 0.848 / 0.939 |
| fresh (one or none shared) | 13 | 0.385 / 0.538 | 0.846 / 0.923 |

The gain holds in the fresh bucket, but that bucket is small and still shares the researcher's intuitions about how tasks are phrased (for example, the example "bookmark the project" and the query "bookmark this project so I can find it later" share only `bookmark` and `project`, which lands that query in echo; "who am I logged in as" and "who am I authenticated as" share no key word). The V3 figures are an upper bound on what examples written by a tool's author would give.

**F17. The overlay answers like the postings; the default fused rebuild answers worse.** (EXECUTED) `InMemoryStorage` searched straight after the write, with no rebuild, matched the rebuilt lexical leg on 262 of 268 query-variant pairs and on every hit@1 figure; each of the six differences moves an acceptable tool by one or two places at rank 2 or lower. Rebuilding the same `InMemoryStorage` fuses in its default hashing embedder (`memory.py:37-39`) and lowers combined hit@1 from 0.477 to 0.354 (V1) and from 0.492 to 0.369 (V2); the hash leg puts files with no matching word into the list and the 0.5 weight lets them outrank lexical hits.

## What this means for a vfs code mode

Everything in this section is INFERRED from the findings above.

**Start the model at the listing, not the catalog.** Preloading the combined catalog costs about 140,000 estimated tokens (F7), and GitHub's alone about 39,000, or 84,000 with its output schemas (F2). `ls /.vfs/mcp` costs about 100 and one server's tool names a median of about 50 (F7). The model's first view should be the server listing plus one line saying how to find a tool (`search` over `/.vfs/mcp`, `cat` a manifest, `--help`). Level 2 (every name, 6,000 tokens) and level 3 (names and first sentences, 22,000) are worth offering only for a small catalog, a single server below a few dozen tools, where they fit and save a search round trip. At the reference deployment's 150,000 agent verb calls a day, a level-1 preamble is paid per session or per turn depending on caching; a listing plus a 2 KB search per discovery (F8) is paid only when a tool is needed.

**Make `search` over the catalog the discovery verb, and keep `grep` for exact names.** On the same files, ranked lexical search beats key-word grep at hit@1 by 0.15 to 0.25 (F11, F12) and returns a ranked 2 KB answer where grep returns a 4 to 25 KB unranked candidate set (F8). `grep` stays the right verb when the model already knows a name (`grep -l pull_request /.vfs/mcp`). Spec 170 §6 serves `grep` over rendered manifests and leaves ranked search over catalogues as "a later item"; these numbers argue for bringing ranked search over manifests forward to the same landing, because the catalog is exactly the region where an agent has a description of what it wants and not the name of what does it.

**Write manifests for search, in this order of value.** (a) The description is the floor and carries the vocabulary of whoever wrote it (F13). (b) Parameter lines add recall at depth 3 to 5 (F15) and are needed anyway for `--help`. (c) Short example requests in the words a user would use gave the largest gain measured here (F16), even after the leakage control; since a server's own text is untrusted (spec 170 §6), the examples should be written on the host side, by the person who registers the server or by a stored overlay file beside the projected manifest, not taken from the server. (d) The `server:` provenance line, which spec 170 requires for trust, also carries the service name that most non-GitHub queries used (F14). The measured shape is a Markdown manifest of a median 229 bytes with parameters (F8); budgets in the low kilobytes per manifest cost nothing at this scale.

**Do not fuse a non-semantic vector leg into catalogue search.** The hashing provider lowered every catalogue result it touched (F17). A catalogue mount should rank with the lexical leg alone unless a real embedding provider is configured; the vocabulary gap of F13 is what a semantic leg would be for, and it is untested here (below).

**The flag table fits real schemas; three amendments are worth making before it is built.** 97% of properties and 89.5% of tools take plain words (F3, F4); no tool needs `--json` to be reachable; dotted flags for nested objects would rescue one tool of 495, so they do not earn a later pass. The amendments: coerce an integer literal under `number` to a JSON integer, because 155 of GitHub's `number` properties are IDs and page sizes (F5); offer a kebab alias for camelCase as well as snake_case, or none for either, so one server's flags read one way (F5); and consider `--x key=value` for objects whose `additionalProperties` is a scalar (F5). The 27 tools with a required JSON-valued property (F4) are where `--help` must show a JSON example, and spec 170's `--help` already renders one line per property.

**Annotations cannot carry governance alone.** Only GitHub annotates, and 28 of its 80 non-read-only tools carry no `destructiveHint` (F6); 20 of its tools multiplex read and write operations behind a `method` enum. Who may call a tool has to stay where spec 170 puts it, in the grants on the entry, and a vfs code mode cannot infer "safe to run" from server hints.

## What this study does not settle

- **A semantic vector leg.** No offline semantic embedder was available without a download (F10), so whether a real embedding closes the paraphrase gap of F13 on tool manifests is untested. The hashing figures are a floor, not a vector result.
- **Model behaviour.** No model chose tools here. Hit@k measures whether the right manifest is in what vfs returns, not whether a model reading those 2 KB picks the right tool and fills its flags, nor how a model does with 140,000 tokens of preloaded schemas.
- **Validity of the labels.** One researcher wrote the 65 queries, their alternates and the 298 examples, in one sitting. The queries lean towards GitHub (46 of 65) and towards English; Alibaba's 50 descriptions with Chinese text were not queried. n is small: a single query moves a 46-query hit@1 by 0.022 and a 13-query bucket by 0.077. The figures compare manifest variants and methods on one fixed set; they are not an estimate of production accuracy.
- **Token counts.** Every token figure is chars/4. For Alibaba's Chinese text, chars/4 undercounts tokens, and JSON punctuation tokenises differently from prose; the byte columns are exact.
- **Grep ranking.** Ranking grep hits by distinct key words with mean-position ties is one reasonable reading of "grep on the key words"; an agent that chains greps, or greps names first, would score differently.
- **Catalog freshness and fidelity.** The Docker lists are what each vendor submitted; 310 are a lossy flat format and 302 carry no arguments, and the census of those is reported apart. GitHub's 149 are every snapshot, more than its default toolsets expose.
- **The supervisor spike and legacy-server pieces of spec 170's pre-build study** (§ Status, items 1 and 3) are untouched; this study is item 2 only.

## One line

Real catalogs cost about 39,000 estimated tokens per large server and 140,000 for 1,107 tools, while a vfs listing costs about 100 and a search plus one manifest about 600; vfs lexical search over one-file-per-tool manifests finds the right tool in the top five 74% of the time (85% when the query uses the tool's words, 47% when it paraphrases), host-written example requests lift GitHub's top-one rate from 0.48 to 0.85, and spec 170's flag table fits 97% of real properties with no tool needing `--json`.
