# Finding the right tool: retrieval over tool catalogs

The question as this study received it: what is the evidence on how an agent finds the right tool among hundreds or thousands, given that vfs proposes tools are files, found with the same `glob`, `grep` and `search` (lexical BM25 plus vector, fused) as every other file? The study covers the papers that measure selection accuracy against tool count and retrieval quality over tool corpora, the implementations that ship a tool search (what they index, how they rank, how many tools they return, whether a hierarchy can be browsed), the evidence on what makes a tool description findable, and what all of this means for the file an MCP or host tool becomes in a vfs namespace.

A note on access. From this session `arxiv.org` and `huggingface.co` did not resolve (EXECUTED: WebFetch returned `getaddrinfo ENOTFOUND` for both, and `curl` to arXiv, the arXiv export API, Semantic Scholar, ACL Anthology and alphaXiv all returned no connection). Paper figures below are therefore READ from web-search excerpts of the papers' own abstract, HTML or PDF pages, as returned by the search tool on 2026-11-23, and each is labelled "READ (search excerpt)". Where excerpts disagreed or a figure was traceable only to a secondary write-up, that is said. Implementation claims come from clones and are cited by file and line.

## Sources

Clones (shallow, `origin/HEAD` default branch, read 2026-11-23):

| Clone | URL | Branch | Commit | Commit date | Licence |
|---|---|---|---|---|---|
| `/home/user/langgraph-bigtool` | https://github.com/langchain-ai/langgraph-bigtool | main | b996f8369fb3c318f511759ce73b0e6681bdfd69 | 2026-11-16 | MIT (`LICENSE`) |
| `/home/user/mcp-gateway` (Docker MCP Gateway) | https://github.com/docker/mcp-gateway | main | 4b5180c5ba8e1b456c53b36b7f90f17964131a16 | 2026-11-19 | MIT (`LICENSE`) |
| `/home/user/spring-ai-tool-search-tool` | https://github.com/spring-ai-community/spring-ai-tool-search-tool | main | d8898b6450907b94f748d384d4d35c15bd62a546 | 2026-06-14 | Apache-2.0 (`LICENSE.txt`) |
| `/home/user/mcp-gateway-registry` | https://github.com/agentic-community/mcp-gateway-registry | main | a2e4a409a10ace87d67d8f428fafc46a1ff33c7f | 2026-11-23 | Apache-2.0 (`LICENSE`) |

This repository: `/home/user/vfs` at f0849c5 (2026-11-23): `src/vfs/models/lexical.py`, `src/vfs/models/chunk.py`, `src/vfs/models/chunking.py`, `src/vfs/storage/ranking.py`, `src/vfs/storage/backends/database/search.py`, `src/vfs/storage/backends/memory.py`, `context/specifications/active/170-tools-and-mcp-servers-as-views/spec.md`.

Experiment: `studies/experiments/06-tool-manifest-findability/run.py` and its saved `output.txt`.

Pages (all read 2026-11-23; papers through search excerpts as noted above):

- RAG-MCP, Gan and Sun, arXiv 2505.03275 (https://arxiv.org/abs/2505.03275).
- ToolRet, "Retrieval Models Aren't Tool-Savvy", ACL Findings 2025, arXiv 2503.01763 (https://aclanthology.org/2025.findings-acl.1258/).
- MCP-Zero, Fei, Zheng and Feng, arXiv 2506.01056 (https://arxiv.org/abs/2506.01056; code https://github.com/xfey/MCP-Zero).
- ScaleMCP, Lumer et al., arXiv 2505.06416 (https://arxiv.org/abs/2505.06416).
- Toolshed, Lumer et al., arXiv 2410.14594 (https://arxiv.org/abs/2410.14594).
- Tool2Vec, Moon et al., arXiv 2409.02141 (https://arxiv.org/abs/2409.02141; https://github.com/SqueezeAILab/Tool2Vec).
- Re-Invoke, Chen et al., Findings of EMNLP 2024 (https://aclanthology.org/2024.findings-emnlp.270/; https://research.google/blog/re-invoke-tool-invocation-rewriting-for-zero-shot-tool-retrieval/).
- Tool documentation enables zero-shot tool use, Hsieh et al., arXiv 2308.00675 (https://arxiv.org/abs/2308.00675).
- Gorilla / APIBench, Patil et al., arXiv 2305.15334 (https://arxiv.org/abs/2305.15334).
- ToolLLM, Qin et al., ICLR 2024, arXiv 2307.16789 (https://arxiv.org/abs/2307.16789).
- AnyTool, Du et al., arXiv 2402.04253 (https://arxiv.org/abs/2402.04253).
- Less is More, Paramanayakam et al., arXiv 2411.15399 (https://arxiv.org/abs/2411.15399).
- LongFuncEval, arXiv 2505.10570 (https://arxiv.org/abs/2505.10570).
- How Many Tools Should an LLM Agent See?, Repantis et al., arXiv 2605.24660 (https://arxiv.org/abs/2605.24660).
- Completeness and Cost of Retrieval Structures for Multi-Tool Requests, arXiv 2610.41905 (https://arxiv.org/abs/2610.41905).
- SING, arXiv 2606.16591 (https://arxiv.org/abs/2606.16591).
- LiveMCPBench, arXiv 2508.01780 (https://arxiv.org/abs/2508.01780); MCP-Bench, ICLR 2026, arXiv 2508.20453 (https://github.com/Accenture/mcp-bench); MCPToolBench++, arXiv 2508.07575 (https://github.com/mcp-tool-bench/MCPToolBenchPP).
- MCP Tool Descriptions Are Smelly!, Hasan et al., arXiv 2602.14878 (https://arxiv.org/abs/2602.14878).
- Tool Preferences in Agentic LLMs are Unreliable, Faghih et al., EMNLP 2025, arXiv 2505.18135 (https://aclanthology.org/2025.emnlp-main.1060/).
- ToolHijacker, "Prompt Injection Attack to Tool Selection in LLM Agents", arXiv 2504.19793, NDSS 2026 (https://www.ndss-symposium.org/wp-content/uploads/2026-s675-paper.pdf).
- Attractive Metadata Attack, Mo et al., NeurIPS 2025, arXiv 2508.02110 (https://github.com/SEAIC-M/AMA).
- MCPTox, arXiv 2508.14925, AAAI (https://ojs.aaai.org/index.php/AAAI/article/view/40895/44856).
- Anthropic tool search tool docs (https://platform.claude.com/docs/en/agents-and-tools/tool-use/tool-search-tool) and engineering post (https://www.anthropic.com/engineering/advanced-tool-use), through search excerpts; another study in this folder covers Anthropic directly.
- OpenAI tool search guide (https://developers.openai.com/api/docs/guides/tools-tool-search), through search excerpts.
- Spring AI: blog (https://spring.io/blog/2025/12/11/spring-ai-tool-search-tools-tzolov/, fetched directly) and docs (https://docs.spring.io/spring-ai/reference/api/tools/tool-search-tool.html, search excerpt).
- Vendor benchmarks, all vendor-run: Stacklok (https://stacklok.com/blog/stackloks-mcp-optimizer-vs-anthropics-tool-search-tool-a-head-to-head-comparison/), StackOne (https://www.stackone.com/blog/mcp-tool-search-bm25-tfidf-hybrid/), MCPProxy (https://mcpproxy.app/blog/2026-03-19-bm25-accuracy-hybrid-search/), through search excerpts.

## Findings

### F1. Selection accuracy falls as the number of tools in context grows, and every measurement agrees on the direction

- READ (search excerpt), RAG-MCP: an "MCP stress test" varies the number of candidate MCP servers from 1 to 11,100 with the correct one placed at every position; retrieving with a vector index and injecting only the top server's schema "more than triples tool selection accuracy (43.13% vs 13.62% baseline)" and cuts prompt tokens by over 50%. The 13.62% baseline is the paper's "Blank Conditioning" (all descriptions in context); an intermediate "Actual Match" (keyword) scored 18.20%. A critique on pith.science notes the method injects top-1 only, so its accuracy is capped by top-1 retrieval recall. Thresholds such as "degrades past 100 tools" circulate in secondary write-ups and could not be traced to the paper's text.
- READ (search excerpt), LongFuncEval (IBM, 2025): adding distractor functions to BFCL to grow the catalog from 8K to 120K tokens, and moving the correct tool's position, drops accuracy by 7.59% to 85.58% across models (Mistral-large excluded), attributed to formatting failures and hallucination; 128K-context models still degrade.
- READ (search excerpt), LiveMCPBench: 70 servers, 527 tools, 95 tasks; the best of 12 models (Claude Sonnet 4) reached 78.95% success, most others 30–50%; the authors attribute nearly half of all failures to retrieval errors, "the main bottleneck".
- READ (search excerpt), How Many Tools Should an LLM Agent See? (2026): on BFCL (370 tools) an adaptive stopping policy reaches about 90.3% coverage while showing about 7 tools on average, against 90.8% when showing 50; a shorter list raised the model's tool-choice accuracy (93.1% vs 87.1% with a fixed 5). On ToolBench (3,251 tools) a fixed top-5 has higher aggregate coverage (64.7% vs 61.9%) but finds nothing when the right tool ranks 6th to 20th.
- READ (search excerpt), Less is More (2024): letting the model first describe the tools it needs, then matching that description to tools at one of three levels (tool, cluster, whole set), improves success and cuts execution time by up to 70% and power by up to 40% on edge hardware.
- READ (search excerpt), Anthropic's engineering post: with the tool search tool, Opus 4 went from 49% to 74% and Opus 4.5 from 79.5% to 88.1% on Anthropic's internal MCP evaluations, with about 85% fewer tokens. These are the vendor's own figures.
- INFERRED: the direction is settled (more tools in context, lower accuracy; a retrieved shortlist of roughly 5 to 10 beats both 1 and 50). The size of the effect depends heavily on how similar the distractors are, which no two studies hold constant.

### F2. Tool retrieval is a hard IR problem in its own right, and plain BM25 over names and descriptions is weak at scale

- READ (search excerpt), ToolRet: 7.6k retrieval tasks over a 43k-tool corpus assembled from existing datasets; "the strongest model on conventional IR benchmarks scored only 33.83" NDCG@10. Training on the released ToolRet-train improves every IR model (one report: NV-Embed-v1 from 33.83 to 42.71), and better retrievers raise ToolBench pass rates for GPT-3.5 and ToolLlama.
- READ (search excerpt), ToolLLM: 16,464 RapidAPI APIs in 49 categories; its trained dense API retriever "consistently outperforms BM25 and Ada Embedding" by NDCG. Gorilla: swapping the oracle retriever for BM25 or GPT-Index at evaluation drops accuracy sharply (the arXiv version states 21.50% on TorchHub and 47.57% on HuggingFace; the NeurIPS version gives different figures).
- READ (search excerpt), vendor benchmarks, none independently replicated: Stacklok, 2,792 tools, Claude Sonnet 4.5 choosing in every arm: its hybrid (embedding plus BM25) optimizer selected correctly 94% (retrieval 98%), Anthropic's tool search BM25 variant 33.7% (retrieval 47.85%) and regex variant 30.0% (39.0%). StackOne, 270 tools in 11 categories, 2,700 cases: BM25 top-1 14%, BM25 plus TF-IDF 21%, embeddings 38%. MCPProxy, 916 tools: BM25 top-1 14%, hybrid 94%, and BM25 "competitive" under about 100 tools. A summary attributes to Arcade 56% (regex) and 64% (BM25) over 4,027 tools.
- INFERRED: the reason is the vocabulary gap. A task is phrased as an intent ("who do I escalate a sev1 to"); a tool is described as an operation ("get escalation procedures"). Lexical retrieval needs shared words; dense retrieval bridges some of the gap; training on query–tool pairs or adding queries to the tool's text bridges more (F4). F10 reproduces the gap on vfs's own lexical leg.

### F3. What shipped tool searches index, how they rank, and how many tools they return

READ, from the clones and docs as cited:

| System | Unit indexed | Text indexed | Ranking | Returned | Hierarchy |
|---|---|---|---|---|---|
| langgraph-bigtool | one tool | `"{name}: {description}"` in the README recipe (`README.md:80-98`); any LangGraph Store index | the Store's semantic search (`tools.py:22-34`) | `limit=2` default (`tools.py:17`, `graph.py:49`) | none built in; README shows a `Literal` category argument as an alternative retriever (`README.md:175-197`) |
| Spring AI tool search (Lucene) | one tool | description only, analysed; name a non-analysed `StringField` (`LuceneToolSearcher.java:347-353`) | phrase query OR boolean-terms query on the description (`:355-373`), min-score threshold | 5 suggested to the model (`ToolSearchToolCallAdvisor.java:96`), searcher default 10 (`LuceneToolSearcher.java:76`) | none; a `categoryFilter` parameter is offered to the model (`ToolSearchToolCallAdvisor.java:97`) but no searcher reads it (EXECUTED: `grep -rn categoryFilter tool-searchers` returned nothing) |
| Spring AI (vector, regex) | one tool | vector: the description text (`VectorToolSearcher.java:139-140`); regex: name and description, the query turned into an OR of its words (`RegexToolSearcher.java:42-56`) | cosine with threshold; regex match | as above | none |
| Docker MCP Gateway `mcp-find` | one **server** | server name ×4, title ×3, description ×1, each tool name ×2, each tool description ×1, by token repetition as a BM25F approximation (`findmcps.go:69-129`) | Okapi BM25, k1 1.5, b 0.75 (`:156-197`); the index is rebuilt on every query to see newly activated servers (`:200-215`); or embeddings when an embeddings client is configured, never both (`reload.go:97-103`) | 10 servers default (`:240-242`) | yes, two steps: `mcp-find` finds servers, `mcp-add` activates their tools (`dynamic_mcps.go:19-26`) |
| mcp-gateway-registry `search_registry` | server, agent, skill or custom record, with matching tools inside | embedding text: server name, description, tags, every model-visible tool's name and description, metadata key–values (`search_repository.py:1211-1235`); keyword: regex hits with boosts path +5, name +3, description +2, tags +1.5, metadata +1, tools +1 (`:770-786`) | vector and keyword lists fused by reciprocal rank fusion, k 60 (`:155`, `:323-367`); tools within a hit graded by name hit 0.5, description hit 0.3, plus coverage (`:475-517`) | 10 (`server.py:1143-1145`); the deprecated `intelligent_tool_finder` 5, max 50 (`server.py:1404-1431`) | yes: server then its matching tools; one search over servers, tools, agents and skills |
| Anthropic tool search | one tool | name, description, argument names, argument descriptions (docs, search excerpt) | regex (Python `re.search`, 200 chars) or BM25 (natural language, 500 chars) | about 5 by default (secondhand) | none; deferred tools by `defer_loading` |
| OpenAI tool search | one function | not documented in the excerpts; the guide asks for namespaces and MCP servers with "clear, high-level descriptions" (search excerpt) | hosted, unspecified | unspecified | yes: namespaces and MCP servers are the surfaces the model searches and loads |
| RAG-MCP, MCP-Zero, ScaleMCP (papers) | server (RAG-MCP), server then tool (MCP-Zero), tool documents with weighted fields (ScaleMCP) | descriptions; MCP-Zero embeds server and tool descriptions with text-embedding-3-large | dense | top-1 (RAG-MCP); top servers then tools (MCP-Zero) | MCP-Zero and ScaleMCP's server source of truth |

- READ: Spring's own tool description tells the model that "the search queries against tool names, descriptions, and parameter information" (`ToolSearchToolCallAdvisor.java:91`), but the Lucene index tokenizes only the description and holds the name as an exact-match field, and no searcher indexes parameters. The claim and the index disagree.
- READ: the Spring blog's benchmark is 28 tools (3 relevant, 25 dummies), one task, three models, not averaged; token savings 34–64% with Lucene, 47–63% with vectors; no accuracy metric is reported ("illustrative").
- READ: the registry filters results by the caller's rights after ranking (`search_routes.py:860-880`: `_user_can_access_server`, then `filter_tools_for_user` on the matched tools), so a caller can receive fewer than the requested number.

### F4. Adding example queries to a tool's text (document expansion) is the most reliable improvement found

- READ (search excerpt), Tool2Vec: embed example user queries for each tool and average them as the tool's vector, instead of embedding the description; improvements "up to 27.28 in Recall@K" on ToolBench; a second-stage ToolRefiner trained on Tool2Vec beats one trained on description embeddings.
- READ (search excerpt), Re-Invoke (Google, zero-shot): generate synthetic queries per tool document at index time, extract intents from the user query at query time, rank by multi-view similarity; about 20% relative nDCG@5 gain single-tool and 39% multi-tool on ToolE over BM25 and HyDE. A 2026 paper lists it as a ToolRet baseline that is not the top method.
- READ (search excerpt), Toolshed: "Advanced RAG-Tool Fusion" enhances tool documents (including generated questions) and adds query planning and reranking; the excerpts that reached this session report 46%, 56% and 47% absolute Recall@5 gains on ToolE single-tool, ToolE multi-tool and Seal-Tools, though one excerpt attached those figures to ScaleMCP, so the attribution should be checked in the PDF.
- READ (search excerpt), ScaleMCP: 5,000 financial-metric MCP servers, 10 LLMs, 5 embedding models, 5 retriever types; proposes Tool Document Weighted Average (TDWA), a normalized weighted average of per-field embeddings; in plain vector search simple concatenation of the fields beat both TDWA variants (0.634 NDCG, 0.912 recall at top-1); a summary reports Recall@5 about 0.94 with TDWA and reranking. ScaleMCP also treats the MCP servers as the source of truth and syncs the index by CRUD on change.
- READ (search excerpt), ToolRet: training on query–tool pairs lifts every retriever (F2).
- INFERRED: the common mechanism is to put the user's vocabulary into the tool's document. It is cheap at index time, needs no model change, and helps the lexical leg as much as the vector leg, because BM25 can only match words that are present.

### F5. Description quality decides both whether a tool is found and whether it is chosen, and descriptions are mostly poor

- READ (search excerpt), Hsieh et al. (2023): zero-shot prompts with tool documentation match few-shot demonstrations on existing benchmarks; with hundreds of APIs, documentation significantly beats demonstrations, which cover too few tools.
- READ (search excerpt), Smelly descriptions (2026): 856 tools from 103 MCP servers scored against a six-component rubric; 56% have an "Unclear Purpose" smell and 2.9% are free of every smell; augmented descriptions gave a median 5.85-point task-success gain on MCP-Universe, raised execution steps, and made results worse in some cases (figures for the augmentation come from secondary summaries).
- READ (search excerpt), Tool Preferences are Unreliable (EMNLP 2025): description edits such as claiming active maintenance, adding usage examples, name-dropping and assertive wording shift selection by up to 10× for GPT-4.1 and Qwen2.5-7B when several tools fit; order of presentation biases choice too. The authors' point is that a description is decoupled from what the tool does.
- READ, corpus used in F10: in the registry's own example records, 22 of 81 tools carry "No description available." (all 21 tools of the SRE gateway record and one Jira tool) (EXECUTED: counted by `run.py`).
- INFERRED: a description-only index cannot find a tool with no description, and a free-text description is both the main ranking signal and the easiest field to game (F7).

### F6. Hierarchy (server, then tool) saves tokens; it does not by itself make retrieval more complete

- READ (search excerpt), MCP-Zero: the model writes a request naming the server and the tool it wants; routing scores servers first, then tools within the top servers, combining the two cosines as `(s_server × s_tool) × max(s_server, s_tool)`; dataset MCP-tools, 308 servers and 2,797 tools; claims a 98% token reduction with preserved accuracy (the authors' own claim).
- READ (search excerpt), AnyTool: a meta-agent, category agents and tool agents navigate ToolLLM's 16k APIs as a tree; a summary reports +35.4% pass rate over ToolLLM on ToolBench.
- READ (search excerpt), Completeness and Cost of Retrieval Structures (2026): on 345 AppWorld queries and 103 MCP-Bench tasks, flat lexical, flat dense, query decomposition, server-then-tool matching and dependency-graph retrieval all complete at most 9.6% (AppWorld) and 36% (MCP-Bench) of requests at k = 16, mostly by missing the target tool at the first step; only a trained set-level retriever, or LLM-navigated hierarchical search in the AnyTool style at 31 to 38 LLM calls and about five minutes a query, reaches high completeness.
- READ (search excerpt), SING (2026): an intention graph over tools improves Global Recall@5 by up to 59.8% and cuts schema exposure by 99.8%.
- READ: Docker and the registry rank servers and then expose or grade tools inside them (F3); OpenAI's guide tells developers to group deferred functions under described namespaces; Less is More picks a search level (tool, cluster, all).
- INFERRED: hierarchy earns its place as a browsing aid and a context budget (load one server's tools, not all), and as a scoping filter for search. The evidence that a mechanical server-then-tool match beats flat retrieval is absent; the one controlled comparison found it no better. A model walking the tree itself (AnyTool) is complete but expensive.

### F7. Poisoned and over-attractive descriptions win retrieval and selection, and prompt-level defences do not stop them

- READ (search excerpt), ToolHijacker (NDSS 2026): a malicious tool document built from a retrieval-optimized part and a selection-optimized part reaches 100% retrieval hit rate on MetaTool and a 96.43% (arXiv v1) to 96.7% (NDSS) attack success rate; StruQ and SecAlign fail (99.71% success under StruQ); a perplexity detector misses 85.71% of gradient-free documents.
- READ (search excerpt), Attractive Metadata Attack (NeurIPS 2025): black-box optimization of names, descriptions and parameter schemas makes agents call attacker tools in 81–95% of cases across ten scenarios, with little effect on the main task; the authors call for execution-level controls.
- READ (search excerpt), MCPTox: 45 real servers, 353 tools, 1,312 (later 1,348) malicious cases; average attack success 36.5% across 20 models, the highest about 72.8%; parameter tampering is the most effective paradigm (46.7%).
- READ, F5: benign wording alone moves selection up to 10×.
- INFERRED: a retriever that ranks description text ranks the attacker's text too. Nothing in BM25 or cosine distinguishes a description written to be found from one written to be true.

### F8. Freshness: where the tool text comes from, and when the index sees a change

- READ: Docker rebuilds its BM25 index on every `mcp-find` call (`findmcps.go:206-215`), which is affordable at catalog size and always fresh. The registry hashes the embedding text and skips re-embedding when unchanged (`search_repository.py:1194-1199`, `:1236-1242`). ScaleMCP syncs its index from the servers by CRUD. Spring builds a per-conversation index (`LuceneToolSearcher.java:95-98`, `:130-137`, an in-memory index per session id).
- READ, vfs spec 170: a catalog entry's `stat` shows the manifest's `content_hash` so a host can see a description change between refreshes (`spec.md:141-144`).
- INFERRED: a description that changes after it was vetted (a "rug pull") is the same event as a stale index entry; both are detected by comparing a hash.

### F9. vfs's search as it stands: what a tool file would be ranked on

- READ, `src/vfs/models/chunk.py:93-119` @ f0849c5: a chunk is built from the file's content only; the path is carried as the chunk's `file` but its text is not tokenized into the chunk. So `search` matches a tool's name only if the name is written inside the body.
- READ, `src/vfs/models/lexical.py:15-31`: the tokenizer emits each identifier whole and split on underscores and case changes (`pthread_create` gives `pthread_create`, `pthread`, `create`), with no stemming and no stop list. A tool name like `jira_add_worklog` is therefore findable both by its full identifier and by `worklog`.
- READ, `src/vfs/storage/backends/database/search.py:58-64` and `src/vfs/storage/ranking.py:100-111`: each leg aggregates chunks to entries by best chunk (MaxP) and is normalized; the default fusion is a convex sum with weight 0.5 per leg (`vector`, `lexical`), renormalized over the legs present; stored per-entry priors (`signals`) multiply the fused score.
- READ, `search.py:1-40`: entries not yet in the lexical epoch (`encoded=False`) are scored at query time from their live bodies by the same engine and formula (the overlay), so a newly written file is searchable before the next index pass.
- READ, spec 170 §1 and §6 (`spec.md:20`, `:141-147`): tools are projected as `/.vfs/tools/<name>` and `/.vfs/mcp/<server>/tools/<tool>`, whose content is the manifest (name, description, input schema, trust line, capabilities); reading never executes; remote text is cleaned and each description capped at `MANIFEST_DESCRIPTION_BUDGET`; the catalog views serve `read`, `stat`, `ls`, `tree`, `glob` and `grep` (grep over rendered manifests in memory), and ranked search over the catalogs "is a later item". As drafted, `search` does not reach tools at all.
- READ, spec 170 §1: "Who may call a tool is who may read its entry", and the ranked verb, like `grep`, answers from the caller's readable set only (spec 165's verb table, `context/specifications/active/165-the-permission-ladder-list-and-contribute/spec.md:28`, where `glean` is the name these specs give ranked search; `:55` also keeps unreadable bodies out of the BM25 statistics); `search.py:20-30` makes `passes_gates` the authority on every row that answers. A tool the caller cannot call is never ranked for them, unlike the registry's post-filter (F3).

### F10. Experiment: real MCP tools under vfs's own lexical search, by manifest shape

EXECUTED: `uv run python -I studies/experiments/06-tool-manifest-findability/run.py /home/user/mcp-gateway-registry -v`, output saved as `output.txt`. The corpus is the 81 tools of five server records in the registry clone (`registry/servers/{atlassian,sre-gateway,mcpgw,currenttime,realserverfaketools}.json`), 22 of them without a description. Each tool is written three times, into three mounts of an in-process SQLite `DatabaseStorage` with no embedder (lexical leg only), at `/<mount>/<server>/tools/<tool>.md`: `desc`, the description alone; `card`, a heading with the name, a `server:` line and the description; `man`, the card plus an Arguments section (each parameter's name, type and description) and a Returns section. Two query sets: 26 task phrasings with an accepted tool set each, and 5 identifier queries. Each was ranked before and after `rebuild`.

| Shape | Task hit@1 | Task hit@5 | Task MRR@10 | Identifier hit@1 | Identifier hit@5 |
|---|---|---|---|---|---|
| `desc` (description only) | 0.46 | 0.54 | 0.50 | 0.20 | 0.40 |
| `card` (name, server, description) | 0.54 | 0.73 | 0.63 | 1.00 | 1.00 |
| `man` (card plus arguments and returns) | 0.50 | 0.81 | 0.66 | 1.00 | 1.00 |

- EXECUTED: the numbers are identical before and after `rebuild`, so the query-time overlay and the built index rank these manifests the same way.
- EXECUTED: with descriptions only, 10 of 26 task queries miss the top 10; 8 of those 10 target tools with no description (the Kubernetes, logs, metrics and runbook tools). The card shape finds them by their name tokens (`k8s-api___get_deployment_status` ranks first for "has the deployment finished rolling out"). With descriptions only, the identifier queries `get_pod_status`, `search_runbooks` and `toggle_service` find nothing, because the name is only in the path.
- EXECUTED: adding arguments and returns raises hit@5 (0.73 to 0.81) but lowers hit@1 (0.54 to 0.50), and pushes "what time is it in Tokyo" from rank 2 to rank 8: the longer body adds matching but off-target words and BM25's length normalization dilutes the name and description. One manifest is one chunk at this size, so MaxP cannot separate the fields.
- EXECUTED: two queries miss in every shape: "who do I escalate a sev1 to" (no shared word with "get escalation procedures", since there is no stemming: `escalate` against `escalation`) and "find Confluence pages about onboarding" (the topic word is in no tool). These are the vocabulary-gap failures F2 and F4 describe, the ones example queries and the vector leg exist to close.
- EXECUTED: `grep` with `case_mode="insensitive"` for `pod` and `escalat` finds the right tool in the `man` mount and nothing in the `desc` mount; `worklog` is found in both, because it appears in the description.
- Limits, stated plainly: 81 tools, one engine, lexical only (no embedding model was reachable), and 26 queries written by the researcher after reading the tool list, which flatters every shape equally but makes absolute figures meaningless. The comparison between shapes is the result; the levels are not.

## What this means for a vfs code mode

INFERRED throughout, from the findings above.

**The direction is right.** Every vendor converged on the same move vfs proposes: do not preload the catalog, give the model a search, return a shortlist of about five, and let it load what it picked (F1, F3). The registry went further and searches servers, tools, agents and skills in one index (`server.py:1143-1155`), which is the vfs idea that a tool is one more thing in the namespace. vfs's existing `search` is already the strongest shape any shipped tool search uses: lexical plus vector, fused (F2 shows BM25 alone at 14–34% top-1 at a few hundred to a few thousand tools, and hybrids reported near 94%, vendor-measured). vfs adds two things none of the gateways have: ranking only over what the caller may call (F9, against the registry's post-filter), and the same `grep` and `glob` for the agent that knows the name.

**What a tool's file should contain to be found.** The body is all that is indexed (F9), so everything that should match must be in the body, ordered so the most discriminating text comes first:

1. A heading line with the tool's exact name (`# jira_add_worklog`). The name is the identifier queries' only match and the strongest signal for tools with bad descriptions (F10: identifier hit@1 0.20 to 1.00). The tokenizer splits it into its words.
2. A provenance line with the server's name and title (`server: atlassian (Atlassian)`), so "github create issue" can match both words, and the trust line spec 170 already requires.
3. The description, cleaned and capped as spec 170 says.
4. A "Use when" block of a few short example requests in a user's words ("log time against a ticket", "record two hours of work"). This is the document expansion of F4 (Tool2Vec, Re-Invoke, Toolshed), which helps the lexical leg directly by putting the user's vocabulary into the file. It should be generated or written by the host, marked as such, never taken from the server, and kept short.
5. Arguments with names and descriptions, and what it returns, after the above. They help recall (F10: hit@5 0.73 to 0.81) and are what `--help` and the code mode need anyway; they cost a little top-1 precision through length normalization.

The input schema in full JSON belongs in the same file only if it does not swamp the text; F10's dilution argues for keeping the searchable card first and the machine schema in a separate section or a sibling entry (`schema.json`) that is not chunked with it.

**Does vfs need anything beyond its existing search?** Four gaps, none of them a new retrieval engine:

- *Ranked search must reach the catalog.* Spec 170 serves `grep` over in-memory manifests and defers ranked search. Without it the agent has only lexical substring matching over tools, the weakest arm in F2. The catalog views need to feed the same lexical and vector legs, either as stored rows of a catalog storage (indexed by the existing pass, and searchable at once through the overlay, F9) or as a view whose manifests the overlay scores at query time. At the reference deployment's scale a catalog is thousands of rows against ten million files, so either is a rounding error on the index-visit multiplier.
- *Scope, not a new hierarchy.* A query for "create issue" over the whole namespace will rank documents about issues above the tool. The answer is the existing `paths=("/.vfs/mcp",)` or `globs=` scope, which is the server-then-tool hierarchy for free: `ls /.vfs/mcp` browses servers, `search --paths /.vfs/mcp/<server>` ranks one server's tools. F6 says the hierarchy's value is browsing and context budget, not better ranking, and the tree gives both.
- *The path's words.* Either the projection writes the name and server into the body (the cheap answer above), or the lexical index learns to index path segments as a field. The first needs no engine change; the second would help every file, and the registry's +5 path boost and Docker's ×4 server-name weight say path text is a strong signal.
- *Field weighting is the one ranking change the evidence suggests.* Docker approximates BM25F by repetition, the registry boosts by field, ScaleMCP weights fields; F10 shows the cost of not weighting. vfs's chunker already splits on structure, so a manifest could be chunked by section (card, arguments) to let MaxP pick the card. Whether that beats one chunk is an experiment, not a conclusion.

**The risks, named.**

- *Poisoning ranks first.* An attacker-optimized description wins retrieval (ToolHijacker: 100% retrieval hit rate) and selection (81–96%), and wording alone moves selection 10× (F7, F5). vfs ranking description text inherits this. Mitigations that fit vfs's model: the description cap bounds keyword stuffing; the provenance line tells the model which server a hit comes from; the `content_hash` lets a host pin a vetted manifest and refuse or flag one that changed (F8); a server admitted to the catalog only by grant keeps unvetted text out of every caller's readable set, so it is never ranked; host-written "Use when" examples, not server text, should carry the user vocabulary; and a stored `signal` prior could rank host-registered and vetted tools above unvetted ones without a new mechanism. None of these makes a malicious tool safe to call; F7's authors point to execution-level controls, which are vfs's permission check before dispatch and the human approval other studies discuss.
- *Stale text.* A manifest refreshed from `tools/list` can lag the server or change under the index. The overlay makes a changed body searchable immediately (F9, F10), so staleness is a refresh-cadence question for the projection, and a hash change is the signal to re-vet.
- *Missing descriptions.* About a quarter of the sample corpus has none (F5). The name-and-server card is the floor that keeps such tools findable (F10).
- *Over-trusting the shortlist.* Retrieval errors are about half of agent failures on LiveMCPBench and the right tool often ranks 6th to 20th (F1). The search result should say how many tools matched, and the agent should be able to page or narrow by server, which `paths=` and `limit=` already allow.

## What this study does not settle

- The vector leg on tool manifests: no embedding model was reachable, so F10 is lexical only; whether vfs's fused search reaches the hybrid figures vendors report (about 94%) is unmeasured.
- Whether host-written example queries help vfs's lexical leg as much as F4's papers report for dense retrieval, and how many examples a manifest should carry before they dilute it; F10 deliberately did not test them, because the same author wrote the queries.
- Whether chunking a manifest by section, or indexing path segments, beats a single-chunk card; a field-weighting experiment on a larger corpus (MCP-Zero's 308 servers and 2,797 tools, or ToolRet) would decide it.
- The exact paper figures where only search excerpts were available (RAG-MCP's per-N curve, ToolRet's per-model table, the Toolshed and ScaleMCP attribution, MCP-Zero's tables); a pass with arXiv reachable should confirm them.
- Whether a stored prior for vetted tools measurably resists ToolHijacker-style documents, or only reorders benign ones.

## One line

Every tool search the field shipped returns a shortlist of about five from a search over the tool's text, and the evidence says hybrid retrieval over a body that carries the tool's name, server, description and a few user-worded examples is what makes it work. vfs already has that search, but as drafted it does not reach the tool catalog and does not index the path, so a tool's file must carry its own name and server, and its description must be capped, hashed and ranked only for callers who may run it, because the most findable description is also the attacker's.
