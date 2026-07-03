import { Link } from "react-router-dom"
import {
  IntegrationsGrid,
  MountMap,
  NamespaceTree,
  Positioning,
  Sample,
  SearchVerbs,
  Section,
  SectionGrid,
  SectionHead,
  SpecHero,
  SpecStrip,
} from "@/components/brand"
import { Seo } from "@/components/Seo"
import { routeMeta, SITE } from "@/lib/site"

export function Home() {
  const heroCode = (
    <Sample label="example · python" kind="quickstart">
{`from vfs `}<span className="kw">{`import`}</span>{` VFSClient
`}<span className="kw">{`from`}</span>{` vfs.backends `}<span className="kw">{`import`}</span>{` PostgresFileSystem
`}<span className="kw">{`from`}</span>{` sqlalchemy.ext.asyncio `}<span className="kw">{`import`}</span>{` create_async_engine

g = `}<span className="call">{`VFSClient`}</span>{`()
engine = `}<span className="call">{`create_async_engine`}</span>{`(uri)
g.`}<span className="call">{`add_mount`}</span>{`(`}<span className="call">{`PostgresFileSystem`}</span>{`(engine=engine), path=`}<span className="str">{`"/enterprise"`}</span>{`)

`}<span className="comment">{`# one namespace over every mount`}</span>{`
g.`}<span className="call">{`write`}</span>{`(`}<span className="str">{`"/enterprise/auth.py"`}</span>{`, source)

`}<span className="comment">{`# compose unix verbs over one result envelope`}</span>{`
hits = g.`}<span className="call">{`cli`}</span>{`(`}<span className="str">{`'grep "authenticate" | nbr | pagerank | top 15'`}</span>{`)

`}<span className="kw">{`for`}</span>{` obs `}<span className="kw">{`in`}</span>{` hits:
    `}<span className="call">{`print`}</span>{`(obs.path, obs.score)`}
    </Sample>
  )

  return (
    <>
      <Seo {...routeMeta.home} />
      <SpecHero
        headline={SITE.headline}
        lede={SITE.description}
        code={heroCode}
        install={{ cmd: SITE.install.python }}
      />

      <SpecStrip metrics={SITE.metrics} />

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
        <SectionHead tagline="Search from every angle.">
          A file carries information four ways: where it sits, what it says,
          what it means, and what it connects to. VFS gives agents one verb per
          dimension — and because every result is a set of paths, one
          verb&rsquo;s output feeds the next.
        </SectionHead>
        <SearchVerbs />
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
