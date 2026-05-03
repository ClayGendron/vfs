import type { ReactNode } from "react"
import { useState } from "react"

export function SpecHero({
  headline,
  lede,
  code,
  install,
}: {
  headline?: ReactNode
  lede: ReactNode
  code?: ReactNode
  install?: { cmd: string }
}) {
  const [copied, setCopied] = useState(false)

  const copy = async () => {
    if (!install) return
    try {
      await navigator.clipboard.writeText(install.cmd)
      setCopied(true)
      setTimeout(() => setCopied(false), 1200)
    } catch {
      // clipboard denied
    }
  }

  // Each line is its own block with `overflow: hidden` so the painted
  // ::selection rectangle (and any span-background or text-decoration that
  // would paint at the line-box extent) is clipped to that one line and
  // can't bleed into the adjacent line.
  //
  // Why this is the fix: in Chrome the selection rect is sized from the
  // font's strut (hhea/OS-2 ascent + descent + line-gap, ~1.15 em for
  // Saira), NOT from `line-height`. With `line-height: 1.02` the strut is
  // ~7.8px taller than the line spacing, so consecutive lines' selection
  // rects overlap by ~4px. `ascent-override`, `descent-override`,
  // `line-gap-override`, and `text-box-trim` all leave the painted
  // selection rect unchanged — `display: block; overflow: hidden` is the
  // only mechanism that actually clips the paint in current Chrome.
  // ReactNode children pass through unchanged so callers can opt out.
  const renderedHeadline =
    typeof headline === "string"
      ? headline.split("\n").map((line, i) => (
          <span key={i} className="vfs-hero-headline-line">
            {line}
          </span>
        ))
      : headline

  return (
    <section className="vfs-hero">
      <div className="vfs-hero-grid">
        <div className="vfs-hero-left">
          {renderedHeadline && (
            <h1 className="vfs-hero-headline">{renderedHeadline}</h1>
          )}
          <p className="vfs-hero-lede">{lede}</p>
        </div>
        {code && <div>{code}</div>}
      </div>

      {install && (
        <div className="vfs-install-row">
          <button
            type="button"
            className={copied ? "vfs-install-btn is-copied" : "vfs-install-btn"}
            onClick={copy}
            aria-label={`Copy install command: ${install.cmd}`}
            title="Click to copy"
          >
            <span className="sig">$</span>
            <span>{install.cmd}</span>
            <span className="copy-status">{copied ? "copied" : ""}</span>
          </button>
        </div>
      )}
    </section>
  )
}
