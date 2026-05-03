import { Link } from "react-router-dom"
import {
  IntegrationsGrid,
  Positioning,
  Sample,
  Section,
  SectionGrid,
  SpecHero,
  SpecStrip,
  TerminalTape,
  Values,
} from "@/components/brand"
import { SITE } from "@/lib/site"

export function Home() {
  const heroCode = (
    <Sample label="example · python" kind="quickstart">
{`from vfs `}<span className="kw">{`import`}</span>{` VFSClient
`}<span className="kw">{`from`}</span>{` vfs.backends `}<span className="kw">{`import`}</span>{` PostgresFileSystem

g = `}<span className="call">{`VFSClient`}</span>{`()
g.`}<span className="call">{`add_mount`}</span>{`(`}<span className="str">{`"/enterprise"`}</span>{`, `}<span className="call">{`PostgresFileSystem`}</span>{`(uri))

`}<span className="comment">{`# 1. write a file into the namespace`}</span>{`
g.`}<span className="call">{`write`}</span>{`(`}<span className="str">{`"/enterprise/auth.py"`}</span>{`, source)

`}<span className="comment">{`# 2. semantic + lexical retrieval over mounts`}</span>{`
hits = g.`}<span className="call">{`search`}</span>{`(`}<span className="str">{`"authenticate"`}</span>{`, k=`}<span className="num">{`5`}</span>{`)

`}<span className="comment">{`# 3. compose unix verbs over the result envelope`}</span>{`
g.`}<span className="call">{`cli`}</span>{`(`}<span className="str">{`'grep "authenticate" | nbr | pagerank | top 15'`}</span>{`)`}
    </Sample>
  )

  return (
    <>
      <SpecHero
        headline={"One Namespace\nfor Enterprise-Scale\nContext Engineering."}
        lede={SITE.description}
        code={heroCode}
        install={{ cmd: SITE.install.python }}
      />

      <SpecStrip metrics={SITE.metrics} />

      <Section label="vfs / 01 · on-wire">
        <SectionGrid
          taglineSize="lg"
          tagline={
            <>
              One result contract.
              <br />
              One method per verb.
            </>
          }
        >
          <p>
            Every operation — read, write, list, search, traverse — returns a{" "}
            <code className="mono">VFSResult</code>. Results compose with set
            algebra (<code className="mono">&amp;</code>,{" "}
            <code className="mono">|</code>,{" "}
            <code className="mono">−</code>) so pipelines are just expressions
            over one envelope.
          </p>
          <div style={{ marginTop: 24 }}>
            <Sample label="async client · result envelope" kind="protocol">
{`async with `}<span className="call">{`VFSClient`}</span>{`() as g:
    auth   = `}<span className="kw">{`await`}</span>{` g.`}<span className="call">{`search`}</span>{`(`}<span className="str">{`"authenticate"`}</span>{`, k=`}<span className="num">{`20`}</span>{`)
    policy = `}<span className="kw">{`await`}</span>{` g.`}<span className="call">{`list`}</span>{`(`}<span className="str">{`"/enterprise"`}</span>{`, glob=`}<span className="str">{`"*.md"`}</span>{`)
    nearby = `}<span className="kw">{`await`}</span>{` g.`}<span className="call">{`neighborhood`}</span>{`(auth.paths, depth=`}<span className="num">{`2`}</span>{`)

    ranked = (auth | nearby) - policy
    top    = ranked.`}<span className="call">{`pagerank`}</span>{`().`}<span className="call">{`top`}</span>{`(`}<span className="num">{`10`}</span>{`)

    `}<span className="kw">{`for`}</span>{` entry `}<span className="kw">{`in`}</span>{` top:
        `}<span className="call">{`print`}</span>{`(entry.path, entry.score, entry.content_hash)`}
            </Sample>
          </div>
        </SectionGrid>
      </Section>

      <Section label="vfs / 02 · integrations">
        <SectionGrid tagline="Mount the stack you already run.">
          <p>
            vfs is the protocol, not the database. Bring postgres, mssql,
            sqlite, your retrievers, your graph. We give you one namespace and
            one envelope across all of them.
          </p>
          <div style={{ marginTop: 24 }}>
            <IntegrationsGrid groups={SITE.integrations} />
          </div>
        </SectionGrid>
      </Section>

      <Section label="vfs / 03 · why vfs?">
        <SectionGrid
          tagline={
            <>
              Not a vector DB.
              <br />
              Not a retriever.
              <br />
              A namespace.
            </>
          }
        >
          <p>
            Developers reach for the closest analogue first. vfs sits next to
            the tools you already use — and gives you a substrate that composes
            them.
          </p>
          <div style={{ marginTop: 24 }}>
            <Positioning rows={SITE.positioning} />
          </div>
        </SectionGrid>
      </Section>

      <Section label="vfs / 04 · the interface agents already know">
        <SectionGrid
          tagline={
            <>
              grep. neighborhood.
              <br />
              pagerank.
            </>
          }
        >
          <p>
            An LLM was already trained on Unix. vfs gives it a shell over
            enterprise data — pasteable in chat, scriptable in code, identical
            results in either.
          </p>
          <div style={{ marginTop: 24 }}>
            <TerminalTape cta="open the repl" to="/terminal" />
          </div>
        </SectionGrid>
      </Section>

      <Section label="vfs / 05 · principles">
        <SectionGrid tagline="Capabilities, not features.">
          <p>
            The product story has three load-bearing claims. The principles
            below describe how those claims hold up under stress.
          </p>
          <div style={{ marginTop: 24 }}>
            <Values
              items={[
                {
                  title: "Agent-first",
                  body:
                    "An LLM already knows how to use a shell. vfs gives it one over enterprise data.",
                },
                {
                  title: "Everything is a file",
                  body:
                    "One Unix-style namespace over heterogeneous stores. No probing. No special cases.",
                },
                {
                  title: "Small composable tools",
                  body:
                    "grep, neighborhood, pagerank, top — pipe results across one envelope.",
                },
                {
                  title: "Bring your own infra",
                  body:
                    "Mount what you already run. vfs is the protocol, not the database.",
                },
              ]}
            />
          </div>
        </SectionGrid>
      </Section>

      <Section label="vfs / 06 · status" tight>
        <SectionGrid tagline={<><em>alpha</em> · v0.0.x</>}>
          <p>
            The core file system, CLI query engine, graph algorithms, and BM25
            lexical search are implemented and tested.{" "}
            <strong style={{ color: "var(--fg)" }}>2,157 tests</strong>,{" "}
            <strong style={{ color: "var(--fg)" }}>99% coverage</strong>, three
            production-grade backends. The API is still moving. Target stable:{" "}
            <strong style={{ color: "var(--fg)" }}>{SITE.milestone}</strong>.
          </p>
          <div
            style={{
              display: "flex",
              gap: 18,
              marginTop: 18,
              flexWrap: "wrap",
              fontFamily: "var(--font-mono)",
              fontSize: 12,
              letterSpacing: "0.18em",
              textTransform: "uppercase",
            }}
          >
            <Link
              to="/terminal"
              style={{
                color: "var(--accent)",
                borderBottom: "1px solid var(--accent)",
                paddingBottom: 2,
              }}
            >
              try the repl →
            </Link>
            <Link
              to="/about"
              style={{
                color: "var(--fg)",
                borderBottom: "1px solid var(--rule)",
                paddingBottom: 2,
              }}
            >
              read the thesis →
            </Link>
            <a
              href={SITE.github}
              target="_blank"
              rel="noreferrer"
              style={{
                color: "var(--fg)",
                borderBottom: "1px solid var(--rule)",
                paddingBottom: 2,
              }}
            >
              source →
            </a>
          </div>
          <div style={{ marginTop: 32 }}>
            <Sample label="install extras" kind="pip">
{`pip install vfs-py                  `}<span className="comment">{`# core`}</span>{`
pip install "vfs-py[postgres]"      `}<span className="comment">{`# pg backend`}</span>{`
pip install "vfs-py[mssql]"         `}<span className="comment">{`# mssql backend`}</span>{`
pip install "vfs-py[graph]"         `}<span className="comment">{`# rustworkx algorithms`}</span>{`
pip install "vfs-py[mcp]"           `}<span className="comment">{`# mcp surface`}</span>{`
pip install "vfs-py[all]"           `}<span className="comment">{`# everything`}</span>
            </Sample>
          </div>
        </SectionGrid>
      </Section>
    </>
  )
}
