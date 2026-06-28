import type { CSSProperties } from "react"
import { cn } from "@/lib/utils"

/**
 * glob · location — an abstract file tree.
 *
 * Folder/file rows with tree guides and blank name bars (no literal names),
 * stripped back to match grep's rectangle language. The tree rests static; on
 * hover a selection box fills in left-to-right behind each matched leaf and the
 * branch from root down to it resolves in colour, segment by segment — a glob
 * pattern retrieving the paths that match.
 */

type Row = {
  level: number
  dir?: boolean
  w: number // name-bar width
  match?: boolean
  step?: number // present when on the resolved path (drives the stagger)
}

const ROWS: Row[] = [
  { level: 0, dir: true, w: 44, step: 0 }, // root/
  { level: 1, dir: true, w: 36, step: 1 }, //  matched dir/
  { level: 2, dir: true, w: 32, step: 2 }, //   matched sub/
  { level: 3, w: 38, match: true, step: 3 }, //    file ✓
  { level: 3, w: 28, match: true, step: 3 }, //    file ✓
  { level: 2, w: 34 }, //   file
  { level: 1, dir: true, w: 40 }, //  dir/
  { level: 2, w: 30 }, //   file
  { level: 1, w: 48 }, //  file
]

const VB_W = 260
const VB_H = 150
const X0 = 16
const INDENT = 22
const GLYPH = 9
const Y0 = 14
const ROW_H = 15
const BAR_GAP = 8
const BAR_H = 6

const glyphX = (level: number) => X0 + level * INDENT
const rowY = (i: number) => Y0 + i * ROW_H

// nearest preceding row one level up — the row's parent in the tree
function parentOf(i: number): number {
  for (let j = i - 1; j >= 0; j--) {
    if (ROWS[j].level === ROWS[i].level - 1) return j
  }
  return -1
}

export function GlobField({ active }: { active: boolean }) {
  return (
    <svg
      viewBox={`0 0 ${VB_W} ${VB_H}`}
      className={cn("vfs-field gb", active && "is-on")}
      preserveAspectRatio="xMidYMid meet"
      aria-hidden="true"
    >
      {/* connector guides: an elbow from each row up to its parent */}
      {ROWS.map((r, i) => {
        if (r.level === 0) return null
        const p = parentOf(i)
        if (p < 0) return null
        const gx = glyphX(r.level - 1) + GLYPH / 2
        const py = rowY(p) + GLYPH
        const y = rowY(i) + GLYPH / 2
        const onPath = r.step !== undefined
        return (
          <path
            key={`g${i}`}
            className={cn("gb-guide", onPath && "is-path")}
            style={onPath ? ({ "--d": r.step } as CSSProperties) : undefined}
            d={`M${gx},${py} V${y} H${glyphX(r.level)}`}
          />
        )
      })}

      {/* selection box behind each match — fills in on hover */}
      {ROWS.map((r, i) =>
        r.match ? (
          <rect
            key={`s${i}`}
            className="gb-sel"
            x={glyphX(r.level) - 3}
            y={rowY(i) - 3}
            width={GLYPH + BAR_GAP + r.w + 7}
            height={GLYPH + 6}
            rx="2.5"
            style={{ "--d": r.step ?? 0 } as CSSProperties}
          />
        ) : null,
      )}

      {/* rows: folder/file glyph + blank name bar */}
      {ROWS.map((r, i) => {
        const gx = glyphX(r.level)
        const y = rowY(i)
        const onPath = r.step !== undefined
        return (
          <g key={`r${i}`}>
            <rect
              className={cn(
                "gb-glyph",
                r.dir && "is-dir",
                r.match && "is-match",
                onPath && "is-path",
              )}
              style={onPath ? ({ "--d": r.step } as CSSProperties) : undefined}
              x={gx}
              y={y}
              width={GLYPH}
              height={GLYPH}
              rx="1.5"
            />
            <rect
              className={cn(
                "gb-bar",
                r.match && "is-match",
                onPath && "is-path",
              )}
              style={onPath ? ({ "--d": r.step } as CSSProperties) : undefined}
              x={gx + GLYPH + BAR_GAP}
              y={y + (GLYPH - BAR_H) / 2}
              width={r.w}
              height={BAR_H}
              rx="2"
            />
          </g>
        )
      })}
    </svg>
  )
}
