import type { CSSProperties } from "react";
import {
  Section,
  Palette,
  TypeSystem,
  Values,
  Voice,
  Tradeoff,
  SpecHero,
  NotesBlock,
} from "../components/Shared";

// Protocol — agent-era substrate. Soft bone paper, muted sage-teal signal.
// Palette is pitched toward depot.dev softness: cream + olive + slate.
const protocolVars: CSSProperties = {
  ["--bg" as any]: "#eeeae0",
  ["--fg" as any]: "#1d1c18",
  ["--muted" as any]: "rgba(29, 28, 24, 0.68)",
  ["--quiet" as any]: "rgba(29, 28, 24, 0.46)",
  ["--rule" as any]: "rgba(29, 28, 24, 0.12)",
  ["--card" as any]: "#e5e0d1",
  ["--card-strong" as any]: "#1f1e1a",
  ["--accent" as any]: "#5f8374",
  ["--font-body" as any]: "'Space Grotesk', system-ui, sans-serif",
  ["--font-mono" as any]: "'Geist Mono', 'JetBrains Mono', monospace",
  ["--font-display" as any]: "'Space Grotesk', system-ui, sans-serif",
  ["--hero-fg" as any]: "#1d1c18",
};

export function Protocol() {
  return (
    <div style={protocolVars}>
      <SpecHero
        topLeft={
          <>
            <div>/protocol/vfs/<span style={{ color: "var(--accent)" }}>v0.1</span></div>
            <div style={{ color: "var(--quiet)", marginTop: 6 }}>spec · reference · clients</div>
          </>
        }
        topRight={
          <>
            <div>fsp / mcp</div>
            <div>jsonrpc 2.0</div>
            <div>alpha · 2026-Q2</div>
          </>
        }
        mark={"vfs"}
        version={"v0.0.21 · build 0442 · sha 6e2fc9e"}
        lede={
          <>
            The filesystem layer for agent loops. One protocol, any backend. Read, write, grep,
            walk — over Postgres, MSSQL, SQLite, and eventually every API you run.
          </>
        }
        side={
          <>
            <div>vfs.dev</div>
            <div>spec → fsp(5)</div>
            <div style={{ color: "var(--accent)" }}>alpha · 2026-Q2</div>
          </>
        }
        install={{ cmd: "pip install vfs-py" }}
      />

      {/* ─── POSITIONING ─── */}
      <Section label="spec / 01 · positioning">
        <div className="positioning">
          <div className="positioning-name stencil">Protocol</div>
          <div className="positioning-body">
            <div className="tagline">
              The filesystem layer for the agent era. MCP-native. Spec-first.
            </div>
            <p>
              <strong>Protocol</strong> positions <span className="mono">vfs</span> as substrate, not
              product. The stencil reads as a callsign on a flight strip — a designation, not a
              billboard. The language is RFC-2119: a <span className="mono">vfs</span> server{" "}
              <em>must</em> implement read, write, list, stat; it <em>should</em> implement watch.
              The homepage is a spec table of contents.
            </p>
            <p>
              The bone-paper, warm-charcoal, muted-sage palette is the whitespace the teardowns
              identified: no Vercel-school dark mesh, no purple auth-startup accent, no "for the AI
              era" subhead. This is the lane an infrastructure standard would take in 2026 if it
              wanted to be taken seriously for the next ten years, not the next quarter.
            </p>
          </div>
        </div>
      </Section>

      {/* ─── CAPABILITIES ─── */}
      <Section label="spec / 02 · capabilities">
        <Values
          items={[
            {
              title: "Uniform",
              body: "One namespace across mounts. One Entry type with path, version, content-hash, size. One VFSResult envelope across every operation. No backend-specific path grammar.",
            },
            {
              title: "Composable",
              body: "Every op returns VFSResult. Set algebra (∣, &, −) on results. CLI-style pipelines: grep → nbr → pagerank → top 10. Agents drive the same API from Python or a shell line.",
            },
            {
              title: "Versioned",
              body: "Every Entry carries a revision and a content_hash. Optimistic concurrency via if_version. StaleVersionError and WriteConflictError are first-class. Restore is a path operation.",
            },
            {
              title: "Governed",
              body: "Capability negotiation at initialize. No probing, no silent fallbacks. ~20 narrow capability names; each op declares streaming, cancellable, paginated, atomic sub-flags.",
            },
          ]}
        />
      </Section>

      {/* ─── COLOR ─── */}
      <Section label="spec / 03 · palette · signal">
        <Palette
          swatches={[
            { name: "Bone", hex: "#eeeae0", role: "paper", fg: "#1d1c18" },
            { name: "Chalk", hex: "#e5e0d1", role: "surface", fg: "#1d1c18" },
            { name: "Slate", hex: "#1d1c18", role: "ink", fg: "#eeeae0" },
            { name: "Sage", hex: "#5f8374", role: "signal", fg: "#eeeae0" },
            { name: "Moss", hex: "#465c52", role: "pressed", fg: "#eeeae0" },
            { name: "Pulse", hex: "#8aa27c", role: "ok", fg: "#1d1c18" },
            { name: "Clay", hex: "#b0644c", role: "fault", fg: "#eeeae0" },
            { name: "Halftone", hex: "#8f887a", role: "secondary", fg: "#eeeae0" },
          ]}
        />
        <div
          className="mono"
          style={{
            marginTop: 24,
            fontSize: 11,
            letterSpacing: "0.14em",
            textTransform: "uppercase",
            color: "var(--quiet)",
          }}
        >
          Bone paper inverts the dark-mesh default. One muted accent. Pulse and Clay used only in
          status — never decoration.
        </div>
      </Section>

      {/* ─── TYPE ─── */}
      <Section label="spec / 04 · typography">
        <TypeSystem
          faces={[
            {
              role: "CALLSIGN",
              name: "Big Shoulders Stencil",
              use: "wordmark · version tags · section headers",
              sample: (
                <div
                  className="stencil stencil-thin"
                  style={{ fontSize: 96, lineHeight: 0.95, color: "var(--accent)", letterSpacing: "0.01em" }}
                >
                  vfs · 0442
                </div>
              ),
            },
            {
              role: "DISPLAY",
              name: "Space Grotesk",
              use: "H1s · headlines · ui display",
              sample: (
                <>
                  <div
                    className="display"
                    style={{ fontSize: 44, lineHeight: 1.1, fontWeight: 500, letterSpacing: "-0.015em" }}
                  >
                    One protocol.<br />Any backend.
                  </div>
                  <div
                    className="display"
                    style={{ fontSize: 17, lineHeight: 1.6, marginTop: 16, color: "var(--muted)", fontWeight: 300 }}
                  >
                    A vfs server MUST implement read, write, list, stat. It SHOULD implement watch.
                  </div>
                </>
              ),
            },
            {
              role: "BODY",
              name: "Space Grotesk 15/24",
              use: "running prose · spec bodies · annotations",
              sample: (
                <div style={{ fontSize: 15, lineHeight: 1.75, maxWidth: 560 }}>
                  Mounts are first-class in FSP:{" "}
                  <code className="mono">fs.mount.list</code>,{" "}
                  <code className="mono">fs.mount.add</code>,{" "}
                  <code className="mono">fs.mount.remove</code>. Longest-prefix routing is
                  client-side; the server is source of truth for topology.
                </div>
              ),
            },
            {
              role: "MONO",
              name: "Geist Mono",
              use: "envelopes · capabilities · path strings",
              sample: (
                <pre
                  className="mono"
                  style={{
                    fontSize: 12.5,
                    lineHeight: 1.75,
                    margin: 0,
                    padding: 18,
                    background: "var(--card-strong)",
                    color: "var(--bg)",
                    borderRadius: 2,
                  }}
                >
{`{ "jsonrpc": "2.0",
  "method": "fs.read",
  "params": { "path": "/workspace/auth.py",
              "if_version": 12 },
  "id": 0442 }`}
                </pre>
              ),
            },
          ]}
        />
      </Section>

      {/* ─── VOICE ─── */}
      <Section label="spec / 05 · voice · on the wire">
        <Voice
          pairs={[
            {
              good: "A vfs server MUST implement read, write, list, stat.",
              bad: "VFS empowers your agents to seamlessly orchestrate retrieval.",
            },
            {
              good: "Capability negotiation happens at initialize. No probing.",
              bad: "Our intelligent platform auto-detects what your data needs.",
            },
            {
              good: "Entry carries path, version, content_hash, size. Nothing else is identity.",
              bad: "VFS uses advanced AI to understand your data relationships.",
            },
            {
              good: "curl vfs.dev | sh — the homepage is the spec.",
              bad: "Book a demo to unlock the power of agentic retrieval.",
            },
          ]}
        />
      </Section>

      {/* ─── SAMPLE ─── */}
      <Section label="spec / 06 · sample · on-wire">
        <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 12 }}>
          <div className="sample">
            <div className="sample-head">
              <span>request</span>
              <span>fs.read</span>
            </div>
            <div className="sample-body">
{`{
  "jsonrpc": "2.0",
  "method": "fs.read",
  "params": {
    "path": "/workspace/auth.py",
    "if_version": 12
  },
  "id": 0442
}`}
            </div>
          </div>
          <div className="sample">
            <div className="sample-head">
              <span>response</span>
              <span>VFSResult</span>
            </div>
            <div className="sample-body">
{`{
  "jsonrpc": "2.0",
  "result": {
    "function": "fs.read",
    "success": true,
    "entries": [{
      "path": "/workspace/auth.py",
      "version": 12,
      "content_hash": "sha256:a1b2...e9f0",
      "kind": "file",
      "size": 2048
    }],
    "next_cursor": null
  },
  "id": 0442
}`}
            </div>
          </div>
        </div>

        <div className="sample" style={{ marginTop: 16 }}>
          <div className="sample-head">
            <span>mount topology</span>
            <span>fs.mount.list</span>
          </div>
          <div className="sample-body">
{`/
├── workspace/        [postgres://local/vfs_main]      fs.read fs.write fs.grep fs.glob fs.search.lexical fs.search.vector
├── docs/             [postgres://local/vfs_docs]      fs.read fs.write fs.grep fs.glob fs.search.lexical
├── memory/           [sqlite:///agent.db]             fs.read fs.write fs.grep fs.glob
└── .vfs/             [internal]                       fs.read fs.mount.list
    └── __meta__/
        ├── chunks/   — addressable chunks per path
        ├── versions/ — revision history
        └── edges/    — out/{type}/{target}, in/{type}/{source}`}
          </div>
        </div>
      </Section>

      {/* ─── SIGNATURE MOVE ─── */}
      <Section label="spec / 07 · signature move">
        <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 40, alignItems: "center" }}>
          <div>
            <div
              className="display"
              style={{
                fontSize: 34,
                lineHeight: 1.15,
                fontWeight: 500,
                letterSpacing: "-0.018em",
                marginBottom: 20,
              }}
            >
              The homepage <em>is</em> the filesystem.
            </div>
            <p style={{ fontSize: 16, lineHeight: 1.7, color: "var(--muted)" }}>
              On first load, <code className="mono">vfs.dev</code> shows one prompt —{" "}
              <code className="mono">$ curl vfs.dev | sh</code> — followed by the actual output: a
              directory listing of the spec. Nav is the filesystem. Docs are mounts. The spec TOC is
              at <code className="mono">/spec/</code>. Clients live at <code className="mono">/clients/</code>.
              No feature grid, no logo wall, no conic gradient.
            </p>
            <p style={{ fontSize: 16, lineHeight: 1.7, color: "var(--muted)", marginTop: 16 }}>
              One gag, executed seriously. Nobody else in the agent-infra landscape can do this
              without cosplaying vfs.
            </p>
          </div>
          <div className="sample">
            <div className="sample-head">
              <span>vfs.dev</span>
              <span>ls /</span>
            </div>
            <div className="sample-body">
{`$ curl vfs.dev | sh

vfs · virtual filesystem for agents
alpha · v0.0.21 · 2026-Q2

/spec/            the protocol (fsp-001)
/clients/         python · ts · mcp
/backends/        postgres · mssql · sqlite
/changelog/       every revision, every commit
/install.sh       pip install vfs-py
/contact/         github · mastodon

$ _`}
            </div>
          </div>
        </div>
      </Section>

      {/* ─── TRADEOFF ─── */}
      <Section label="spec / 08 · trade-off">
        <Tradeoff
          keeps="Legibility to the audience that matters most — people who've used MCP, LSP, 9P, and know what a protocol brand looks like. The mono-for-headings move and the bone/sage palette place vfs visually adjacent to nobody, which is the entire point."
          risks="Calling yourself a protocol is a strong claim; it has to be earned by a reference spec (fsp-001), not by marketing. Without that artefact shipping, the direction reads as aspiration. Single-weight stencil over Swiss-grid layout requires disciplined typesetting — one wrong margin and it collapses to generic dev-tool."
        />
      </Section>

      {/* ─── NOTES ─── */}
      <Section label="spec / 09 · notes" tight>
        <NotesBlock
          left={
            <>
              Stencil as callsign. Mono-for-headings is the single strongest differentiator against
              the Vercel-school consensus. Muted sage on bone softens the protocol tone without
              losing signal. Zero gradient. Zero illustration. ASCII diagrams are the brand.
            </>
          }
          right={
            <>
              modelcontextprotocol.io (Mintlify-restrained) · Turbopuffer's essay homepage · depot.dev
              (soft sage-on-paper) · the 9P protocol · IETF RFC layout · Geist typeface ·
              Swiss-grid sports livery.
            </>
          }
        />
      </Section>
    </div>
  );
}
