import { Section, Sample } from "@/components/brand"
import { Badge } from "@/components/ui/badge"
import { Separator } from "@/components/ui/separator"
import { SITE } from "@/lib/site"

export function About() {
  return (
    <>
      {/* ─── Lede ─── */}
      <Section label="about / 01 · what vfs is" className="pt-24">
        <div className="grid md:grid-cols-[minmax(0,1fr)_minmax(0,1.6fr)] gap-16 items-start">
          <div className="font-[family-name:var(--font-brand)] font-medium text-[clamp(56px,10vw,128px)] leading-[0.88] tracking-[-0.01em]">
            The context<br />layer
            <span className="signal">.</span>
          </div>
          <div className="space-y-6 max-w-prose">
            <p className="font-[family-name:var(--font-display)] font-medium text-[clamp(22px,2.4vw,30px)] leading-[1.25] tracking-[-0.012em]">
              {SITE.description}
            </p>
            <p className="text-[15px] leading-relaxed text-[var(--muted)]">
              Unix has been a foundational technology in computing for over 50 years
              because of its enduring core design principles: a uniform namespace,
              small composable tools, and portability. <strong className="text-[var(--fg)] font-semibold">vfs</strong>{" "}
              builds on these principles to design the platform for building agent
              context and performing agentic actions.
            </p>
            <p className="text-[15px] leading-relaxed text-[var(--muted)]">
              Everything in <code className="mono">vfs</code> is addressable by
              path. Files live in the user namespace. Chunks, versions, and
              edges live under the reserved{" "}
              <code className="mono">/.vfs/.../__meta__/...</code> tree. Ordinary{" "}
              <code className="mono">ls</code>, <code className="mono">glob</code>, and search operate on user
              paths. Metadata is explicit and opt-in.
            </p>
          </div>
        </div>
      </Section>

      {/* ─── Three core components ─── */}
      <Section label="about / 02 · core components">
        <div className="grid md:grid-cols-3 gap-0 border-t border-[var(--rule)]">
          {[
            {
              num: "01",
              title: "File system",
              body:
                "A versioned, chunkable, permission-aware, database-backed file system for text and documents. All operations are reversible and protected against data loss.",
            },
            {
              num: "02",
              title: "Retrieval",
              body:
                "Pluggable vector search and BM25 lexical search enable semantic and keyword retrieval across the file system. Embedding and indexing happen automatically on write.",
            },
            {
              num: "03",
              title: "Graph",
              body:
                "Connections between files are first-class objects. PageRank, centrality, and subgraph extraction operate on the same paths as every other operation.",
            },
          ].map((c, i) => (
            <div
              key={c.num}
              className={[
                "p-8 md:p-10 border-b border-[var(--rule)]",
                i > 0 && "md:border-l md:border-[var(--rule)]",
              ]
                .filter(Boolean)
                .join(" ")}
            >
              <div className="mono text-[10px] tracking-[0.28em] uppercase text-[var(--quiet)] mb-4">
                {c.num}
              </div>
              <div className="font-[family-name:var(--font-display)] font-medium text-2xl leading-tight tracking-[-0.012em] mb-3">
                {c.title}
              </div>
              <p className="text-[14px] leading-[1.65] text-[var(--muted)]">
                {c.body}
              </p>
            </div>
          ))}
        </div>
      </Section>

      {/* ─── Composable results ─── */}
      <Section label="about / 03 · composable results">
        <div className="grid md:grid-cols-[minmax(0,1fr)_minmax(0,1.1fr)] gap-12 items-start">
          <div className="space-y-5 max-w-prose">
            <p className="font-[family-name:var(--font-display)] font-medium text-[clamp(22px,2.2vw,28px)] leading-[1.2] tracking-[-0.012em]">
              Every operation returns a <code className="mono">VFSResult</code>.
              Results support set algebra.
            </p>
            <p className="text-[15px] leading-relaxed text-[var(--muted)]">
              Different retrieval strategies combine without LLM re-interpretation.
              Intersect semantic and glob. Union with graph neighbors. Re-rank by
              centrality. Every step is a method, every method is a CLI verb, every
              result is the same envelope.
            </p>
          </div>
          <Sample label="python" kind="set algebra">
{`semantic = g.semantic_search("authentication")
python_files = g.glob("/workspace/**/*.py")

# intersection
candidates = semantic & python_files

# union — expand through graph
expanded = candidates | g.neighborhood(candidates)

# re-rank by centrality
ranked = g.pagerank(candidates=expanded)`}
          </Sample>
        </div>
      </Section>

      {/* ─── Backends + clients ─── */}
      <Section label="about / 04 · backends · clients">
        <div className="grid md:grid-cols-2 gap-12 items-start">
          <div>
            <div className="mono text-[10px] tracking-[0.28em] uppercase text-[var(--quiet)] mb-5">
              backends
            </div>
            <ul className="space-y-3">
              {[
                ["SQLite", "core · rustworkx · BM25"],
                ["PostgreSQL", "pgvector · FTS · graph pushdown"],
                ["MSSQL", "enterprise-ready · CONTAINS · graph"],
                ["Local disk", "files on disk, metadata in SQLite (soon)"],
              ].map(([name, desc]) => (
                <li
                  key={name}
                  className="flex items-baseline justify-between gap-4 py-3 border-b border-[var(--rule)]"
                >
                  <span className="font-[family-name:var(--font-display)] text-lg font-medium">
                    {name}
                  </span>
                  <span className="mono text-[11px] tracking-[0.06em] text-[var(--quiet)] text-right">
                    {desc}
                  </span>
                </li>
              ))}
            </ul>
          </div>
          <div>
            <div className="mono text-[10px] tracking-[0.28em] uppercase text-[var(--quiet)] mb-5">
              clients
            </div>
            <ul className="space-y-3">
              {[
                ["VFSClient", "sync · scripts, notebooks, pipelines"],
                ["VFSClientAsync", "async · app servers, long-running agents"],
                ["CLI", "g.cli('...') · one-line pipelines"],
                ["MCP server", "single-tool interface (soon)"],
              ].map(([name, desc]) => (
                <li
                  key={name}
                  className="flex items-baseline justify-between gap-4 py-3 border-b border-[var(--rule)]"
                >
                  <span className="font-[family-name:var(--font-display)] text-lg font-medium">
                    {name}
                  </span>
                  <span className="mono text-[11px] tracking-[0.06em] text-[var(--quiet)] text-right">
                    {desc}
                  </span>
                </li>
              ))}
            </ul>
          </div>
        </div>
      </Section>

      {/* ─── Status + roadmap ─── */}
      <Section label="about / 05 · status · roadmap">
        <div className="flex flex-wrap items-center gap-3 mb-8">
          <Badge className="rounded-none bg-[var(--accent)] text-[var(--bg)] px-3 py-1 tracking-[0.2em] uppercase">
            {SITE.stage}
          </Badge>
          <Badge
            variant="outline"
            className="rounded-none border-[var(--rule)] bg-transparent text-[var(--fg)] tracking-[0.2em] uppercase px-3 py-1"
          >
            target · {SITE.milestone}
          </Badge>
          <Badge
            variant="outline"
            className="rounded-none border-[var(--rule)] bg-transparent text-[var(--fg)] tracking-[0.2em] uppercase px-3 py-1"
          >
            apache 2.0
          </Badge>
        </div>

        <p className="text-[15px] leading-relaxed text-[var(--muted)] max-w-prose mb-8">
          The core file system, CLI query engine, graph algorithms, and BM25 lexical
          search are implemented and tested. <strong className="text-[var(--fg)] font-semibold">2,157 tests · 99% coverage.</strong>
        </p>

        <Separator className="bg-[var(--rule)] mb-8" />

        <div className="mono text-[10px] tracking-[0.28em] uppercase text-[var(--quiet)] mb-4">
          next
        </div>
        <ul className="grid md:grid-cols-2 gap-x-10 gap-y-2 max-w-5xl">
          {[
            "MCP single-tool interface — progressive discovery via --help",
            "Shell entrypoint — vfs 'grep \"auth\" | pagerank | top 15'",
            ".api/ control plane — live API pass-through for Jira, Slack, GitHub",
            "LocalFileSystem — mount local dirs, metadata in SQLite",
            "More analyzers — Markdown, PDF, email, Slack, Jira, CSV/JSON",
            "Automatic embedding on write — background indexing",
          ].map((item) => (
            <li
              key={item}
              className="flex gap-3 py-2 text-[14px] leading-[1.6] text-[var(--fg)]"
            >
              <span className="signal select-none">→</span>
              <span>{item}</span>
            </li>
          ))}
        </ul>
      </Section>
    </>
  )
}
