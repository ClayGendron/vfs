export type SpecMetric = {
  label: string
  value: string
  signal?: boolean
}

/**
 * Mono proof band that sits directly under the hero. Each cell is a
 * label + value pair. `signal: true` paints the value cobalt — used to
 * draw the eye to the strongest facts (tests, coverage).
 */
export function SpecStrip({ metrics }: { metrics: readonly SpecMetric[] }) {
  return (
    <aside className="vfs-spec-strip" aria-label="Project facts">
      {metrics.map((m) => (
        <div
          key={m.label}
          className={m.signal ? "vfs-spec-cell signal" : "vfs-spec-cell"}
        >
          <span className="lbl">{m.label}</span>
          <span className="val">{m.value}</span>
        </div>
      ))}
    </aside>
  )
}
