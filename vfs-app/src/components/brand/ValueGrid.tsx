import { VALUE_AREAS } from "@/lib/site"

/**
 * The value areas as a ruled plate grid — what vfs gives an agent that a
 * vector index, an fsspec mount, or a tool-per-query-shape does not.
 */
export function ValueGrid() {
  return (
    <div className="vfs-values">
      {VALUE_AREAS.map((v) => (
        <article className="vfs-value" key={v.id}>
          <span className="id">{v.id}</span>
          <h3>{v.title}</h3>
          <p>{v.body}</p>
          <span className="note">{v.note}</span>
        </article>
      ))}
    </div>
  )
}
