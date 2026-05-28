#!/usr/bin/env python3
# /// script
# requires-python = ">=3.9"
# dependencies = [
#     "pillow>=10",
#     "fonttools>=4.33",
#     "brotli>=1.0",
# ]
# ///
"""Render the transparent "vfs" favicon in several cobalt shades and emit an
HTML page that previews each one on real light/dark browser-tab backgrounds.

Reuses the rendering pipeline from make_logo.py so the glyphs match the logo
exactly. Output lands in ./logos/favicon-preview/ — open index.html.

Run with uv:
    uv run scripts/favicon_contrast_preview.py
"""
from __future__ import annotations

import importlib.util
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent

# Import make_logo.py's helpers (same dir) without running its main().
_spec = importlib.util.spec_from_file_location(
    "make_logo", Path(__file__).resolve().parent / "make_logo.py"
)
make_logo = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(make_logo)

# Candidate cobalt shades (same 225° hue, increasing lightness).
CANDIDATES = {
    "brand #2F58CF": (0x2F, 0x58, 0xCF),
    "mid   #3661DF": (0x36, 0x61, 0xDF),
    "balanced #3E6BEF": (0x3E, 0x6B, 0xEF),
}

# Representative tab backgrounds the transparent icon will actually sit on.
LIGHT_TABS = {"white #FFFFFF": (255, 255, 255),
              "chrome light #DEE1E6": (0xDE, 0xE1, 0xE6)}
DARK_TABS = {"chrome dark #202124": (0x20, 0x21, 0x24),
             "night #0B0B0D": (0x0B, 0x0B, 0x0D)}


def lin(c: float) -> float:
    c /= 255
    return c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4


def lum(rgb: tuple[int, int, int]) -> float:
    r, g, b = (lin(x) for x in rgb)
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def ratio(a: tuple[int, int, int], b: tuple[int, int, int]) -> float:
    la, lb = lum(a), lum(b)
    hi, lo = max(la, lb), min(la, lb)
    return (hi + 0.05) / (lo + 0.05)


def hexstr(rgb: tuple[int, int, int]) -> str:
    return "#{:02X}{:02X}{:02X}".format(*rgb)


def main() -> None:
    out = REPO / "logos" / "favicon-preview"
    out.mkdir(parents=True, exist_ok=True)

    if not make_logo.SAIRA_WOFF2.exists():
        raise SystemExit(f"Saira Stencil font not found at {make_logo.SAIRA_WOFF2}")
    ttf = make_logo.woff2_to_ttf(make_logo.SAIRA_WOFF2,
                                 out / ".cache" / "saira-stencil-600-italic.ttf")
    font = make_logo.load_saira(ttf, 1600)

    # One transparent PNG per candidate (no frame — favicons don't want crop marks).
    files: dict[str, str] = {}
    for label, rgb in CANDIDATES.items():
        img = make_logo.render_pixel_perfect(
            font, make_logo.TEXT, rgb, None, pad_frac=0.12, frame=False
        )
        fname = f"vfs-{hexstr(rgb).lstrip('#')}.png"
        img.save(out / fname)
        files[label] = fname
        print(f"  {(out / fname).relative_to(REPO)}  ({img.width}x{img.height})")

    html = build_html(files)
    (out / "index.html").write_text(html)
    print(f"\nOpen {(out / 'index.html').relative_to(REPO)}")


def build_html(files: dict[str, str]) -> str:
    def cell(rgb, fname, bg, bg_name, dark):
        r = ratio(rgb, bg)
        ok = r >= 3.0
        badge = "#16a34a" if ok else "#dc2626"
        verdict = "PASS ≥3" if ok else "FAIL <3"
        fg = "#f1f1ee" if dark else "#0b0b0d"
        return f"""
        <div class="cell" style="background:{hexstr(bg)};color:{fg}">
          <div class="sizes">
            <img src="{fname}" width="16" height="16" alt="">
            <img src="{fname}" width="32" height="32" alt="">
            <img src="{fname}" width="64" height="64" alt="">
          </div>
          <div class="meta">
            <span class="bgname">{bg_name}</span>
            <span class="ratio" style="background:{badge}">{r:.2f}:1 · {verdict}</span>
          </div>
        </div>"""

    rows = []
    for label, fname in files.items():
        rgb = CANDIDATES[label]
        light = "".join(cell(rgb, fname, bg, n, False) for n, bg in LIGHT_TABS.items())
        dark = "".join(cell(rgb, fname, bg, n, True) for n, bg in DARK_TABS.items())
        rows.append(f"""
      <section>
        <h2><span class="sw" style="background:{hexstr(rgb)}"></span>{label}</h2>
        <div class="grid">{light}{dark}</div>
      </section>""")

    # The glyph alpha shape (same in every candidate PNG) drives a CSS mask so
    # the picker can recolor it live. JS gets the tab backgrounds + dark flag.
    mask = next(iter(files.values()))
    tabs_js = ",".join(
        f'{{name:"{n}",hex:"{hexstr(bg)}",dark:{str(d).lower()}}}'
        for d, group in ((False, LIGHT_TABS), (True, DARK_TABS))
        for n, bg in group.items()
    )

    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<title>vfs favicon contrast preview</title>
<style>
  :root {{ color-scheme: light dark; }}
  body {{ font:14px/1.5 system-ui,sans-serif; margin:0; padding:32px;
         background:#fafafa; color:#111; }}
  h1 {{ font-size:18px; margin:0 0 4px; }}
  p.lead {{ color:#666; margin:0 0 28px; max-width:60ch; }}
  section {{ margin:0 0 32px; }}
  h2 {{ font-size:15px; display:flex; align-items:center; gap:10px; margin:0 0 12px; }}
  .sw {{ width:18px; height:18px; border-radius:4px; box-shadow:0 0 0 1px #0002; }}
  .grid {{ display:grid; grid-template-columns:repeat(4,1fr); gap:14px; }}
  .cell {{ border-radius:10px; padding:18px 16px; box-shadow:0 0 0 1px #0001;
          display:flex; flex-direction:column; gap:14px; }}
  .sizes {{ display:flex; align-items:flex-end; gap:16px; min-height:64px; }}
  .glyph {{ background:var(--c); -webkit-mask:var(--m) center/contain no-repeat;
           mask:var(--m) center/contain no-repeat; }}
  .meta {{ display:flex; flex-direction:column; gap:6px; font-size:12px; }}
  .bgname {{ opacity:.7; }}
  .ratio {{ align-self:flex-start; color:#fff; padding:2px 8px; border-radius:999px;
           font-weight:600; letter-spacing:.02em; }}
  .picker {{ background:#fff; border-radius:12px; padding:20px; margin:0 0 36px;
            box-shadow:0 0 0 1px #0001; }}
  .controls {{ display:flex; align-items:center; gap:12px; margin:0 0 16px; }}
  .controls input[type=color] {{ width:48px; height:36px; padding:0; border:none;
            border-radius:8px; background:none; cursor:pointer; }}
  .controls input[type=text] {{ font:600 14px ui-monospace,monospace; width:9ch;
            padding:8px 10px; border:1px solid #0002; border-radius:8px;
            text-transform:uppercase; }}
  @media (prefers-color-scheme: dark) {{
    body {{ background:#161616; color:#eee; }}
    p.lead {{ color:#aaa; }}
    .picker {{ background:#222; }}
    .controls input[type=text] {{ background:#111; color:#eee; border-color:#fff3; }}
  }}
</style></head>
<body>
  <h1>vfs favicon — cobalt contrast across tab backgrounds</h1>
  <p class="lead">Each transparent icon shown at 16 / 32 / 64&nbsp;px on the
  light and dark tab colors it will actually sit on. Badge = WCAG non-text
  (graphic) contrast; ≥3:1 is the bar for a legible icon.</p>

  <section class="picker">
    <h2>Try a color</h2>
    <div class="controls">
      <input type="color" id="pick" value="#3E6BEF">
      <input type="text" id="hex" value="#3E6BEF" maxlength="7">
    </div>
    <div class="grid" id="live"></div>
  </section>
  {''.join(rows)}

<script>
  const MASK = "url({mask})";
  const TABS = [{tabs_js}];
  const lin = c => (c/=255, c<=0.03928 ? c/12.92 : Math.pow((c+0.055)/1.055,2.4));
  const lum = ([r,g,b]) => 0.2126*lin(r)+0.7152*lin(g)+0.0722*lin(b);
  const rgb = h => [1,3,5].map(i => parseInt(h.slice(i,i+2),16));
  const ratio = (a,b) => {{
    const la=lum(a), lb=lum(b), hi=Math.max(la,lb), lo=Math.min(la,lb);
    return (hi+0.05)/(lo+0.05);
  }};
  const live = document.getElementById("live");
  const pick = document.getElementById("pick");
  const hex  = document.getElementById("hex");

  function render(h) {{
    if (!/^#[0-9a-fA-F]{{6}}$/.test(h)) return;
    const c = rgb(h);
    live.innerHTML = TABS.map(t => {{
      const r = ratio(c, rgb(t.hex)), ok = r >= 3;
      const fg = t.dark ? "#f1f1ee" : "#0b0b0d";
      const badge = ok ? "#16a34a" : "#dc2626";
      const glyph = px =>
        `<div class="glyph" style="--c:${{h}};--m:${{MASK}};width:${{px}}px;height:${{px}}px"></div>`;
      return `<div class="cell" style="background:${{t.hex}};color:${{fg}}">
        <div class="sizes">${{glyph(16)}}${{glyph(32)}}${{glyph(64)}}</div>
        <div class="meta"><span class="bgname">${{t.name}}</span>
        <span class="ratio" style="background:${{badge}}">${{r.toFixed(2)}}:1 · ${{ok?"PASS ≥3":"FAIL <3"}}</span>
        </div></div>`;
    }}).join("");
  }}
  pick.addEventListener("input", e => {{ hex.value = e.target.value.toUpperCase(); render(hex.value); }});
  hex.addEventListener("input", e => {{
    const v = e.target.value.trim();
    if (/^#[0-9a-fA-F]{{6}}$/.test(v)) {{ pick.value = v; render(v); }}
  }});
  render(hex.value);
</script>
</body></html>"""


if __name__ == "__main__":
    main()
