export type IntegrationGroup = {
  group: string
  items: readonly string[]
}

/**
 * Plain-text ecosystem grid. Mono labels, square borders, no logo polish.
 * Each group is a stacked column: the group name sits on a hairline rule,
 * items list below in mono with a leading `·` marker.
 */
export function IntegrationsGrid({
  groups,
}: {
  groups: readonly IntegrationGroup[]
}) {
  return (
    <div className="vfs-integrations">
      {groups.map((g) => (
        <div className="vfs-integration" key={g.group}>
          <div className="vfs-integration-head">
            <span className="vfs-integration-marker" aria-hidden="true">
              ./
            </span>
            <span className="vfs-integration-name">{g.group}</span>
          </div>
          <ul className="vfs-integration-list">
            {g.items.map((item) => (
              <li key={item}>
                <span className="vfs-integration-dot" aria-hidden="true">
                  ·
                </span>
                <span>{item}</span>
              </li>
            ))}
          </ul>
        </div>
      ))}
    </div>
  )
}
