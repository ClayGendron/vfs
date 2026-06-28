import type { ReactNode } from "react"
import { cn } from "@/lib/utils"

export function Section({
  label,
  children,
  tight,
  className,
  id,
  pillar,
}: {
  label?: ReactNode
  children: ReactNode
  tight?: boolean
  className?: string
  id?: string
  /** Two-digit pillar id ("01"–"05") — drives the leading color tick on the label. */
  pillar?: string
}) {
  return (
    <section
      id={id}
      data-pillar={pillar}
      className={cn("vfs-section", tight && "tight", className)}
    >
      {label && <div className="vfs-section-label">{label}</div>}
      {children}
    </section>
  )
}

/**
 * Full-bleed section header — a Display tagline + lede that spans the content
 * width, used when the section body is a wide grid/table rather than the
 * standard 1fr / 2.4fr rail.
 */
export function SectionHead({
  tagline,
  children,
}: {
  tagline: ReactNode
  children?: ReactNode
}) {
  return (
    <div className="vfs-section-widehead">
      <h2 className="vfs-section-tagline lg">{tagline}</h2>
      {children && <p className="vfs-section-lede">{children}</p>}
    </div>
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
