export type SpecMetric = {
  label: string
  value: string
}

/**
 * Mono proof band that sits directly under the hero. Each cell carries a
 * small uppercase label above the value so the strip reads like a
 * fact-sheet rather than a marketing claim. Separators live in CSS.
 */
export function SpecStrip({ metrics }: { metrics: readonly SpecMetric[] }) {
  return (
    <aside className="vfs-spec-strip" aria-label="Project facts">
      <div className="vfs-spec-strip-rule" aria-hidden="true" />
      <ul className="vfs-spec-strip-row">
        {metrics.map((m) => (
          <li key={m.label} className="vfs-spec-strip-cell">
            <div className="vfs-spec-strip-label">{m.label}</div>
            <div className="vfs-spec-strip-value">{m.value}</div>
          </li>
        ))}
      </ul>
      <div className="vfs-spec-strip-rule" aria-hidden="true" />
    </aside>
  )
}
