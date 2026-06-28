import { useEffect, useMemo, useRef, useState } from "react"
import type { CSSProperties } from "react"
import { cn } from "@/lib/utils"

/**
 * glean · meaning — a vector space.
 *
 * A scattered point cloud sits fully uniform at rest — no query, no links. On
 * hover a query point is chosen at random, grows, and draws links to its five
 * nearest neighbors in colour — the gesture of a semantic lookup landing
 * somewhere in the embedding space.
 */

type Pt = { x: number; y: number }

const W = 260
const H = 150
const PAD = 16
const N = 36
const K = 5

function makePoints(): Pt[] {
  const pts: Pt[] = []
  let guard = 0
  while (pts.length < N && guard++ < 4000) {
    const x = PAD + Math.random() * (W - 2 * PAD)
    const y = PAD + Math.random() * (H - 2 * PAD)
    // reject points that crowd an existing one — keeps the cloud legible
    if (pts.every((p) => (p.x - x) ** 2 + (p.y - y) ** 2 > 150)) {
      pts.push({ x, y })
    }
  }
  return pts
}

function nearest(pts: Pt[], qi: number, k: number): number[] {
  return pts
    .map((p, i) => ({ i, d: (p.x - pts[qi].x) ** 2 + (p.y - pts[qi].y) ** 2 }))
    .filter((o) => o.i !== qi)
    .sort((a, b) => a.d - b.d)
    .slice(0, k)
    .map((o) => o.i)
}

export function GleanField({ active }: { active: boolean }) {
  const ptsRef = useRef<Pt[] | null>(null)
  if (ptsRef.current === null) ptsRef.current = makePoints()
  const pts = ptsRef.current

  // initial query is random; each hover relocates it to a new random point and
  // it stays put when the pointer leaves — no snap back to a default.
  const [qi, setQi] = useState(() => Math.floor(Math.random() * pts.length))

  useEffect(() => {
    if (!active) return
    setQi((cur) => {
      let n = cur
      for (let t = 0; t < 10 && n === cur; t++) {
        n = Math.floor(Math.random() * pts.length)
      }
      return n
    })
  }, [active, pts])

  const nn = useMemo(() => nearest(pts, qi, K), [pts, qi])
  const nnSet = useMemo(() => new Set(nn), [nn])
  const q = pts[qi]

  return (
    <svg
      viewBox={`0 0 ${W} ${H}`}
      className="vfs-field gf"
      preserveAspectRatio="xMidYMid meet"
      aria-hidden="true"
    >
      {/* neighbour links — keyed by query so they remount + redraw on change */}
      <g key={qi} className={cn("gf-links", active && "is-on")}>
        {nn.map((j, idx) => (
          <line
            key={j}
            className="gf-link"
            x1={q.x}
            y1={q.y}
            x2={pts[j].x}
            y2={pts[j].y}
            pathLength="1"
            style={{ "--d": idx } as CSSProperties}
          />
        ))}
      </g>

      {/* cloud */}
      {pts.map((p, i) =>
        i === qi ? null : (
          <circle
            key={i}
            cx={p.x}
            cy={p.y}
            r={active && nnSet.has(i) ? 3.8 : 2.9}
            className={cn("gf-pt", nnSet.has(i) && "is-nn", active && "is-on")}
          />
        ),
      )}

      {/* query node on top — a plain point until hover picks it out */}
      <circle cx={q.x} cy={q.y} r={active ? 7.5 : 2.9} className={cn("gf-q", active && "is-on")} />
    </svg>
  )
}
