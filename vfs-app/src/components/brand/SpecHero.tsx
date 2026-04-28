import type { ReactNode } from "react"
import { useState } from "react"

export function SpecHero({
  topLeft,
  topRight,
  headline,
  mark,
  version,
  lede,
  side,
  code,
  install,
}: {
  topLeft?: ReactNode
  topRight?: ReactNode
  headline?: ReactNode
  mark?: ReactNode
  version?: ReactNode
  lede: ReactNode
  side?: ReactNode
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

  const showTop = topLeft || topRight
  const showMarkRow = mark || version

  return (
    <section className="vfs-hero">
      {showTop && (
        <div className="vfs-hero-top">
          <div className="vfs-hero-top-cell">{topLeft}</div>
          <div className="vfs-hero-top-cell vfs-hero-top-cell--right">
            {topRight}
          </div>
        </div>
      )}

      <div className="vfs-hero-body">
        <div className="vfs-hero-stage">
          <div className="vfs-hero-stage-text">
            {showMarkRow && (
              <div className="vfs-hero-mark-row">
                <span className="vfs-hero-mark-sigil" aria-hidden="true" />
                {mark && <span className="vfs-hero-mark-name">{mark}</span>}
                {version && (
                  <span className="vfs-hero-mark-version">{version}</span>
                )}
              </div>
            )}
            {headline && <h1 className="vfs-hero-headline">{headline}</h1>}
            <p className="vfs-hero-lede">{lede}</p>
            {side && <div className="vfs-hero-meta">{side}</div>}
          </div>
          {code && <div className="vfs-hero-code-col">{code}</div>}
        </div>
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
            <span className="vfs-install-sigil">$</span>
            <span>{install.cmd}</span>
          </button>
        </div>
      )}
    </section>
  )
}
