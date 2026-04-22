import type { ReactNode, CSSProperties } from "react";
import { useState } from "react";

export function Section({
  label,
  title,
  children,
  tight,
  style,
}: {
  label?: string;
  title?: ReactNode;
  children: ReactNode;
  tight?: boolean;
  style?: CSSProperties;
}) {
  return (
    <section className={tight ? "section section-tight" : "section"} style={style}>
      {label && <div className="section-label">{label}</div>}
      {title && <h2 style={{ marginBottom: 40 }}>{title}</h2>}
      {children}
    </section>
  );
}

export type Swatch = { name: string; hex: string; fg?: string; role?: string };

export function Palette({ swatches }: { swatches: Swatch[] }) {
  return (
    <div className="palette">
      {swatches.map((s) => (
        <div
          key={s.name}
          className="swatch"
          style={{ background: s.hex, color: s.fg ?? "#fff" }}
        >
          <div className="name">{s.name}</div>
          <div>
            {s.role && <div className="hex" style={{ opacity: 0.72, marginBottom: 4 }}>{s.role}</div>}
            <div className="hex">{s.hex}</div>
          </div>
        </div>
      ))}
    </div>
  );
}

export type TypeSpec = { role: string; name: string; use: string; sample: ReactNode; style?: CSSProperties };

export function TypeSystem({ faces }: { faces: TypeSpec[] }) {
  return (
    <div className="type-stack">
      {faces.map((f) => (
        <div key={f.role} className="type-row">
          <div className="type-meta">
            <div>{f.role}</div>
            <div className="name-line">{f.name}</div>
            <div className="use-line">{f.use}</div>
          </div>
          <div className="type-sample" style={f.style}>
            {f.sample}
          </div>
        </div>
      ))}
    </div>
  );
}

export function Values({
  items,
  label = "cap.",
}: {
  items: { title: string; body: string }[];
  label?: string;
}) {
  return (
    <div className="values">
      {items.map((v, i) => (
        <div key={v.title} className="value">
          <div className="value-label">
            {label} {String(i + 1).padStart(2, "0")}
          </div>
          <h3 className="value-title">{v.title}</h3>
          <div className="value-body">{v.body}</div>
        </div>
      ))}
    </div>
  );
}

export function Voice({
  pairs,
}: {
  pairs: { good: string; bad: string }[];
}) {
  return (
    <div className="voice">
      {pairs.map((p, i) => (
        <div key={i} style={{ display: "contents" }}>
          <div className="voice-cell">
            <div className="voice-label">
              <span className="mark">✓</span> we say
            </div>
            <div className="voice-line">{p.good}</div>
          </div>
          <div className="voice-cell bad">
            <div className="voice-label">
              <span className="mark">×</span> we don't
            </div>
            <div className="voice-line">{p.bad}</div>
          </div>
        </div>
      ))}
    </div>
  );
}

export function Tradeoff({ keeps, risks }: { keeps: string; risks: string }) {
  return (
    <div className="tradeoff-grid">
      <div className="tradeoff">
        <div className="tradeoff-label">what it wins</div>
        <div className="tradeoff-body">
          <span className="yes">{keeps}</span>
        </div>
      </div>
      <div className="tradeoff cost">
        <div className="tradeoff-label">what it costs</div>
        <div className="tradeoff-body">{risks}</div>
      </div>
    </div>
  );
}

export function SpecHero({
  topLeft,
  topRight,
  mark,
  version,
  lede,
  side,
  install,
}: {
  topLeft: ReactNode;
  topRight: ReactNode;
  mark: ReactNode;
  version?: ReactNode;
  lede: ReactNode;
  side: ReactNode;
  install?: InstallSpec;
}) {
  return (
    <section className="spec-hero">
      <div className="spec-hero-top">
        <div className="mono" style={{ fontSize: 10, letterSpacing: "0.26em", textTransform: "uppercase" }}>
          {topLeft}
        </div>
        <div
          className="mono"
          style={{
            fontSize: 10,
            letterSpacing: "0.26em",
            textTransform: "uppercase",
            textAlign: "right",
            lineHeight: 1.9,
            color: "var(--quiet)",
          }}
        >
          {topRight}
        </div>
      </div>

      <div className="spec-hero-body">
        <div>
          <h1 className="spec-hero-mark">{mark}</h1>
          {version && (
            <div
              className="mono"
              style={{
                fontSize: 11,
                letterSpacing: "0.2em",
                textTransform: "uppercase",
                color: "var(--quiet)",
                marginTop: 22,
              }}
            >
              {version}
            </div>
          )}
        </div>

        <div className="spec-hero-grid">
          <div className="spec-hero-lede">{lede}</div>
          <div className="spec-hero-meta">{side}</div>
        </div>
      </div>

      {install && <InstallBar cmd={install.cmd} label={install.label ?? "install ↓"} />}
    </section>
  );
}

export type InstallSpec = { cmd: string; label?: string };

export function InstallBar({ cmd, label = "install ↓" }: InstallSpec) {
  const [copied, setCopied] = useState(false);
  const copy = async () => {
    try {
      await navigator.clipboard.writeText(cmd);
      setCopied(true);
      setTimeout(() => setCopied(false), 1400);
    } catch {}
  };
  return (
    <div className="install-bar">
      <div className="install-label">{label}</div>
      <button className="install-btn" onClick={copy}>
        <span style={{ display: "inline-flex", alignItems: "center", gap: 14 }}>
          <span className="sigil">$</span>
          <span>{cmd}</span>
        </span>
        <span className={copied ? "copy-flag copied" : "copy-flag"}>
          {copied ? "✓ copied" : "copy"}
        </span>
      </button>
    </div>
  );
}

export function NotesBlock({
  left,
  right,
  leftLabel = "concept",
  rightLabel = "references",
}: {
  left: ReactNode;
  right: ReactNode;
  leftLabel?: string;
  rightLabel?: string;
}) {
  return (
    <div className="notes-grid">
      <div>
        <div className="label">{leftLabel}</div>
        {left}
      </div>
      <div>
        <div className="label">{rightLabel}</div>
        {right}
      </div>
    </div>
  );
}
