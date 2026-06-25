#!/usr/bin/env python3
# /// script
# requires-python = ">=3.9"
# dependencies = [
#     "pillow>=10",
#     "fonttools>=4.33",
#     "brotli>=1.0",
# ]
# ///
"""Render the "vfs" wordmark in Saira Stencil SemiBold (600) Italic.

The bounding box is computed from the *actual rendered pixels* (tightest
rectangle containing the left/right/top/bottom-most ink), and the text is then
perfectly centered on a padded square canvas.

Uses the project's own Saira Stencil font (the static 600-italic .woff2 shipped
via @fontsource/saira-stencil), decompressed to TTF so Pillow can read it.

Run with uv:
    uv run scripts/make_logo.py
"""
from __future__ import annotations

import argparse
from pathlib import Path

from fontTools.ttLib import TTFont
from PIL import Image, ImageDraw, ImageFont

REPO = Path(__file__).resolve().parent.parent
PUBLIC_DIR = REPO / "vfs-app/public"  # Vite serves this at the site root

# Saira Stencil static font (600 italic) shipped with the web app.
SAIRA_WOFF2 = (
    REPO
    / "vfs-app/node_modules/@fontsource/saira-stencil/files"
    / "saira-stencil-latin-600-italic.woff2"
)

# Pluto brand signal — cobalt --accent from vfs-app/src/index.css (light mode).
PLUTO_BLUE = (0x2F, 0x58, 0xCF)
# Brighter cobalt for the transparent favicon: clears WCAG 3:1 graphic contrast
# on both light and dark browser tabs, where the deeper brand cobalt is too dim.
PLUTO_BLUE_BRIGHT = (0x3E, 0x6B, 0xEF)
BLACK = (0x0B, 0x0B, 0x0D)  # "night" ink from the Pluto palette
WHITE = (0xF1, 0xF1, 0xEE)  # "frost" paper from the Pluto palette

TEXT = "vfs"


def woff2_to_ttf(woff2: Path, out: Path) -> Path:
    """Decompress a .woff2 to a plain .ttf that FreeType/Pillow can read."""
    font = TTFont(str(woff2))  # reads woff2 (needs brotli)
    font.flavor = None  # strip woff2 wrapper -> raw sfnt
    out.parent.mkdir(parents=True, exist_ok=True)
    font.save(str(out))
    return out


def load_saira(ttf: Path, px: int) -> ImageFont.FreeTypeFont:
    """Load the static Saira Stencil face at the given pixel size."""
    return ImageFont.truetype(str(ttf), px)


def draw_corner_frame(
    img: Image.Image,
    color: tuple[int, int, int],
    inset_frac: float = 0.05,
    arm_frac: float = 0.12,
    thick_frac: float = 0.036,
) -> None:
    """Draw an L-shaped 90° bracket in each corner (spec-sheet crop marks)."""
    d = ImageDraw.Draw(img)
    s = img.width
    inset = round(s * inset_frac)
    arm = round(s * arm_frac)
    t = max(2, round(s * thick_frac))
    lo, hi = inset, s - inset
    fill = color + (255,)
    for x, y, dx, dy in ((lo, lo, 1, 1), (hi, lo, -1, 1),
                         (lo, hi, 1, -1), (hi, hi, -1, -1)):
        # Horizontal arm + vertical arm meeting at the corner (x, y).
        d.rectangle(sorted_box(x, y, x + dx * arm, y + dy * t), fill=fill)
        d.rectangle(sorted_box(x, y, x + dx * t, y + dy * arm), fill=fill)


def sorted_box(x0: int, y0: int, x1: int, y1: int) -> tuple[int, int, int, int]:
    return (min(x0, x1), min(y0, y1), max(x0, x1), max(y0, y1))


def render_pixel_perfect(
    font: ImageFont.FreeTypeFont,
    text: str,
    fg: tuple[int, int, int],
    bg: tuple[int, int, int] | None,
    pad_frac: float,
    frame: bool = True,
) -> Image.Image:
    """Render text, crop to its true pixel bbox, center on a padded square."""
    # 1. Render onto a generously oversized transparent scratch layer.
    scratch = Image.new("RGBA", (1, 1))
    d = ImageDraw.Draw(scratch)
    l, t, r, b = d.textbbox((0, 0), text, font=font)
    margin = max(r - l, b - t)  # leave room for italic overhang / negative bbox
    W, H = (r - l) + 2 * margin, (b - t) + 2 * margin
    layer = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    ImageDraw.Draw(layer).text(
        (margin - l, margin - t), text, font=font, fill=fg + (255,)
    )

    # 2. Tightest rectangle containing every inked (non-transparent) pixel.
    bbox = layer.getbbox()
    if bbox is None:
        raise RuntimeError("Nothing was rendered — check the font/text.")
    glyphs = layer.crop(bbox)
    gw, gh = glyphs.size

    # 3. Square canvas with even padding; text centered to sub-pixel midpoint.
    side = max(gw, gh)
    pad = round(side * pad_frac)
    canvas_side = side + 2 * pad
    canvas = Image.new("RGBA", (canvas_side, canvas_side), (0, 0, 0, 0))
    ox = (canvas_side - gw) // 2
    oy = (canvas_side - gh) // 2
    canvas.alpha_composite(glyphs, (ox, oy))

    if bg is not None:
        out = Image.new("RGBA", canvas.size, bg + (255,))
        out.alpha_composite(canvas)
        canvas = out
    if frame:
        draw_corner_frame(canvas, fg)
    return canvas


# Tab-icon padding. The glyph fill fraction is 1 / (1 + 2 * pad_frac); these
# values make the "vfs" glyph ~20% larger in the square than the previous
# 0.12 / 0.22 padding (i.e. fill fraction scaled by 1.2).
FAVICON_PAD = 0.017   # was 0.12
APPLE_PAD = 0.10      # was 0.22


def write_favicons(font: ImageFont.FreeTypeFont, out: Path) -> list[Path]:
    """Emit browser tab-icon assets (balanced cobalt) into the Vite public dir.

    The glyph is rendered frameless and tightly padded so it stays legible at
    16 px — unlike the padded, crop-marked logo files. All tab icons are
    transparent; note iOS composites the apple-touch-icon onto black, so the
    cobalt glyph there will sit on black on a home screen.
    """
    out.mkdir(parents=True, exist_ok=True)
    written: list[Path] = []

    # Transparent master for the .ico / .png tab icons.
    master = render_pixel_perfect(
        font, TEXT, PLUTO_BLUE_BRIGHT, None, pad_frac=FAVICON_PAD, frame=False
    )
    ico = out / "favicon.ico"
    master.save(ico, sizes=[(16, 16), (32, 32), (48, 48)])
    written.append(ico)

    png = out / "favicon-96x96.png"
    master.resize((96, 96), Image.LANCZOS).save(png)
    written.append(png)

    # Apple touch icon: transparent, like the rest of the tab icons.
    apple = render_pixel_perfect(
        font, TEXT, PLUTO_BLUE_BRIGHT, None, pad_frac=APPLE_PAD, frame=False
    )
    apple_png = out / "apple-touch-icon.png"
    apple.resize((180, 180), Image.LANCZOS).save(apple_png)
    written.append(apple_png)

    return written


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--out", type=Path, default=REPO / "logos",
                    help="output directory (default: ./logos)")
    ap.add_argument("--size", type=int, default=1600,
                    help="font pixel size used for rendering (default: 1600)")
    ap.add_argument("--pad", type=float, default=0.28,
                    help="padding as a fraction of the text's larger side")
    ap.add_argument("--no-frame", dest="frame", action="store_false",
                    help="omit the corner brackets")
    ap.add_argument("--no-favicon", dest="favicon", action="store_false",
                    help="skip writing tab-icon assets into vfs-app/public")
    args = ap.parse_args()

    if not SAIRA_WOFF2.exists():
        raise SystemExit(f"Saira Stencil font not found at {SAIRA_WOFF2}\n"
                         "Run `npm install @fontsource/saira-stencil` in vfs-app first.")

    ttf = woff2_to_ttf(SAIRA_WOFF2, args.out / ".cache" / "saira-stencil-600-italic.ttf")
    font = load_saira(ttf, args.size)
    args.out.mkdir(parents=True, exist_ok=True)

    variants = {
        "vfs-logo-black.png": (BLACK, WHITE),
        "vfs-logo-pluto.png": (PLUTO_BLUE, WHITE),
        "vfs-logo-black-transparent.png": (BLACK, None),
        "vfs-logo-pluto-transparent.png": (PLUTO_BLUE_BRIGHT, None),
    }
    for name, (fg, bg) in variants.items():
        img = render_pixel_perfect(font, TEXT, fg, bg, args.pad, args.frame)
        path = args.out / name
        img.save(path)
        print(f"  {path.relative_to(REPO)}  ({img.width}x{img.height})")

    print(f"\nDone — wrote {len(variants)} logos to {args.out.relative_to(REPO)}/")

    if args.favicon and PUBLIC_DIR.parent.exists():
        for path in write_favicons(font, PUBLIC_DIR):
            print(f"  {path.relative_to(REPO)}")
        print(f"Wrote tab-icon assets to {PUBLIC_DIR.relative_to(REPO)}/")


if __name__ == "__main__":
    main()
