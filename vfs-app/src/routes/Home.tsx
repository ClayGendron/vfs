import { Link } from "react-router-dom"
import {
  IntegrationsGrid,
  Positioning,
  Sample,
  Section,
  SpecHero,
  SpecStrip,
  TerminalTape,
  Values,
} from "@/components/brand"
import { SITE } from "@/lib/site"
import { useLatestRelease } from "@/hooks/useLatestRelease"

export function Home() {
  const { version } = useLatestRelease()

  return (
    <>
      <SpecHero
        headline={SITE.headline}
        lede={SITE.description}
        code={
          <Sample label="python" kind="VFSClient">
{`from vfs import VFSClient
from vfs.backends import PostgresFileSystem

g = VFSClient()
g.add_mount("/enterprise", PostgresFileSystem(...))

# pipelines are composable, like shell
g.cli('grep "authenticate" | nbr | pagerank | top 15')`}
          </Sample>
        }
        install={{ cmd: SITE.install.python }}
      />

      {/* ─── proof strip (alpha-appropriate facts, not logos) ─── */}
      <SpecStrip metrics={SITE.metrics} />

      {/* ─── on-wire: input vs. result contract ─── */}
      <Section label="vfs / 01 · on-wire">
        <div className="grid md:grid-cols-[minmax(0,1fr)_minmax(0,2.4fr)] gap-12 items-start mb-10">
          <div className="font-[family-name:var(--font-display)] text-[clamp(22px,2.2vw,30px)] leading-tight tracking-tight font-medium">
            One result contract. One method per verb.
          </div>
          <p className="text-[var(--muted)] text-[15px] leading-relaxed max-w-prose">
            Every operation — search, grep, pagerank, neighborhood — returns
            the same{" "}
            <code className="mono">VFSResult</code>. That is what makes
            pipelines compose: one method's output is always the next
            method's input.
          </p>
        </div>
        <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
          <Sample label="python · async" kind="VFSClient">
{`from vfs import AsyncVFSClient
from vfs.backends import PostgresFileSystem

async def run():
    g = AsyncVFSClient()
    await g.add_mount("/enterprise", PostgresFileSystem(...))

    # one verb per call; returns VFSResult
    return await g.semantic_search(
        "authentication",
        scope="/enterprise/**/*.py",
        top_k=15,
    )`}
          </Sample>
          <Sample label="result" kind="VFSResult">
{`VFSResult(
  function="semantic_search",
  success=True,
  candidates=[
    Candidate(path="/enterprise/auth.py",    score=0.184),
    Candidate(path="/enterprise/session.py", score=0.131),
    Candidate(path="/enterprise/policy.md",  score=0.097),
    ...
  ],
  next_cursor=None,
)`}
          </Sample>
        </div>
      </Section>

      {/* ─── integrations grid ─── */}
      <Section label="vfs / 02 · integrations">
        <div className="grid md:grid-cols-[minmax(0,1fr)_minmax(0,2.4fr)] gap-12 items-start mb-10">
          <div className="font-[family-name:var(--font-display)] text-[clamp(22px,2.2vw,30px)] leading-tight tracking-tight font-medium">
            Mount the stack you already run.
          </div>
          <p className="text-[var(--muted)] text-[15px] leading-relaxed max-w-prose">
            One result contract over the backends, retrieval primitives, graph
            algorithms, and agent frameworks you're already wiring together.
            Plain Python, plain CLI, no new infrastructure to host.
          </p>
        </div>
        <IntegrationsGrid groups={SITE.integrations} />
      </Section>

      {/* ─── positioning: why vfs vs. obvious alternatives ─── */}
      <Section label="vfs / 03 · why vfs?">
        <div className="grid md:grid-cols-[minmax(0,1fr)_minmax(0,2.4fr)] gap-12 items-start mb-10">
          <div className="font-[family-name:var(--font-display)] text-[clamp(22px,2.2vw,30px)] leading-tight tracking-tight font-medium">
            Not a vector DB. Not a retriever. A namespace.
          </div>
          <p className="text-[var(--muted)] text-[15px] leading-relaxed max-w-prose">
            vfs is the substrate underneath your retrievers, vector stores, and
            graph queries. Everything is addressable by path; every operation
            returns the same{" "}
            <code className="mono">VFSResult</code>; pipelines compose like the
            shell.
          </p>
        </div>
        <Positioning rows={SITE.positioning} />
      </Section>

      {/* ─── terminal tape preview ─── */}
      <Section label="vfs / 04 · the interface agents already know">
        <div className="grid md:grid-cols-[minmax(0,1fr)_minmax(0,1.6fr)] gap-12 items-start">
          <div>
            <div className="font-[family-name:var(--font-display)] text-[clamp(28px,3vw,40px)] leading-[1.1] tracking-tight font-medium">
              grep. neighborhood. pagerank.
            </div>
            <p className="text-[var(--muted)] text-[15px] leading-relaxed mt-4 max-w-prose">
              Unix verbs over enterprise context. Pipe the same way you'd pipe
              on a shell — the same way an LLM was trained to. The REPL is a
              click away.
            </p>
          </div>
          <TerminalTape cta="Open the REPL" to="/terminal" />
        </div>
      </Section>

      {/* ─── principles · capability surface ─── */}
      <Section label="vfs / 05 · principles">
        <Values
          items={[
            {
              title: "Agent-first",
              body:
                "Built for an LLM running in a loop over a long horizon. Every operation is versioned, reversible, and expressible through a composable CLI — the interface agents are trained to use.",
            },
            {
              title: "Everything is a file",
              body:
                "Files, chunks, versions, edges, tools — all addressable by path, all conforming to the same data types. One abstraction, one API, predictable behavior.",
            },
            {
              title: "Small, composable tools",
              body:
                "Not a new tool per use case. Read, grep, pagerank, neighborhood — each tiny, each pipeable. Specialized tools live at their own paths and load into context only when needed.",
            },
            {
              title: "Bring your own infra",
              body:
                "Database-first. Runs in-process with your app or as an MCP server. No new infra, no new patterns — vfs lives on the Postgres you already run.",
            },
          ]}
        />
      </Section>

      {/* ─── status + next ─── */}
      <Section label="vfs / 06 · status" tight>
        <div className="grid md:grid-cols-2 gap-12 items-start">
          <div>
            <div className="font-[family-name:var(--font-display)] text-[clamp(28px,3vw,40px)] leading-[1.1] tracking-tight font-medium">
              {SITE.stage} · {version}
            </div>
            <p className="text-[var(--muted)] text-[15px] leading-relaxed mt-4 max-w-prose">
              Alpha means the API is still moving. The core file system, CLI
              query engine, graph algorithms, and BM25 lexical search are
              implemented and tested.{" "}
              <span className="signal">2,157 tests, 99% coverage.</span> What's
              next: MCP single-tool interface, shell entrypoint,{" "}
              <code className="mono">.api/</code> control plane,
              LocalFileSystem, more analyzers, automatic embedding on write.
            </p>
            <div className="flex flex-wrap gap-4 mt-8">
              <Link
                to="/terminal"
                className="mono text-[11px] tracking-[0.22em] uppercase border border-[var(--rule)] px-4 py-3 hover:border-[var(--accent)] hover:text-[var(--accent)] transition-colors"
              >
                try the repl →
              </Link>
              <Link
                to="/about"
                className="mono text-[11px] tracking-[0.22em] uppercase border border-[var(--rule)] px-4 py-3 hover:border-[var(--accent)] hover:text-[var(--accent)] transition-colors"
              >
                read the thesis →
              </Link>
              <a
                href={SITE.github}
                target="_blank"
                rel="noreferrer"
                className="mono text-[11px] tracking-[0.22em] uppercase border border-[var(--rule)] px-4 py-3 hover:border-[var(--accent)] hover:text-[var(--accent)] transition-colors"
              >
                source →
              </a>
            </div>
          </div>
          <Sample label="install" kind="extras">
{`pip install vfs-py                 # core: sqlite, rustworkx, bm25
pip install 'vfs-py[postgres]'     # postgres: pgvector, fts, graph pushdown
pip install 'vfs-py[mssql]'        # mssql backend
pip install 'vfs-py[openai]'       # openai embeddings
pip install 'vfs-py[langchain]'    # langchain embedding provider
pip install 'vfs-py[deepagents]'   # deepagents integration
pip install 'vfs-py[all]'          # everything`}
          </Sample>
        </div>
      </Section>
    </>
  )
}
