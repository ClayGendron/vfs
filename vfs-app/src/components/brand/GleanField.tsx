import { useEffect, useMemo, useState } from "react"
import type { CSSProperties } from "react"
import { cn } from "@/lib/utils"
import { Field } from "./Field"

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

// Seeded so the resting cloud is identical on the server and first client
// render — a random-per-load layout would mismatch on hydration.
function mulberry32(seed: number): () => number {
  return () => {
    seed = (seed + 0x6d2b79f5) | 0
    let t = Math.imul(seed ^ (seed >>> 15), 1 | seed)
    t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296
  }
}

function makePoints(): Pt[] {
  const rand = mulberry32(0x9e3779b9)
  const pts: Pt[] = []
  let guard = 0
  while (pts.length < N && guard++ < 4000) {
    const x = PAD + rand() * (W - 2 * PAD)
    const y = PAD + rand() * (H - 2 * PAD)
    // reject points that crowd an existing one — keeps the cloud legible
    if (pts.every((p) => (p.x - x) ** 2 + (p.y - y) ** 2 > 150)) {
      pts.push({ x, y })
    }
  }
  return pts
}

function nearest(pts: Pt[], qi: number, k: number): number[] {
  const q = pts[qi]
  if (!q) return []
  return pts
    .map((p, i) => ({ i, d: (p.x - q.x) ** 2 + (p.y - q.y) ** 2 }))
    .filter((o) => o.i !== qi)
    .sort((a, b) => a.d - b.d)
    .slice(0, k)
    .map((o) => o.i)
}

export function GleanField({ active }: { active: boolean }) {
  const [pts] = useState(makePoints)

  // Deterministic at rest (hydration-safe); the first activation re-rolls it to
  // a random point and it stays put when the pointer leaves — no snap to default.
  const [qi, setQi] = useState(0)

  // deferred a frame so the re-roll lands outside render, not synchronously
  useEffect(() => {
    if (!active) return
    const id = requestAnimationFrame(() => {
      setQi((cur) => {
        let n = cur
        for (let t = 0; t < 10 && n === cur; t++) {
          n = Math.floor(Math.random() * pts.length)
        }
        return n
      })
    })
    return () => cancelAnimationFrame(id)
  }, [active, pts])

  const nn = useMemo(() => nearest(pts, qi, K), [pts, qi])
  const nnSet = useMemo(() => new Set(nn), [nn])
  const q = pts[qi]
  if (!q) return null

  return (
    <Field code="gf" viewBox={`0 0 ${W} ${H}`}>
      {/* neighbour links — keyed by query so they remount + redraw on change */}
      <g key={qi} className={cn("gf-links", active && "is-on")}>
        {nn.map((j, idx) => {
          const t = pts[j]
          if (!t) return null
          return (
            <line
              key={j}
              className="gf-link"
              x1={q.x}
              y1={q.y}
              x2={t.x}
              y2={t.y}
              pathLength="1"
              style={{ "--d": idx } as CSSProperties}
            />
          )
        })}
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
    </Field>
  )
}
