import { Link } from "react-router-dom"
import {
  IntegrationsGrid,
  MountMap,
  NamespaceTree,
  Positioning,
  Sample,
  Section,
  SectionGrid,
  SectionHead,
  SpecHero,
  SpecStrip,
  TryTerminal,
  ValueGrid,
  VerbStrip,
} from "@/components/brand"
import { Seo } from "@/components/Seo"
import { routeMeta, SITE } from "@/lib/site"

export function Home() {
  return (
    <>
      <Seo {...routeMeta.home} />
      <SpecHero
        eyebrow={`${SITE.stage} · ${SITE.versionFallback} · apache 2.0`}
        headline={<>Agentic search on <em>your</em> database</>}
        lede={SITE.description}
      />

      <Section tight>
        <SectionHead tagline="Built on one claim.">
          Glob, grep, glean, and graph are the four verbs any agent needs to
          navigate a knowledge base.
        </SectionHead>
        <VerbStrip />
      </Section>

      <SpecStrip metrics={SITE.metrics} />

      <Section>
        <SectionHead tagline={<>A context substrate, not another <em>retriever</em></>}>
          Six things vfs gives an agent that a vector index, an fsspec mount,
          or a bespoke tool per query shape does not.
        </SectionHead>
        <ValueGrid />
      </Section>

      <Section>
        <SectionHead tagline="Run the verbs.">
          A sandboxed vfs over a sample repo — the same surface an agent gets
          over MCP. Pick a command below; the transcript is canned for now,
          and the{" "}
          <Link to="/terminal" className="accent">
            live repl
          </Link>{" "}
          is a click away.
        </SectionHead>
        <TryTerminal />
      </Section>

      <Section>
        <SectionGrid taglineSize="lg" tagline="Treat everything as a file.">
          <p>
            More than fifty years ago, Bell Labs settled on one idea:
            everything is a file, and you act on it with small programs that
            pipe together. Unix outlasted every platform built since because
            that held — a uniform namespace, composable tools, no special
            cases. VFS takes the same bet for agents. One namespace over every
            store, one <code className="mono">VFSResult</code> out of every
            operation, and verbs that compose with set algebra (
            <code className="mono">&amp;</code>, <code className="mono">|</code>,{" "}
            <code className="mono">−</code>) — so pipelines are expressions, not
            bespoke tools.
          </p>
          <div style={{ marginTop: 24 }}>
            <NamespaceTree />
          </div>
        </SectionGrid>
      </Section>

      <Section>
        <SectionHead tagline="Mount on your stack.">
          VFS is the protocol, not the database. Mount Postgres, MSSQL, SQLite,
          your retrievers, your graph — in-process with your app or as an MCP
          server. One namespace and one envelope across every mount, with no
          migration and no new infrastructure to stand up.
        </SectionHead>
        <MountMap />
        <div style={{ marginTop: 24 }}>
          <IntegrationsGrid groups={SITE.integrations} />
        </div>
        <div style={{ marginTop: 24 }}>
          <Positioning rows={SITE.positioning} />
        </div>
      </Section>

      <Section tight>
        <SectionGrid tagline={<><em>alpha</em> · v0.0.x</>}>
          <p>
            The core file system, CLI query engine, graph algorithms, and BM25
            lexical search are implemented and proven, now being re-landed on a
            new MCP-native core.{" "}
            <strong style={{ color: "var(--fg)" }}>{SITE.tests} tests</strong>{" "}
            green on that core; SQLite, Postgres, and MSSQL backends tested against real
            databases. The API is still moving. Target stable:{" "}
            <strong style={{ color: "var(--fg)" }}>{SITE.milestone}</strong>.
          </p>
          <div className="vfs-linkline" style={{ marginTop: 18 }}>
            <Link to="/terminal" className="accent">
              try the repl →
            </Link>
            <Link to="/about">read the thesis →</Link>
            <a href={SITE.github} target="_blank" rel="noreferrer">
              source →
            </a>
          </div>
          <div style={{ marginTop: 32 }}>
            <Sample label="install extras" kind="pip">
{`pip install vfs-py                  `}<span className="comment">{`# core + rustworkx graph`}</span>{`
pip install "vfs-py[search]"        `}<span className="comment">{`# vector + embedding search`}</span>{`
pip install "vfs-py[postgres]"      `}<span className="comment">{`# pg + pgvector backend`}</span>{`
pip install "vfs-py[mssql]"         `}<span className="comment">{`# mssql backend`}</span>{`
pip install "vfs-py[all]"           `}<span className="comment">{`# everything`}</span>
            </Sample>
          </div>
        </SectionGrid>
      </Section>
    </>
  )
}
