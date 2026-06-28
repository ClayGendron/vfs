import { Link } from "react-router-dom"

/**
 * §3 visual — search and action in one namespace.
 *
 * A scripted, deterministic terminal preview (no animation) that lists the
 * reserved `/.agents` tree, then shows one `glean` whose result set mixes a
 * document and a tool. The tool row carries a `run →` affordance — the single
 * idea being that the same search that finds knowledge also finds the
 * capability that acts on it, returned through one envelope.
 */
export function CapabilityTape({
  cta = "open the repl",
  to = "/terminal",
}: {
  cta?: string
  to?: string
}) {
  return (
    <div className="vfs-tape">
      <div className="vfs-tape-bar" aria-hidden="true">
        <span className="vfs-tape-bar-label">tty / capabilities</span>
        <span className="vfs-tape-bar-meta">vfs · noninteractive</span>
      </div>
      <pre className="vfs-tape-body" aria-label="Search and run share one namespace">
        <span className="vfs-tape-line">
          <span className="vfs-tape-prompt">$ </span>
          <span className="vfs-tape-cmd">vfs ls </span>
          <span className="vfs-tape-arg">/.agents</span>
        </span>
        <span className="vfs-tape-line">
          <span className="vfs-tape-arg"> tools/ skills/</span>
        </span>
        <span className="vfs-tape-line">
          <span className="vfs-tape-prompt">$ </span>
          <span className="vfs-tape-cmd">vfs glean </span>
          <span className="vfs-tape-arg">"rank Q3 revenue by region"</span>
        </span>
        <span className="vfs-tape-out-row">
          <span className="vfs-tape-out-path">/enterprise/finance/q3-revenue.md</span>
          <span className="vfs-tape-kind">doc</span>
        </span>
        <span className="vfs-tape-out-row">
          <span className="vfs-tape-out-path">/.agents/tools/sql-report/TOOL.md</span>
          <span className="vfs-tape-run">run →</span>
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
