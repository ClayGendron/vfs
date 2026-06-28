import type { CSSProperties } from "react"
import { cn } from "@/lib/utils"

/**
 * grep · content — literal matches in text.
 *
 * Rows of "words" with a few matches, static by default. On hover a scan line
 * sweeps the rows and the matches flare — the feel of a regex pass landing on
 * exact hits.
 */

type Word = { w: number; match?: boolean }

const ROWS: Word[][] = [
  [{ w: 26 }, { w: 34, match: true }, { w: 18 }],
  [{ w: 16 }, { w: 22 }, { w: 40 }, { w: 14 }],
  [{ w: 30, match: true }, { w: 20 }, { w: 28 }],
  [{ w: 18 }, { w: 24 }, { w: 16 }, { w: 30, match: true }],
  [{ w: 36 }, { w: 18 }, { w: 22 }],
  [{ w: 20 }, { w: 28 }, { w: 16 }, { w: 24 }],
]

const X0 = 16
const GAP = 7
const Y0 = 20
const ROW_H = 22
const WORD_H = 7

export function GrepField({ active }: { active: boolean }) {
  let matchOrder = 0
  return (
    <svg
      viewBox="0 0 260 150"
      className={cn("vfs-field gp", active && "is-on")}
      preserveAspectRatio="xMidYMid meet"
      aria-hidden="true"
    >
      {ROWS.map((row, r) => {
        let x = X0
        const y = Y0 + r * ROW_H
        return row.map((word, c) => {
          const rect = (
            <rect
              key={`${r}-${c}`}
              className={cn("gp-word", word.match && "is-match")}
              x={x}
              y={y}
              width={word.w}
              height={WORD_H}
              rx="2"
              style={
                word.match ? ({ "--d": matchOrder++ } as CSSProperties) : undefined
              }
            />
          )
          x += word.w + GAP
          return rect
        })
      })}
      <rect className="gp-scan" x="12" y="14" width="120" height="2" rx="1" />
    </svg>
  )
}
