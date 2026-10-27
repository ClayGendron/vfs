"""Build ``index.html``, the interactive viewer for the architecture pages.

The viewer is one self-contained HTML file. It carries a snapshot of every
Markdown page in this directory, renders the Markdown in the browser, draws
each ``mermaid`` block as a diagram, and gives every diagram pan, zoom and a
full-screen mode. Opened straight from disk (double-click) it shows the
embedded snapshot; served over HTTP it re-reads the ``.md`` files on load, so
the page is always as fresh as the directory.

Rebuild after editing a page::

    uv run python context/architecture/build_html.py

Serve it live while editing (then open http://localhost:8765/)::

    uv run python -m http.server 8765 --directory context/architecture

Stdlib only; the Markdown and Mermaid renderers load from a CDN at view time.
"""

from __future__ import annotations

import datetime
import json
import re
import subprocess
from pathlib import Path

HERE = Path(__file__).resolve().parent
OUT = HERE / "index.html"
GLOSSARY = "glossary"
START = "README"

_H1 = re.compile(r"^# (.+)$", re.MULTILINE)


# ---------------------------------------------------------------------------
# Collecting the pages
# ---------------------------------------------------------------------------


def page_order(paths: list[Path]) -> list[Path]:
    """README first, the numbered pages in order, the glossary last."""

    def key(p: Path) -> tuple[int, str]:
        if p.stem == START:
            return (0, "")
        if p.stem == GLOSSARY:
            return (2, "")
        return (1, p.stem)

    return sorted(paths, key=key)


def page_title(path: Path, text: str) -> str:
    if path.stem == START:
        return "Start here"
    match = _H1.search(text)
    return match.group(1).strip() if match else path.stem


def collect_pages() -> list[dict[str, str]]:
    pages = []
    for path in page_order(sorted(HERE.glob("*.md"))):
        text = path.read_text(encoding="utf-8")
        pages.append({"id": path.stem, "file": path.name, "title": page_title(path, text), "markdown": text})
    return pages


def git_commit() -> str:
    try:
        out = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"], cwd=HERE, capture_output=True, text=True, check=True
        )
    except (OSError, subprocess.CalledProcessError):
        return "unknown"
    return out.stdout.strip() or "unknown"


# ---------------------------------------------------------------------------
# Writing the viewer
# ---------------------------------------------------------------------------


def build() -> Path:
    data = {
        "pages": collect_pages(),
        "build": {"date": datetime.datetime.now(datetime.UTC).date().isoformat(), "commit": git_commit()},
    }
    # ``</`` would end the <script> element early; ``<\/`` is the same string in JSON.
    payload = json.dumps(data, ensure_ascii=False).replace("</", "<\\/")
    OUT.write_text(TEMPLATE.replace("__DATA__", payload), encoding="utf-8")
    return OUT


TEMPLATE = r"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>vfs architecture</title>
<meta name="description" content="The architecture map of vfs: living diagrams with pan, zoom and full-screen, rendered from context/architecture/*.md.">
<style>
  :root {
    --bg: #fbfaf7; --fg: #1f1f1d; --muted: #6a6964; --line: #e2dfd7; --panel: #f3f1eb;
    --accent: #2f5d8a; --accent-soft: #e4edf6; --code-bg: #efede7; --shadow: 0 1px 2px rgba(0,0,0,.06);
    --stage: #ffffff; --nav-w: 288px; --header-h: 52px;
    color-scheme: light;
  }
  @media (prefers-color-scheme: dark) {
    :root:not([data-theme="light"]) {
      --bg: #151618; --fg: #e7e5df; --muted: #9b9992; --line: #2b2d31; --panel: #1c1e21;
      --accent: #85b4e3; --accent-soft: #1f2b38; --code-bg: #20232a; --shadow: 0 1px 2px rgba(0,0,0,.4);
      --stage: #1a1c1f; color-scheme: dark;
    }
  }
  :root[data-theme="dark"] {
    --bg: #151618; --fg: #e7e5df; --muted: #9b9992; --line: #2b2d31; --panel: #1c1e21;
    --accent: #85b4e3; --accent-soft: #1f2b38; --code-bg: #20232a; --shadow: 0 1px 2px rgba(0,0,0,.4);
    --stage: #1a1c1f; color-scheme: dark;
  }

  * { box-sizing: border-box; }
  html { scroll-padding-top: calc(var(--header-h) + 12px); }
  body {
    margin: 0; background: var(--bg); color: var(--fg);
    font: 15px/1.55 ui-sans-serif, system-ui, -apple-system, "Segoe UI", Roboto, sans-serif;
  }
  body.locked { overflow: hidden; }
  a { color: var(--accent); text-decoration: none; }
  a:hover { text-decoration: underline; }
  button {
    font: inherit; color: var(--fg); background: var(--panel); border: 1px solid var(--line);
    border-radius: 6px; padding: 4px 10px; cursor: pointer; line-height: 1.2;
  }
  button:hover { border-color: var(--accent); }

  header {
    position: sticky; top: 0; z-index: 20; height: var(--header-h);
    display: flex; align-items: center; gap: 16px; padding: 0 16px;
    background: var(--bg); border-bottom: 1px solid var(--line);
  }
  header .brand { font-weight: 650; letter-spacing: .01em; white-space: nowrap; }
  header .brand span { color: var(--muted); font-weight: 400; }
  header .crumb { color: var(--muted); overflow: hidden; text-overflow: ellipsis; white-space: nowrap; flex: 1; }
  header .badge {
    font-size: 12px; color: var(--muted); border: 1px solid var(--line); border-radius: 999px; padding: 2px 10px;
    white-space: nowrap;
  }
  header .badge.live { color: #2e7d4f; border-color: #2e7d4f66; }

  .frame { display: grid; grid-template-columns: var(--nav-w) minmax(0, 1fr); }
  nav {
    position: sticky; top: var(--header-h); height: calc(100vh - var(--header-h)); overflow: auto;
    border-right: 1px solid var(--line); padding: 14px 10px 24px; background: var(--panel);
  }
  nav h2 { font-size: 11px; text-transform: uppercase; letter-spacing: .08em; color: var(--muted); margin: 10px 8px 6px; }
  nav ol { list-style: none; margin: 0; padding: 0; }
  nav li a { display: block; padding: 5px 8px; border-radius: 6px; color: var(--fg); font-size: 14px; }
  nav li a:hover { background: var(--accent-soft); text-decoration: none; }
  nav li.active > a { background: var(--accent); color: #fff; }
  nav li .num { color: var(--muted); display: inline-block; width: 26px; }
  nav li.active > a .num { color: #ffffffb3; }
  nav ol.outline { margin: 2px 0 6px 34px; border-left: 1px solid var(--line); }
  nav ol.outline li a { font-size: 13px; color: var(--muted); padding: 3px 8px; }
  nav ol.outline li a:hover { color: var(--fg); }

  main { padding: 24px 40px 80px; max-width: 1240px; width: 100%; }
  main h1 { font-size: 28px; line-height: 1.2; margin: 6px 0 18px; letter-spacing: -.01em; }
  main h2 { font-size: 21px; margin: 40px 0 12px; padding-top: 10px; border-top: 1px solid var(--line); }
  main h3 { font-size: 17px; margin: 28px 0 8px; }
  main h2 .anchor, main h3 .anchor { color: var(--muted); opacity: 0; margin-left: -1.1em; width: 1.1em; display: inline-block; }
  main h2:hover .anchor, main h3:hover .anchor { opacity: .7; }
  main p, main ul, main ol, main blockquote { max-width: 78ch; }
  main li { margin: 3px 0; }
  main code { font: 13px/1.4 ui-monospace, SFMono-Regular, Menlo, Consolas, monospace; background: var(--code-bg); padding: 1px 5px; border-radius: 4px; }
  main pre { background: var(--code-bg); padding: 12px 14px; border-radius: 8px; overflow: auto; max-width: 100%; }
  main pre code { background: none; padding: 0; }
  main table { border-collapse: collapse; width: 100%; margin: 14px 0 22px; font-size: 14px; display: block; overflow-x: auto; }
  main table thead th { text-align: left; border-bottom: 2px solid var(--line); padding: 8px 10px; font-weight: 600; vertical-align: bottom; }
  main table td { border-bottom: 1px solid var(--line); padding: 7px 10px; vertical-align: top; }
  main table tr > :first-child { white-space: nowrap; }
  main blockquote { border-left: 3px solid var(--line); margin: 14px 0; padding: 2px 16px; color: var(--muted); }
  main hr { border: 0; border-top: 1px solid var(--line); margin: 32px 0; }

  figure.diagram { margin: 18px 0 26px; border: 1px solid var(--line); border-radius: 10px; background: var(--stage); box-shadow: var(--shadow); overflow: hidden; }
  figure.diagram .toolbar { display: flex; align-items: center; gap: 6px; padding: 8px 10px; border-bottom: 1px solid var(--line); background: var(--panel); flex-wrap: wrap; }
  figure.diagram .toolbar .zoom-level { min-width: 48px; text-align: center; font-variant-numeric: tabular-nums; color: var(--muted); font-size: 13px; }
  figure.diagram .toolbar .spacer { flex: 1; }
  figure.diagram .toolbar .hint { color: var(--muted); font-size: 12px; }
  figure.diagram .stage { position: relative; overflow: hidden; user-select: none; cursor: grab; touch-action: none; }
  figure.diagram .stage.dragging { cursor: grabbing; }
  figure.diagram .layer { position: absolute; left: 0; top: 0; transform-origin: 0 0; will-change: transform; }
  figure.diagram .layer svg { display: block; }
  figure.diagram details { border-top: 1px solid var(--line); background: var(--panel); }
  figure.diagram details summary { padding: 6px 12px; font-size: 13px; color: var(--muted); cursor: pointer; }
  figure.diagram details pre { margin: 0; border-radius: 0; font-size: 12.5px; }
  figure.diagram.expanded { position: fixed; inset: 0; z-index: 40; margin: 0; border: 0; border-radius: 0; display: flex; flex-direction: column; }
  figure.diagram.expanded .stage { flex: 1; }
  figure.diagram.expanded details { display: none; }
  figure.diagram .diagram-error { color: #b3261e; white-space: pre-wrap; margin: 0; padding: 12px; }

  .pager { display: flex; justify-content: space-between; gap: 16px; margin-top: 48px; padding-top: 18px; border-top: 1px solid var(--line); }
  .pager a { display: block; padding: 10px 14px; border: 1px solid var(--line); border-radius: 8px; max-width: 48%; }
  .pager a small { display: block; color: var(--muted); font-size: 12px; }
  .pager a:hover { text-decoration: none; border-color: var(--accent); }

  @media (max-width: 900px) {
    .frame { grid-template-columns: 1fr; }
    nav { position: static; height: auto; border-right: 0; border-bottom: 1px solid var(--line); }
    nav ol.outline { display: none; }
    main { padding: 16px 16px 60px; }
    header .crumb { display: none; }
  }
</style>
</head>
<body>
<header>
  <div class="brand">vfs <span>/ architecture</span></div>
  <div class="crumb" id="crumb"></div>
  <span class="badge" id="badge" title="Where the page text comes from">loading…</span>
  <button id="theme" title="Switch light and dark">Theme</button>
</header>
<div class="frame">
  <nav id="nav"></nav>
  <main id="content"><p>Loading…</p></main>
</div>

<script type="application/json" id="pages-data">__DATA__</script>
<script src="https://cdn.jsdelivr.net/npm/marked@15.0.7/lib/marked.umd.js"></script>
<script type="module">
import mermaid from "https://cdn.jsdelivr.net/npm/mermaid@11.4.1/dist/mermaid.esm.min.mjs";

const $ = (sel, root = document) => root.querySelector(sel);
const DATA = JSON.parse($("#pages-data").textContent);
const PAGES = DATA.pages;
const BY_ID = new Map(PAGES.map((p) => [p.id, p]));

const escapeHtml = (s) => s.replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));

// ---------------------------------------------------------------------------
// Theme: follows the system until the button is pressed, then remembers.
// ---------------------------------------------------------------------------
function currentTheme() {
  const pinned = document.documentElement.dataset.theme;
  if (pinned) return pinned;
  return matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light";
}
try {
  const saved = localStorage.getItem("vfs-arch-theme");
  if (saved) document.documentElement.dataset.theme = saved;
} catch {}

function initMermaid() {
  mermaid.initialize({
    startOnLoad: false,
    theme: currentTheme() === "dark" ? "dark" : "default",
    themeVariables: { fontFamily: 'ui-sans-serif, system-ui, -apple-system, "Segoe UI", Roboto, sans-serif', fontSize: "14px" },
    flowchart: { useMaxWidth: false, htmlLabels: true, curve: "basis" },
    sequence: { useMaxWidth: false },
    class: { useMaxWidth: false },
    state: { useMaxWidth: false },
  });
}

$("#theme").addEventListener("click", () => {
  const next = currentTheme() === "dark" ? "light" : "dark";
  document.documentElement.dataset.theme = next;
  try { localStorage.setItem("vfs-arch-theme", next); } catch {}
  initMermaid();
  renderPage(current, true);
});

// ---------------------------------------------------------------------------
// Markdown: headings get ids, .md links become in-app routes, mermaid blocks
// become diagram placeholders that are drawn after the HTML is in place.
// ---------------------------------------------------------------------------
const slugger = {
  seen: new Map(),
  reset() { this.seen.clear(); },
  slug(html) {
    const base = html.replace(/<[^>]+>/g, "").toLowerCase().replace(/[^\w\s-]/g, "").trim().replace(/\s+/g, "-");
    const n = this.seen.get(base) || 0;
    this.seen.set(base, n + 1);
    return n ? `${base}-${n}` : base;
  },
};
let current = null;

marked.use({
  gfm: true,
  renderer: {
    heading({ tokens, depth }) {
      const text = this.parser.parseInline(tokens);
      const id = slugger.slug(text);
      const anchor = depth > 1 ? `<a class="anchor" href="#${current}/${id}" aria-label="Link to this section">#</a>` : "";
      return `<h${depth} id="${id}">${anchor}${text}</h${depth}>\n`;
    },
    link({ href, title, tokens }) {
      const text = this.parser.parseInline(tokens);
      const m = href.match(/^([\w.-]+)\.md(?:#(.*))?$/);
      let target = href;
      if (m && BY_ID.has(m[1])) target = `#${m[1]}${m[2] ? "/" + m[2] : ""}`;
      const extra = /^https?:/.test(target) ? ' target="_blank" rel="noopener"' : "";
      const t = title ? ` title="${escapeHtml(title)}"` : "";
      return `<a href="${escapeHtml(target)}"${t}${extra}>${text}</a>`;
    },
    code({ text, lang }) {
      if (lang === "mermaid") return `<figure class="diagram" data-source="${escapeHtml(text)}"></figure>\n`;
      return `<pre><code class="lang-${escapeHtml(lang || "")}">${escapeHtml(text)}</code></pre>\n`;
    },
  },
});

// ---------------------------------------------------------------------------
// Diagrams: each mermaid block is drawn once, then wrapped in a pan/zoom stage.
// ---------------------------------------------------------------------------
let viewers = [];
let seq = 0;

async function drawDiagrams(root) {
  viewers = [];
  for (const fig of root.querySelectorAll("figure.diagram")) {
    const source = fig.dataset.source;
    const id = `diagram-${++seq}`;
    try {
      const { svg } = await mermaid.render(id, source);
      viewers.push(mountViewer(fig, svg, source));
    } catch (err) {
      document.getElementById(id)?.remove();
      fig.innerHTML = `<pre class="diagram-error">This block did not render:\n${escapeHtml(String(err?.message || err))}</pre><pre><code>${escapeHtml(source)}</code></pre>`;
    }
  }
}

function mountViewer(fig, svgText, source) {
  fig.innerHTML = `
    <div class="toolbar">
      <button data-act="out" title="Zoom out">−</button>
      <span class="zoom-level">100%</span>
      <button data-act="in" title="Zoom in">+</button>
      <button data-act="fit" title="Fit the whole diagram">Fit</button>
      <button data-act="one" title="Actual size">1:1</button>
      <button data-act="full" title="Full screen (Esc to leave)">Full screen</button>
      <span class="spacer"></span>
      <span class="hint">Drag to pan · pinch or ⌃ wheel to zoom · double-click to fit</span>
    </div>
    <div class="stage"><div class="layer"></div></div>
    <details><summary>Mermaid source</summary><pre><code></code></pre></details>`;
  $("details code", fig).textContent = source;
  const stage = $(".stage", fig);
  const layer = $(".layer", fig);
  const level = $(".zoom-level", fig);
  layer.innerHTML = svgText;
  const svg = $("svg", layer);
  const vb = svg.viewBox.baseVal;
  const W = vb && vb.width ? vb.width : parseFloat(svg.getAttribute("width")) || 800;
  const H = vb && vb.height ? vb.height : parseFloat(svg.getAttribute("height")) || 400;
  svg.style.maxWidth = "none";
  svg.setAttribute("width", W);
  svg.setAttribute("height", H);

  const PAD = 16;
  let s = 1, tx = 0, ty = 0;
  const clamp = (v) => Math.min(8, Math.max(0.05, v));
  const expanded = () => fig.classList.contains("expanded");

  function apply() {
    layer.style.transform = `translate(${tx}px, ${ty}px) scale(${s})`;
    level.textContent = `${Math.round(s * 100)}%`;
  }
  function sizeStage() {
    if (expanded()) { stage.style.height = ""; return; }
    const w = stage.clientWidth - PAD * 2;
    const fitW = Math.min(1, w / W);
    stage.style.height = `${Math.max(160, Math.min(H * fitW + PAD * 2, innerHeight * 0.72))}px`;
  }
  function center() {
    const r = stage.getBoundingClientRect();
    tx = (r.width - W * s) / 2;
    ty = (r.height - H * s) / 2;
  }
  function fit() {
    sizeStage();
    const r = stage.getBoundingClientRect();
    const best = Math.min((r.width - PAD * 2) / W, (r.height - PAD * 2) / H);
    s = expanded() ? best : Math.min(1, best);
    center();
    apply();
  }
  function zoomAt(cx, cy, factor) {
    const r = stage.getBoundingClientRect();
    const x = cx - r.left, y = cy - r.top;
    const ns = clamp(s * factor);
    tx = x - (x - tx) * (ns / s);
    ty = y - (y - ty) * (ns / s);
    s = ns;
    apply();
  }
  function zoomCenter(factor) {
    const r = stage.getBoundingClientRect();
    zoomAt(r.left + r.width / 2, r.top + r.height / 2, factor);
  }
  function setExpanded(on) {
    fig.classList.toggle("expanded", on);
    document.body.classList.toggle("locked", on);
    $('[data-act="full"]', fig).textContent = on ? "Exit full screen" : "Full screen";
    fit();
  }

  $(".toolbar", fig).addEventListener("click", (e) => {
    const act = e.target.closest("button")?.dataset.act;
    if (act === "in") zoomCenter(1.25);
    else if (act === "out") zoomCenter(1 / 1.25);
    else if (act === "fit") fit();
    else if (act === "one") { s = 1; center(); apply(); }
    else if (act === "full") setExpanded(!expanded());
  });
  stage.addEventListener("wheel", (e) => {
    if (!expanded() && !e.ctrlKey && !e.metaKey) return;
    e.preventDefault();
    zoomAt(e.clientX, e.clientY, Math.exp(-e.deltaY * (e.ctrlKey ? 0.01 : 0.0015)));
  }, { passive: false });
  stage.addEventListener("dblclick", fit);
  let drag = null;
  stage.addEventListener("pointerdown", (e) => {
    if (e.button !== 0) return;
    drag = { x: e.clientX, y: e.clientY };
    stage.classList.add("dragging");
    stage.setPointerCapture(e.pointerId);
  });
  stage.addEventListener("pointermove", (e) => {
    if (!drag) return;
    tx += e.clientX - drag.x;
    ty += e.clientY - drag.y;
    drag = { x: e.clientX, y: e.clientY };
    apply();
  });
  const endDrag = () => { drag = null; stage.classList.remove("dragging"); };
  stage.addEventListener("pointerup", endDrag);
  stage.addEventListener("pointercancel", endDrag);

  fit();
  return { fit, collapse: () => expanded() && setExpanded(false) };
}

addEventListener("keydown", (e) => { if (e.key === "Escape") viewers.forEach((v) => v.collapse()); });
let resizeTimer;
addEventListener("resize", () => { clearTimeout(resizeTimer); resizeTimer = setTimeout(() => viewers.forEach((v) => v.fit()), 120); });

// ---------------------------------------------------------------------------
// Navigation: the page list, the active page's outline, prev/next, routing.
// ---------------------------------------------------------------------------
function pageLabel(p) {
  const m = p.title.match(/^(\d+)\.\s*(.*)$/);
  return m ? `<span class="num">${m[1]}</span>${escapeHtml(m[2])}` : `<span class="num"></span>${escapeHtml(p.title)}`;
}

function buildNav(outlineFor) {
  const items = PAGES.map((p) => {
    const active = p.id === current;
    let outline = "";
    if (active && outlineFor) {
      const heads = [...outlineFor.querySelectorAll("h2")].map((h) => `<li><a href="#${p.id}/${h.id}">${escapeHtml(h.textContent.replace(/^#/, ""))}</a></li>`);
      if (heads.length) outline = `<ol class="outline">${heads.join("")}</ol>`;
    }
    return `<li class="${active ? "active" : ""}"><a href="#${p.id}">${pageLabel(p)}</a>${outline}</li>`;
  });
  $("#nav").innerHTML = `<h2>Pages</h2><ol>${items.join("")}</ol>`;
}

function pager(page) {
  const i = PAGES.indexOf(page);
  const link = (p, label) => (p ? `<a href="#${p.id}"><small>${label}</small>${escapeHtml(p.title)}</a>` : "<span></span>");
  return `<div class="pager">${link(PAGES[i - 1], "Previous")}${link(PAGES[i + 1], "Next")}</div>`;
}

async function renderPage(id, force = false) {
  const page = BY_ID.get(id) || PAGES[0];
  if (page.id === current && !force) return;
  current = page.id;
  slugger.reset();
  const main = $("#content");
  main.innerHTML = marked.parse(page.markdown) + pager(page);
  document.title = `${page.title} · vfs architecture`;
  $("#crumb").textContent = page.title;
  buildNav(main);
  await drawDiagrams(main);
}

async function route() {
  const raw = decodeURIComponent(location.hash.replace(/^#/, ""));
  const [pid, anchor] = raw.split("/");
  const samePage = pid === current;
  await renderPage(pid || PAGES[0].id);
  if (anchor) document.getElementById(anchor)?.scrollIntoView({ block: "start" });
  else if (!samePage) scrollTo(0, 0);
}

// Served over HTTP, read the .md files from disk so the view is never stale.
async function refreshFromDisk() {
  if (location.protocol === "file:") return false;
  const ok = await Promise.all(PAGES.map(async (p) => {
    try {
      const r = await fetch(p.file, { cache: "no-store" });
      if (!r.ok) return false;
      p.markdown = await r.text();
      return true;
    } catch { return false; }
  }));
  return ok.every(Boolean);
}

initMermaid();
const live = await refreshFromDisk();
const badge = $("#badge");
badge.textContent = live ? "live from the .md files" : `snapshot ${DATA.build.date} · ${DATA.build.commit}`;
badge.classList.toggle("live", live);
addEventListener("hashchange", route);
await route();
</script>
</body>
</html>
"""


if __name__ == "__main__":
    print(f"wrote {build()}")
