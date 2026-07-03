import { useEffect, useState } from "react"
import type { CSSProperties } from "react"
import { cn } from "@/lib/utils"
import { pickDistinct, randInt } from "@/lib/pickDistinct"
import { Field } from "./Field"

/**
 * glob · location — an abstract file tree.
 *
 * Folder/file rows with tree guides and blank name bars (no literal names),
 * stripped back to match grep's rectangle language. The tree rests neutral;
 * on each play 1–3 leaves are chosen at random, a selection box fills in behind
 * each, and the branch from root down to it resolves in colour segment by
 * segment — a glob pattern retrieving the paths that match.
 */

type Row = {
  level: number
  dir?: boolean
  w: number // name-bar width
}

const ROWS: Row[] = [
  { level: 0, dir: true, w: 44 }, // root/
  { level: 1, dir: true, w: 36 }, //  dir/
  { level: 2, dir: true, w: 32 }, //   sub/
  { level: 3, w: 38 }, //    file
  { level: 3, w: 28 }, //    file
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
  const ri = ROWS[i]
  if (!ri) return -1
  for (let j = i - 1; j >= 0; j--) {
    if (ROWS[j]?.level === ri.level - 1) return j
  }
  return -1
}

// file (leaf) rows — the paths a glob can land on
const LEAVES = ROWS.flatMap((r, i) => (r.dir ? [] : [i]))

type Selection = { matched: Set<number>; onPath: Set<number> }
const EMPTY: Selection = { matched: new Set(), onPath: new Set() }

// pick 1–3 leaves at random; the resolved path is the union of their ancestors
function pickSelection(): Selection {
  const matched = new Set(
    pickDistinct(randInt(1, 3), LEAVES.length)
      .map((i) => LEAVES[i])
      .filter((n): n is number => n !== undefined),
  )
  const onPath = new Set<number>()
  for (const leaf of matched) {
    for (let cur = leaf; cur >= 0; cur = parentOf(cur)) onPath.add(cur)
  }
  return { matched, onPath }
}

export function GlobField({ active }: { active: boolean }) {
  const [sel, setSel] = useState<Selection>(EMPTY)

  // fresh paths on each play; clears back to neutral when the spotlight leaves.
  // deferred a frame so the re-roll lands outside render, not synchronously.
  useEffect(() => {
    const id = requestAnimationFrame(() => setSel(active ? pickSelection() : EMPTY))
    return () => cancelAnimationFrame(id)
  }, [active])

  return (
    <Field code="gb" viewBox={`0 0 ${VB_W} ${VB_H}`} active={active}>
      {/* connector guides: an elbow from each row up to its parent. Drawn with
          non-path elbows first so the lit (on-path) ones paint on top — sibling
          verticals share a column, and a later gray stroke would otherwise
          cover the blue segment beneath it. The stagger (--d) tracks tree depth
          so the branch resolves root-first. */}
      {ROWS.map((r, i) => {
        const p = r.level > 0 ? parentOf(i) : -1
        if (p < 0) return null
        const gx = glyphX(r.level - 1) + GLYPH / 2
        const py = rowY(p) + GLYPH
        const y = rowY(i) + GLYPH / 2
        const onPath = sel.onPath.has(i)
        return { i, onPath, step: r.level, d: `M${gx},${py} V${y} H${glyphX(r.level)}` }
      })
        .filter((g): g is NonNullable<typeof g> => g !== null)
        .sort((a, b) => Number(a.onPath) - Number(b.onPath))
        .map((g) => (
          <path
            key={`g${g.i}`}
            className={cn("gb-guide", g.onPath && "is-path")}
            style={g.onPath ? ({ "--d": g.step } as CSSProperties) : undefined}
            d={g.d}
          />
        ))}

      {/* selection box behind each match — fills in on hover */}
      {ROWS.map((r, i) =>
        sel.matched.has(i) ? (
          <rect
            key={`s${i}`}
            className="gb-sel"
            x={glyphX(r.level) - 3}
            y={rowY(i) - 3}
            width={GLYPH + BAR_GAP + r.w + 7}
            height={GLYPH + 6}
            rx="2.5"
            style={{ "--d": r.level } as CSSProperties}
          />
        ) : null,
      )}

      {/* rows: folder/file glyph + blank name bar */}
      {ROWS.map((r, i) => {
        const gx = glyphX(r.level)
        const y = rowY(i)
        const onPath = sel.onPath.has(i)
        const isMatch = sel.matched.has(i)
        return (
          <g key={`r${i}`}>
            <rect
              className={cn("gb-glyph", isMatch && "is-match", onPath && "is-path")}
              style={onPath ? ({ "--d": r.level } as CSSProperties) : undefined}
              x={gx}
              y={y}
              width={GLYPH}
              height={GLYPH}
              rx="1.5"
            />
            <rect
              className={cn("gb-bar", isMatch && "is-match", onPath && "is-path")}
              style={onPath ? ({ "--d": r.level } as CSSProperties) : undefined}
              x={gx + GLYPH + BAR_GAP}
              y={y + (GLYPH - BAR_H) / 2}
              width={r.w}
              height={BAR_H}
              rx="2"
            />
          </g>
        )
      })}
    </Field>
  )
}
