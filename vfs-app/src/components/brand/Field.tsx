import type { ReactNode } from "react"
import { cn } from "@/lib/utils"

/**
 * Shared SVG scaffolding for the brand search-verb fields.
 *
 * Owns the identical <svg> wrapper each field returns: the viewBox, the
 * "vfs-field <code>" class (plus "is-on" when `active`), and the fixed
 * preserveAspectRatio / aria-hidden attributes. Fields that light their own
 * inner elements on hover simply omit `active` so the root stays neutral.
 */
export function Field({
  code,
  viewBox,
  active,
  children,
}: {
  code: string
  viewBox: string
  active?: boolean
  children: ReactNode
}) {
  return (
    <svg
      viewBox={viewBox}
      className={cn("vfs-field", code, active && "is-on")}
      preserveAspectRatio="xMidYMid meet"
      aria-hidden="true"
    >
      {children}
    </svg>
  )
}
