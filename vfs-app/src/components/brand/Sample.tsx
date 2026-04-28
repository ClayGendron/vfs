import type { ReactNode } from "react"
import { Card } from "@/components/ui/card"
import { cn } from "@/lib/utils"

export function Sample({
  label,
  kind,
  children,
  className,
}: {
  label: ReactNode
  kind: ReactNode
  children: ReactNode
  className?: string
}) {
  return (
    <Card
      className={cn(
        "vfs-sample gap-0 border border-[var(--rule)] bg-[var(--card-strong)] p-0 ring-0",
        className,
      )}
    >
      <div className="vfs-sample-head">
        <span>{label}</span>
        <span>{kind}</span>
      </div>
      <pre className="vfs-sample-body">{children}</pre>
    </Card>
  )
}
