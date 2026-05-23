"""Chunking visualizer (exploratory tool, not production code).

Run:
    uv run python scripts/chunk_viz.py

Opens a local server at http://127.0.0.1:8765. Pick any supported file from
the repo on the left; toggle strategy and chunk_size at the top; see chunks
rendered with colored backgrounds in the main pane.

Every supported file — code, markup, config, data, *and* markdown/Python —
is parsed by its tree-sitter grammar (via ``tree-sitter-language-pack``, ~300
grammars) and chunked by one language-agnostic byte-span walker. Adding a
language is a single ``ext: "grammar"`` (or ``filename: "grammar"``) entry; no
per-language node-type knowledge. Markdown rides the same path because the
markdown grammar nests heading sections, so the walker cuts at heading
boundaries for free. Unmapped paths fall back to a plain recursive separator
split.

Strategies:
  - regex        : pure separator split (Tier-0; no parser)
  - ast_sections : one chunk per atomic AST node / structural unit (no packing
                   — over-fragments)
  - ast_packed   : structural units packed sequentially up to chunk_size
                   (recommended)
"""
from __future__ import annotations

import json
import sys
import time
import urllib.parse

sys.setrecursionlimit(20000)  # deep ASTs from the generic tree-sitter walker
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

REPO_ROOT = Path(__file__).parent.parent.resolve()
sys.path.insert(0, str(REPO_ROOT / "src"))

from vfs.chunking import recursive_text_split, split_with_line_ranges  # noqa: E402
from tree_sitter_language_pack import get_parser  # noqa: E402

PORT = 8765
GENERIC_FILL_SEPS = ("\n\n", "\n", " ", "")


# ── shared chunk builders ──────────────────────────────────────────────────

def _mk(text: str, line_start: int) -> dict:
    return {"text": text, "line_start": line_start, "line_end": line_start + text.count("\n")}


def _chunks_from_pieces(content: str, pieces: list[str]) -> list[dict]:
    """Build chunk dicts from exact content slices, tracking absolute lines."""
    out, pos = [], 0
    for p in pieces:
        line_start = content[:pos].count("\n") + 1
        out.append(_mk(p, line_start))
        pos += len(p)
    return out


# ── generic tree-sitter (every grammar in the language pack) ────────────────
#
# Language-agnostic structural chunking by recursive descent over byte spans.
# Any node that fits the budget is emitted whole; oversized nodes recurse into
# their children; the contiguous atomic spans are then greedily packed back up
# to the budget. Byte spans (not line spans) keep reconstruction exact when
# several nodes share a line — true across most grammars.

# The language-pack ships a Rust-native binding whose Node accessors are
# methods, and whose byte offsets index the UTF-8 encoding of the source.
def _call(attr):  # accessor is a bound method here, but be tolerant of props
    return attr() if callable(attr) else attr


_TS_PARSERS: dict[str, object] = {}


def _ts_parser(lang_name: str):
    parser = _TS_PARSERS.get(lang_name)
    if parser is None:
        parser = get_parser(lang_name)
        _TS_PARSERS[lang_name] = parser
    return parser


def _ts_atomic_spans(content: str, chunk_size: int, lang_name: str) -> list[tuple[int, int]]:
    """Contiguous, file-covering byte spans, each as coarse as fits the budget."""
    root = _call(_ts_parser(lang_name).parse(content).root_node)
    spans: list[tuple[int, int]] = []

    def visit(node) -> None:
        start, end = _call(node.start_byte), _call(node.end_byte)
        count = _call(node.named_child_count)
        if end - start <= chunk_size or count == 0:
            spans.append((start, end))
            return
        cursor = start
        for i in range(count):
            child = node.named_child(i)
            child_start = _call(child.start_byte)
            if child_start > cursor:  # interstitial text (punctuation, comments)
                spans.append((cursor, child_start))
            visit(child)
            cursor = _call(child.end_byte)
        if cursor < end:
            spans.append((cursor, end))

    visit(root)
    return spans


def _ts_chunks(content: str, chunk_size: int, lang_name: str, *, pack: bool) -> list[dict]:
    data = content.encode("utf-8")

    def emit(start: int, end: int, out: list[dict]) -> None:
        text = data[start:end].decode("utf-8", "replace")
        if not text.strip():
            return
        line_start = data[:start].count(b"\n") + 1
        if len(text) > chunk_size:  # leaf still too big: separator fallback
            base = line_start - 1
            for piece, rel, _ in split_with_line_ranges(
                text, chunk_size=chunk_size, overlap=0, separators=GENERIC_FILL_SEPS
            ):
                out.append(_mk(piece, base + rel))
        else:
            out.append(_mk(text, line_start))

    try:
        spans = _ts_atomic_spans(content, chunk_size, lang_name)
    except Exception:  # unparseable / binding hiccup: plain separator split
        return _chunks_from_pieces(
            content, recursive_text_split(content, chunk_size=chunk_size, overlap=0, separators=GENERIC_FILL_SEPS)
        )
    out: list[dict] = []
    if not pack:  # ast_sections: one chunk per atomic span
        for s, e in spans:
            emit(s, e, out)
        return out
    cur_s, cur_e = None, None  # ast_packed: greedily merge contiguous spans
    for s, e in spans:
        if cur_s is None:
            cur_s, cur_e = s, e
        elif e - cur_s <= chunk_size:
            cur_e = e
        else:
            emit(cur_s, cur_e, out)
            cur_s, cur_e = s, e
    if cur_s is not None:
        emit(cur_s, cur_e, out)
    return out


# ── language registry ──────────────────────────────────────────────────────
#
# Everything goes through the one generic byte-span walker above — markdown and
# Python included (tree-sitter's markdown grammar nests heading sections, so the
# walker cuts at heading boundaries for free). Only files with no grammar fall
# back to the plain recursive separator split.

# Extension → tree-sitter-language-pack grammar name. Validated against the
# pack's supported set at import (unknown names are dropped, not fatal).
_EXT_TO_TS_RAW: dict[str, str] = {
    # docs / literate (markdown grammar is heading-hierarchical)
    "md": "markdown", "mdx": "markdown", "markdown": "markdown",
    "rmd": "markdown", "qmd": "markdown",  # R Markdown / Quarto: markdown supersets
    # python
    "py": "python", "pyi": "python",
    # systems / compiled
    "rs": "rust", "go": "go", "c": "c", "h": "c", "cc": "cpp", "cpp": "cpp",
    "cxx": "cpp", "hpp": "cpp", "hh": "cpp", "hxx": "cpp", "cu": "cuda",
    "zig": "zig", "d": "d", "nim": "nim", "v": "v", "odin": "odin",
    # jvm / .net
    "java": "java", "kt": "kotlin", "kts": "kotlin", "scala": "scala",
    "groovy": "groovy", "cs": "csharp", "fs": "fsharp", "vb": "vb",
    # web / scripting
    "js": "javascript", "mjs": "javascript", "cjs": "javascript",
    "jsx": "javascript", "ts": "typescript", "mts": "typescript",
    "cts": "typescript", "tsx": "tsx", "vue": "vue", "svelte": "svelte",
    "astro": "astro", "php": "php", "rb": "ruby", "lua": "lua",
    "pl": "perl", "pm": "perl", "r": "r", "jl": "julia", "dart": "dart",
    "ex": "elixir", "exs": "elixir", "erl": "erlang", "clj": "clojure",
    "cljs": "clojure", "hs": "haskell", "ml": "ocaml", "swift": "swift",
    "elm": "elm", "gleam": "gleam", "sol": "solidity", "tcl": "tcl",
    # shell
    "sh": "bash", "bash": "bash", "zsh": "bash", "fish": "fish",
    "ps1": "powershell", "psm1": "powershell",
    # markup / docs / data
    "html": "html", "htm": "html", "xml": "xml", "css": "css",
    "scss": "scss", "less": "less", "json": "json", "json5": "json5",
    "yaml": "yaml", "yml": "yaml", "toml": "toml", "ini": "ini",
    "rst": "rst", "tex": "latex", "sql": "sql", "graphql": "graphql",
    "gql": "graphql", "proto": "proto", "tf": "terraform",
    "hcl": "hcl", "dockerfile": "dockerfile", "cmake": "cmake",
    "make": "make", "mk": "make", "nix": "nix", "vim": "vim",
    "csv": "csv", "tsv": "tsv",
}
# Special filenames with no usable extension (basename match takes priority).
_FILENAME_TO_TS_RAW: dict[str, str] = {
    "dockerfile": "dockerfile", "containerfile": "dockerfile",
    "makefile": "make", "gnumakefile": "make", "cmakelists.txt": "cmake",
    "go.mod": "gomod", "go.sum": "gosum", "go.work": "gowork",
    "requirements.txt": "requirements", ".gitignore": "gitignore",
    ".gitattributes": "gitattributes", ".editorconfig": "editorconfig",
}
try:
    import typing as _typing
    from tree_sitter_language_pack import SupportedLanguage as _Supported

    _AVAILABLE = set(_typing.get_args(_Supported))
except Exception:  # pragma: no cover - defensive
    _AVAILABLE = set(_EXT_TO_TS_RAW.values()) | set(_FILENAME_TO_TS_RAW.values())

EXT_TO_TS_LANG: dict[str, str] = {
    ext: lang for ext, lang in _EXT_TO_TS_RAW.items() if lang in _AVAILABLE
}
FILENAME_TO_TS_LANG: dict[str, str] = {
    name: lang for name, lang in _FILENAME_TO_TS_RAW.items() if lang in _AVAILABLE
}


def _ext(path: str) -> str:
    return path.rsplit(".", 1)[-1].lower() if "." in path else ""


def language_for_path(path: str) -> str | None:
    """Resolve a tree-sitter grammar name from a path (basename then extension)."""
    name = path.rsplit("/", 1)[-1].lower()
    if name in FILENAME_TO_TS_LANG:
        return FILENAME_TO_TS_LANG[name]
    return EXT_TO_TS_LANG.get(_ext(path))


def lang_label(path: str) -> str:
    """Human-readable language name for the chunk pane header."""
    return language_for_path(path) or "plain"


def chunk_dispatch(path: str, content: str, strategy: str, chunk_size: int) -> list[dict]:
    ts_lang = language_for_path(path)
    if ts_lang is None or strategy == "regex":
        return _chunks_from_pieces(
            content, recursive_text_split(content, chunk_size=chunk_size, overlap=0, separators=GENERIC_FILL_SEPS)
        )
    return _ts_chunks(content, chunk_size, ts_lang, pack=(strategy != "ast_sections"))


def find_files() -> list[str]:
    skip = {"node_modules", "__pycache__", "site", "dist", "build", "src_old", "tests_old"}
    files = []
    for p in REPO_ROOT.rglob("*"):
        if not p.is_file():
            continue
        if language_for_path(p.name) is None:
            continue
        if any(part.startswith(".") or part in skip for part in p.parts):
            continue
        files.append(str(p.relative_to(REPO_ROOT)))
    return sorted(files)


INDEX_HTML = """<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<title>Chunk visualizer</title>
<style>
  * { box-sizing: border-box; }
  body { font-family: -apple-system, BlinkMacSystemFont, sans-serif; margin: 0; display: flex; height: 100vh; color: #1a1a1a; }
  #sidebar { width: 340px; border-right: 1px solid #e5e5e5; overflow-y: auto; background: #fafafa; }
  #sidebar h3 { margin: 12px; font-size: 13px; text-transform: uppercase; color: #666; letter-spacing: 0.5px; }
  #filter { width: calc(100% - 24px); margin: 0 12px 8px; padding: 5px 8px; font-size: 12px; }
  .file { padding: 5px 12px; cursor: pointer; font-size: 12px; font-family: ui-monospace, "SF Mono", Menlo, monospace; display: flex; gap: 8px; align-items: center; }
  .file:hover { background: #eef; }
  .file.active { background: #2563eb; color: white; }
  .file .tag { font-size: 9px; font-weight: 700; padding: 1px 5px; border-radius: 3px; text-transform: uppercase; }
  .tag.md { background: #dbeafe; color: #1e40af; }
  .tag.py { background: #dcfce7; color: #166534; }
  .tag.js { background: #fef9c3; color: #854d0e; }
  .tag.ts { background: #e0e7ff; color: #3730a3; }
  .tag.txt { background: #e5e5e5; color: #525252; }
  .file.active .tag { background: rgba(255,255,255,0.25); color: white; }
  .file .name { white-space: nowrap; overflow: hidden; text-overflow: ellipsis; direction: rtl; text-align: left; }
  #main { flex: 1; display: flex; flex-direction: column; overflow: hidden; }
  #controls { padding: 12px 16px; border-bottom: 1px solid #e5e5e5; display: flex; gap: 20px; align-items: center; flex-wrap: wrap; }
  #controls label { font-size: 13px; }
  #controls input[type=number] { width: 90px; padding: 4px 6px; font-size: 13px; }
  .seg { display: inline-flex; border: 1px solid #d1d5db; border-radius: 6px; overflow: hidden; }
  .seg button { padding: 6px 12px; border: 0; background: white; cursor: pointer; font-size: 12px; }
  .seg button.active { background: #2563eb; color: white; }
  .seg button + button { border-left: 1px solid #d1d5db; }
  #stats { font-size: 12px; color: #666; margin-left: auto; }
  #view { flex: 1; overflow-y: auto; padding: 12px 16px; background: #fbfbfb; }
  .chunk { margin: 6px 0; border-radius: 6px; overflow: hidden; border: 1px solid; }
  .chunk-meta { padding: 4px 10px; font-size: 11px; font-family: -apple-system, sans-serif; display: flex; gap: 12px; align-items: center; }
  .chunk-meta .idx { font-weight: 600; }
  .chunk-body { padding: 8px 10px; font-family: ui-monospace, "SF Mono", Menlo, monospace; font-size: 11.5px; line-height: 1.5; white-space: pre-wrap; word-wrap: break-word; background: white; }
  .empty { padding: 40px; text-align: center; color: #999; }
</style>
</head>
<body>
<div id="sidebar">
  <h3>Files</h3>
  <input id="filter" placeholder="filter by path...">
  <div id="filelist">Loading...</div>
</div>
<div id="main">
  <div id="controls">
    <div class="seg" id="strategySeg">
      <button data-v="regex">regex</button>
      <button data-v="ast_sections">AST sections</button>
      <button data-v="ast_packed" class="active">AST packed</button>
    </div>
    <label>chunk_size <input id="chunkSize" type="number" value="2048" min="200" max="10000" step="128"></label>
    <span id="stats"></span>
  </div>
  <div id="view"><div class="empty">Pick a file from the sidebar.</div></div>
</div>
<script>
const COLORS = [
  ["#fef3c7", "#d97706"], ["#dbeafe", "#2563eb"], ["#dcfce7", "#16a34a"],
  ["#fce7f3", "#db2777"], ["#e0e7ff", "#6366f1"], ["#fed7aa", "#ea580c"],
  ["#f3e8ff", "#9333ea"], ["#cffafe", "#0891b2"], ["#fef9c3", "#ca8a04"],
  ["#fee2e2", "#dc2626"],
];

let activeFile = null;
let strategy = "ast_packed";
let allFiles = [];

async function loadFiles() {
  const r = await fetch("/files");
  allFiles = await r.json();
  renderFileList("");
}

function renderFileList(filter) {
  const list = document.getElementById("filelist");
  list.innerHTML = "";
  for (const f of allFiles) {
    if (filter && !f.toLowerCase().includes(filter.toLowerCase())) continue;
    const ext = f.split(".").pop().toLowerCase();
    const CLASS = {
      md: "md", mdx: "md", markdown: "md", py: "py",
      js: "js", mjs: "js", cjs: "js", jsx: "js",
      ts: "ts", mts: "ts", cts: "ts", tsx: "ts",
    };
    const cls = CLASS[ext] || "txt";
    const el = document.createElement("div");
    el.className = "file";
    el.title = f;
    el.innerHTML = `<span class="tag ${cls}">${ext}</span><span class="name">${f}</span>`;
    el.onclick = () => selectFile(f, el);
    if (f === activeFile) el.classList.add("active");
    list.appendChild(el);
  }
}

function selectFile(path, el) {
  document.querySelectorAll(".file").forEach(e => e.classList.remove("active"));
  el.classList.add("active");
  activeFile = path;
  refresh();
}

async function refresh() {
  if (!activeFile) return;
  const size = document.getElementById("chunkSize").value;
  const r = await fetch(`/chunk?path=${encodeURIComponent(activeFile)}&strategy=${strategy}&chunk_size=${size}`);
  const data = await r.json();
  render(data);
}

function render(data) {
  const view = document.getElementById("view");
  view.innerHTML = "";
  let totalChars = 0;
  data.chunks.forEach((c, i) => {
    const [bg, fg] = COLORS[i % COLORS.length];
    const div = document.createElement("div");
    div.className = "chunk";
    div.style.borderColor = fg;
    const meta = document.createElement("div");
    meta.className = "chunk-meta";
    meta.style.background = bg;
    meta.style.color = fg;
    meta.innerHTML = `
      <span class="idx">#${i + 1}</span>
      <span>L${c.line_start}-${c.line_end}</span>
      <span>${c.text.length.toLocaleString()} chars</span>
    `;
    div.appendChild(meta);
    const body = document.createElement("div");
    body.className = "chunk-body";
    body.textContent = c.text;
    div.appendChild(body);
    view.appendChild(div);
    totalChars += c.text.length;
  });
  const avg = data.chunks.length ? Math.round(totalChars / data.chunks.length) : 0;
  document.getElementById("stats").innerHTML =
    `<b>${data.lang}</b> · <b>${data.chunks.length}</b> chunks · avg <b>${avg.toLocaleString()}</b> chars ` +
    `· chunked in <b>${data.elapsed_ms.toFixed(1)}</b> ms`;
}

document.getElementById("chunkSize").addEventListener("input", refresh);
document.getElementById("filter").addEventListener("input", e => renderFileList(e.target.value));
document.querySelectorAll("#strategySeg button").forEach(btn => {
  btn.addEventListener("click", () => {
    document.querySelectorAll("#strategySeg button").forEach(b => b.classList.remove("active"));
    btn.classList.add("active");
    strategy = btn.dataset.v;
    refresh();
  });
});
loadFiles();
</script>
</body>
</html>
"""


class Handler(BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):
        return

    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path
        params = urllib.parse.parse_qs(parsed.query)
        if path in ("/", "/index.html"):
            self._send(200, "text/html; charset=utf-8", INDEX_HTML.encode())
        elif path == "/files":
            self._send_json(find_files())
        elif path == "/chunk":
            rel = params.get("path", [""])[0]
            strategy = params.get("strategy", ["ast_packed"])[0]
            chunk_size = int(params.get("chunk_size", ["2048"])[0])
            target = (REPO_ROOT / rel).resolve()
            if not str(target).startswith(str(REPO_ROOT)) or not target.exists():
                self._send(404, "text/plain", b"Not found")
                return
            if strategy not in ("regex", "ast_sections", "ast_packed"):
                self._send(400, "text/plain", b"Bad strategy")
                return
            content = target.read_text(encoding="utf-8")
            t0 = time.perf_counter()
            chunks = chunk_dispatch(rel, content, strategy, chunk_size)
            elapsed_ms = (time.perf_counter() - t0) * 1000
            self._send_json({
                "path": rel,
                "lang": lang_label(rel),
                "chunks": chunks,
                "elapsed_ms": elapsed_ms,
            })
        else:
            self._send(404, "text/plain", b"Not found")

    def _send(self, status, content_type, body):
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _send_json(self, payload):
        body = json.dumps(payload).encode()
        self._send(200, "application/json", body)


def main():
    server = HTTPServer(("127.0.0.1", PORT), Handler)
    print(f"Chunk visualizer running at http://127.0.0.1:{PORT}")
    print("Ctrl+C to stop.")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print()


if __name__ == "__main__":
    main()
