import type { ReactNode } from "react"
import { cn } from "@/lib/utils"

export function Section({
  label,
  children,
  tight,
  className,
  id,
}: {
  label?: ReactNode
  children: ReactNode
  tight?: boolean
  className?: string
  id?: string
}) {
  return (
    <section
      id={id}
      className={cn("vfs-section", tight && "tight", className)}
    >
      {label && <div className="vfs-section-label">{label}</div>}
      {children}
    </section>
  )
}

/**
 * The standard 1fr / 2.4fr two-column inside a section: left is a
 * Display-font tagline; right is body copy + content. Mirrors the
 * `vfs-section-grid` + `vfs-section-tagline` pattern from the design.
 */
export function SectionGrid({
  tagline,
  taglineSize,
  children,
}: {
  tagline: ReactNode
  taglineSize?: "default" | "lg"
  children: ReactNode
}) {
  return (
    <div className="vfs-section-grid">
      <h2
        className={cn(
          "vfs-section-tagline",
          taglineSize === "lg" && "lg",
        )}
      >
        {tagline}
      </h2>
      <div className="vfs-section-body">{children}</div>
    </div>
  )
}
