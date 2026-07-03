/**
 * §1 visual — heterogeneous backends collapsing into one namespace.
 *
 * A mono `tree` listing where every store hangs off a single `/` root as an
 * ordinary directory. The picture *is* the thesis: everything is a file, so
 * disparate backends share one addressable namespace. The footer shows the
 * payoff — results compose with set algebra over one envelope.
 */

import { SITE } from "@/lib/site"

const MOUNTS = SITE.mounts.filter((m) => m.treePath)

export function NamespaceTree() {
  return (
    <div
      className="vfs-tree"
      role="img"
      aria-label="One namespace mounted over Postgres, MSSQL, SQLite, and a graph store"
    >
      <div className="vfs-tree-row vfs-tree-root">
        <span className="vfs-tree-branch" aria-hidden="true">
          {"  "}
        </span>
        <span className="vfs-tree-path">/</span>
        <span className="vfs-tree-mount">one root</span>
      </div>
      {MOUNTS.map((m, i) => (
        <div className="vfs-tree-row" key={m.treePath}>
          <span className="vfs-tree-branch" aria-hidden="true">
            {i === MOUNTS.length - 1 ? "└─" : "├─"}
          </span>
          <span className="vfs-tree-path">{m.treePath}</span>
          <span className="vfs-tree-mount">{m.store}</span>
        </div>
      ))}
      <div className="vfs-tree-foot">
        <span className="vfs-tree-expr">
          (auth <span className="op">|</span> nearby) <span className="op">−</span>{" "}
          policy
        </span>
        <span className="vfs-tree-note">results compose · one envelope</span>
      </div>
    </div>
  )
}
