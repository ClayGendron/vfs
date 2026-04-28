import { Card } from "@/components/ui/card"
import { cn } from "@/lib/utils"

export type ValueItem = { title: string; body: string }

export function Values({
  items,
  label = "cap.",
}: {
  items: ValueItem[]
  label?: string
}) {
  return (
    <div className="vfs-values">
      {items.map((v, i) => (
        <Card
          key={v.title}
          className={cn(
            "gap-0 rounded-none border border-[var(--rule)] bg-[var(--card)] px-6 py-7 ring-0",
            "transition-colors duration-200 hover:border-[color-mix(in_oklab,var(--accent)_50%,var(--rule))]"
          )}
        >
          <div className="vfs-value-label">
            {label} {String(i + 1).padStart(2, "0")}
          </div>
          <h3 className="vfs-value-title">{v.title}</h3>
          <div className="vfs-value-body">{v.body}</div>
        </Card>
      ))}
    </div>
  )
}
