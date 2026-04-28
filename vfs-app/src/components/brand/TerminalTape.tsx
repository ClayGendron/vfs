import { Link } from "react-router-dom"

/**
 * Scripted, deterministic terminal preview. Mirrors the recommendation
 * doc — three commands, three result rows, then a CTA to /terminal.
 *
 * Implemented as a static block (no animation) so the homepage remains
 * trustworthy at first glance: what you see is what `vfs` actually does.
 */
export function TerminalTape({
  cta = "Try the REPL",
  to = "/terminal",
}: {
  cta?: string
  to?: string
}) {
  return (
    <div className="vfs-tape">
      <div className="vfs-tape-bar" aria-hidden="true">
        <span className="vfs-tape-bar-label">tty / preview</span>
        <span className="vfs-tape-bar-meta">vfs · noninteractive</span>
      </div>
      <pre className="vfs-tape-body" aria-label="Sample vfs session">
        <span className="vfs-tape-line">
          <span className="vfs-tape-prompt">$ </span>
          <span className="vfs-tape-cmd">vfs mount /enterprise </span>
          <span className="vfs-tape-arg">postgres://…</span>
        </span>
        <span className="vfs-tape-line">
          <span className="vfs-tape-prompt">$ </span>
          <span className="vfs-tape-cmd">vfs grep </span>
          <span className="vfs-tape-arg">"authenticate" /enterprise</span>
        </span>
        <span className="vfs-tape-line">
          <span className="vfs-tape-prompt">$ </span>
          <span className="vfs-tape-cmd">vfs nbr</span>
          <span className="vfs-tape-arg"> --depth 2</span>
          <span className="vfs-tape-pipe"> | </span>
          <span className="vfs-tape-cmd">vfs pagerank</span>
          <span className="vfs-tape-pipe"> | </span>
          <span className="vfs-tape-cmd">vfs top</span>
          <span className="vfs-tape-arg"> 5</span>
        </span>
        <span className="vfs-tape-out-row">
          <span className="vfs-tape-out-path">/enterprise/auth.py</span>
          <span className="vfs-tape-out-score">0.184</span>
        </span>
        <span className="vfs-tape-out-row">
          <span className="vfs-tape-out-path">/enterprise/session.py</span>
          <span className="vfs-tape-out-score">0.131</span>
        </span>
        <span className="vfs-tape-out-row">
          <span className="vfs-tape-out-path">/enterprise/policy.md</span>
          <span className="vfs-tape-out-score">0.097</span>
        </span>
      </pre>
      <div className="vfs-tape-cta">
        <Link to={to} className="vfs-tape-cta-link">
          <span>{cta}</span>
          <span aria-hidden="true" className="vfs-tape-cta-arrow">
            →
          </span>
        </Link>
      </div>
    </div>
  )
}
