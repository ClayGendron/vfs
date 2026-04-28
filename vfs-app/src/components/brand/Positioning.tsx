export type PositioningRow = {
  already: string
  adds: string
}

/**
 * Direct comparison: "If you already use X / vfs adds Y." Renders as a
 * two-column schematic — left cell is mono+quiet, right cell is body type.
 * Hairline rules separate rows so it reads like a spec sheet.
 */
export function Positioning({ rows }: { rows: readonly PositioningRow[] }) {
  return (
    <div className="vfs-positioning-table" role="table">
      <div className="vfs-positioning-table-head" role="row">
        <div role="columnheader">If you already use…</div>
        <div role="columnheader">vfs adds</div>
      </div>
      {rows.map((r) => (
        <div className="vfs-positioning-row" role="row" key={r.already}>
          <div className="vfs-positioning-already" role="cell">
            <span className="vfs-positioning-arrow" aria-hidden="true">
              ↳
            </span>
            <span>{r.already}</span>
          </div>
          <div className="vfs-positioning-adds" role="cell">
            {r.adds}
          </div>
        </div>
      ))}
    </div>
  )
}
