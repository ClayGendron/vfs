import type { CSSProperties } from "react";
import { Section, Palette, TypeSystem, Values, Voice, SpecHero } from "../components/Shared";

// Pluto — the ninth planet, in homage to Plan 9 from Bell Labs.
// Pure grayscale with a single cobalt signal. No warmth, no tint.
const plutoVars: CSSProperties = {
  ["--bg" as any]: "#f1f1ee",
  ["--fg" as any]: "#0b0b0d",
  ["--muted" as any]: "rgba(11,11,13,0.70)",
  ["--quiet" as any]: "rgba(11,11,13,0.46)",
  ["--rule" as any]: "rgba(11,11,13,0.14)",
  ["--card" as any]: "#e4e4df",
  ["--card-strong" as any]: "#0f1012",
  ["--accent" as any]: "#2f58cf",
  ["--font-body" as any]: "'Space Grotesk', system-ui, sans-serif",
  ["--font-mono" as any]: "'Geist Mono', 'JetBrains Mono', monospace",
  ["--font-display" as any]: "'Space Grotesk', system-ui, sans-serif",
  ["--hero-fg" as any]: "#0b0b0d",
  background: "#f1f1ee",
  color: "#0b0b0d",
  minHeight: "100vh",
};

export function Protocol() {
  return (
    <div style={plutoVars}>
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
            Everything is a file. One protocol, any backend. Read, write, grep,
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
              <strong>vfs</strong> takes its central claim from Plan 9 from Bell
              Labs: <em>everything is a file</em>. One <span className="mono">Entry</span> type,
              one <span className="mono">VFSResult</span> envelope, one path grammar
              across every backend you mount. The language is RFC-2119: a{" "}
              <span className="mono">vfs</span> server <em>must</em> implement read,
              write, list, stat; it <em>should</em> implement watch.
            </p>
            <p>
              The grayscale page with one cobalt signal is the whitespace the
              teardowns identified: no Vercel-school dark mesh, no purple
              auth-startup accent, no "for the AI era" subhead. This is the lane
              an infrastructure standard would take in 2026 if it wanted to be
              taken seriously for the next ten years, not the next quarter.
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

      {/* ─── PALETTE ─── */}
      <Section label="spec / 03 · palette · pluto">
        <div className="palette-mode-label">
          <span className="palette-mode-dot light" /> light · paper mode
        </div>
        <Palette
          swatches={[
            { name: "Frost", hex: "#f1f1ee", role: "paper", fg: "#0b0b0d" },
            { name: "Plain", hex: "#e4e4df", role: "surface", fg: "#0b0b0d" },
            { name: "Night", hex: "#0b0b0d", role: "ink", fg: "#f1f1ee" },
            { name: "Cobalt", hex: "#2f58cf", role: "signal", fg: "#f1f1ee" },
            { name: "Indigo", hex: "#183988", role: "pressed", fg: "#f1f1ee" },
            { name: "Charon", hex: "#3d7d3f", role: "ok", fg: "#f1f1ee" },
          ]}
        />

        <div className="palette-mode-label" style={{ marginTop: 32 }}>
          <span className="palette-mode-dot dark" /> dark · ink mode
        </div>
        <Palette
          swatches={[
            { name: "Night", hex: "#0f1012", role: "paper", fg: "#e7e7e8" },
            { name: "Shadow", hex: "#18191c", role: "surface", fg: "#e7e7e8" },
            { name: "Ice", hex: "#e7e7e8", role: "ink", fg: "#0f1012" },
            { name: "Cobalt", hex: "#4d7cf3", role: "signal", fg: "#0f1012" },
            { name: "Azurite", hex: "#2c54be", role: "pressed", fg: "#e7e7e8" },
            { name: "Charon", hex: "#86c17a", role: "ok", fg: "#0f1012" },
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
          Fully desaturated grayscale, one cobalt wire — shifted one step
          between modes to hold contrast on paper and in the ink pool. Full
          specimen study at{" "}
          <a href="/colors" style={{ color: "var(--accent)" }}>/colors</a>.
        </div>
      </Section>

      {/* ─── TYPE ─── */}
      <Section label="spec / 04 · typography">
        <TypeSystem
          faces={[
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
                    Everything<br />is a file.
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
              The color study lives at <code className="mono"><a href="/colors" style={{ color: "var(--accent)" }}>/colors</a></code>.
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
/colors/          brand · palette study
/changelog/       every revision, every commit
/install.sh       pip install vfs-py
/contact/         github · mastodon

$ _`}
            </div>
          </div>
        </div>
      </Section>
    </div>
  );
}
