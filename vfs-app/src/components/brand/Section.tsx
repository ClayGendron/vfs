import type { ReactNode } from "react"
import { cn } from "@/lib/utils"

export function Section({
  label,
  title,
  children,
  tight,
  className,
  id,
}: {
  label?: ReactNode
  title?: ReactNode
  children: ReactNode
  tight?: boolean
  className?: string
  id?: string
}) {
  return (
    <section
      id={id}
      className={cn("vfs-section", tight && "vfs-section--tight", className)}
    >
      {label && <div className="vfs-section-label">{label}</div>}
      {title && <h2 className="mb-10">{title}</h2>}
      {children}
    </section>
  )
}
