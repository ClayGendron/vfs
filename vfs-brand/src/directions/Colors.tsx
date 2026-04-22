import type { CSSProperties } from "react";

// One candidate palette for the vfs protocol brand.
// Pluto — the ninth planet, in homage to Plan 9 from Bell Labs,
// the distributed OS that argued everything is a file.
// Grayscale discipline with a single cobalt signal; ships in both
// light and dark modes so the palette survives the whole day/night
// surface spectrum without losing character.

type ThemeVars = {
  bg: string;
  surface: string;
  fg: string;
  muted: string;
  quiet: string;
  rule: string;
  accent: string;
  pressed: string;
  ok: string;
  fault: string;
  inkSample: string;
};

type Chip = {
  name: string;
  hex: string;
  role: string;
  fg?: string;
};

type Mode = {
  theme: ThemeVars;
  chips: Chip[];
};

type PaletteSpec = {
  id: string;
  num: string;
  name: string;
  mood: string;
  lede: string;
  notes: string;
  wordmark: string;
  light: Mode;
  dark: Mode;
};

// ─── 09 · Pluto ────────────────────────────────────────────────
// The protocol as a distant instrument. Cold grayscale of outer-
// system ice, one cobalt signal — the only saturated pigment in
// the kit. Named after the ninth planet in homage to Plan 9 from
// Bell Labs, the OS whose central claim was "everything is a file."
const pluto: PaletteSpec = {
  id: "pluto",
  num: "09",
  name: "Pluto",
  mood: "plan 9 · ninth planet · instrument",
  lede:
    "The protocol as the ninth planet. Fully desaturated everything, then one cobalt wire running through the panel — the single thing the eye is allowed to find first.",
  notes:
    "Named after Pluto in homage to Plan 9 from Bell Labs — the distributed OS whose central claim (everything is a file) is the same claim vfs makes. The palette with the strongest opinion: no warmth, no tint, no ornament. Cobalt is the only saturated pigment in the kit, and it only appears in signal or pressed roles — never in surface, rule, or label.",
  wordmark: "vfs",
  dark: {
    theme: {
      bg: "#0f1012",
      surface: "#18191c",
      fg: "#e7e7e8",
      muted: "rgba(231,231,232,0.66)",
      quiet: "rgba(231,231,232,0.42)",
      rule: "rgba(231,231,232,0.14)",
      accent: "#4d7cf3",
      pressed: "#2c54be",
      ok: "#86c17a",
      fault: "#e47b62",
      inkSample: "#070708",
    },
    chips: [
      { name: "Night", hex: "#0f1012", role: "paper", fg: "#e7e7e8" },
      { name: "Shadow", hex: "#18191c", role: "surface", fg: "#e7e7e8" },
      { name: "Ice", hex: "#e7e7e8", role: "ink" },
      { name: "Cobalt", hex: "#4d7cf3", role: "signal", fg: "#0f1012" },
      { name: "Azurite", hex: "#2c54be", role: "pressed", fg: "#e7e7e8" },
      { name: "Charon", hex: "#86c17a", role: "ok", fg: "#0f1012" },
    ],
  },
  light: {
    theme: {
      bg: "#f1f1ee",
      surface: "#e4e4df",
      fg: "#0b0b0d",
      muted: "rgba(11,11,13,0.7)",
      quiet: "rgba(11,11,13,0.46)",
      rule: "rgba(11,11,13,0.14)",
      accent: "#2f58cf",
      pressed: "#183988",
      ok: "#3d7d3f",
      fault: "#c23d2a",
      inkSample: "#0f1012",
    },
    chips: [
      { name: "Frost", hex: "#f1f1ee", role: "paper" },
      { name: "Plain", hex: "#e4e4df", role: "surface" },
      { name: "Night", hex: "#0b0b0d", role: "ink", fg: "#f1f1ee" },
      { name: "Cobalt", hex: "#2f58cf", role: "signal", fg: "#f1f1ee" },
      { name: "Indigo", hex: "#183988", role: "pressed", fg: "#f1f1ee" },
      { name: "Charon", hex: "#3d7d3f", role: "ok", fg: "#f1f1ee" },
    ],
  },
};

const palettes: PaletteSpec[] = [pluto];

// ─── helpers ────────────────────────────────────────────────────
function themeVars(t: ThemeVars): CSSProperties {
  return {
    ["--bg" as any]: t.bg,
    ["--surface" as any]: t.surface,
    ["--fg" as any]: t.fg,
    ["--muted" as any]: t.muted,
    ["--quiet" as any]: t.quiet,
    ["--rule" as any]: t.rule,
    ["--accent" as any]: t.accent,
    ["--pressed" as any]: t.pressed,
    ["--ok" as any]: t.ok,
    ["--fault" as any]: t.fault,
    ["--ink-sample" as any]: t.inkSample,
  };
}

function ChipTile({ c }: { c: Chip }) {
  const fg = c.fg ?? "rgba(255,255,255,0.94)";
  return (
    <div className="colors-chip" style={{ background: c.hex, color: fg }}>
      <div className="colors-chip-top">
        <span className="colors-chip-role">{c.role}</span>
        <span className="colors-chip-reg">·</span>
      </div>
      <div className="colors-chip-bottom">
        <div className="colors-chip-name">{c.name}</div>
        <div className="colors-chip-hex">{c.hex.toUpperCase()}</div>
      </div>
    </div>
  );
}

function ModeCard({
  palette,
  mode,
  modeLabel,
}: {
  palette: PaletteSpec;
  mode: Mode;
  modeLabel: "light" | "dark";
}) {
  return (
    <div
      className={`colors-mode colors-mode-${modeLabel}`}
      style={{
        background: mode.theme.bg,
        color: mode.theme.fg,
        ...themeVars(mode.theme),
      }}
    >
      <div className="colors-mode-head">
        <span className="colors-mode-tag">
          <span className="colors-mode-dot" />
          {modeLabel}
        </span>
        <span className="colors-mode-meta">{palette.num}·{modeLabel.charAt(0).toUpperCase()}</span>
      </div>

      <div className="colors-mode-wordmark">{palette.wordmark}</div>

      <div className="colors-chips">
        {mode.chips.map((c) => (
          <ChipTile key={c.name} c={c} />
        ))}
      </div>

      <div className="colors-mode-demo">
        <button className="colors-install">
          <span className="colors-install-sigil">$</span>
          <span className="colors-install-cmd">pip install vfs-py</span>
          <span className="colors-install-flag">copy</span>
        </button>
        <pre className="colors-sample">
{`{ "method": "fs.read",
  "path":   "/workspace/auth.py",
  "ver":    ${palette.num}2 }`}
        </pre>
      </div>
    </div>
  );
}

function Sheet({ p }: { p: PaletteSpec }) {
  return (
    <section className="colors-sheet">
      <div className="colors-sheet-header">
        <div className="colors-catalogue">
          <span className="colors-num">VFS · {p.num}</span>
          <span className="colors-name">{p.name}</span>
        </div>
        <div className="colors-reg">
          <RegMark />
          <span>SPECIMEN · LIGHT / DARK</span>
          <RegMark />
        </div>
      </div>

      <div className="colors-sheet-meta">
        <div className="colors-sheet-mood">{p.mood}</div>
        <p className="colors-sheet-lede">{p.lede}</p>
        <div className="colors-sheet-notes">{p.notes}</div>
      </div>

      <div className="colors-pair">
        <ModeCard palette={p} mode={p.light} modeLabel="light" />
        <ModeCard palette={p} mode={p.dark} modeLabel="dark" />
      </div>
    </section>
  );
}

function RegMark() {
  return (
    <svg
      className="colors-regmark"
      width="14"
      height="14"
      viewBox="0 0 14 14"
      fill="none"
      stroke="currentColor"
      strokeWidth="0.8"
    >
      <circle cx="7" cy="7" r="4.2" />
      <line x1="7" y1="0" x2="7" y2="14" />
      <line x1="0" y1="7" x2="14" y2="7" />
    </svg>
  );
}

function ColorsHeader() {
  return (
    <header className="colors-header">
      <div className="colors-header-top">
        <div>
          <div className="colors-header-tag">vfs · brand · color study</div>
          <div className="colors-header-date">2026·Q2 · specimen sheet · rev 03</div>
        </div>
        <div className="colors-header-right">
          <div>one palette</div>
          <div>two modes</div>
          <div>one accent</div>
        </div>
      </div>

      <h1 className="colors-title">
        color<span className="colors-title-dot">·</span>study
      </h1>

      <div className="colors-header-grid">
        <p className="colors-header-lede">
          One palette for the <em>vfs</em> protocol brand. <strong>Pluto</strong>
          {" "}— the ninth planet, named in homage to <em>Plan 9 from Bell Labs</em>,
          the distributed OS whose central claim (everything is a file) is the
          same claim vfs makes. Fully desaturated grayscale with a single cobalt
          signal, expressed in both light and dark modes. Six role fields per
          mode — paper, surface, ink, signal, pressed, ok / fault.
        </p>
        <div className="colors-header-legend">
          <div><span>paper</span> — background</div>
          <div><span>surface</span> — raised card</div>
          <div><span>ink</span> — body text</div>
          <div><span>signal</span> — single accent</div>
          <div><span>pressed</span> — activated</div>
          <div><span>ok / fault</span> — status only</div>
        </div>
      </div>
    </header>
  );
}

export function Colors() {
  return (
    <div className="colors-page">
      <ColorsHeader />
      {palettes.map((p) => (
        <Sheet key={p.id} p={p} />
      ))}
      <footer className="colors-footer">
        <div>vfs · color study · end of sheet</div>
        <div>← back to /protocol</div>
      </footer>
    </div>
  );
}
