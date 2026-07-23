import { useEffect, useState } from "react"
import type { CSSProperties } from "react"
import { cn } from "@/lib/utils"
import { Field } from "./Field"
import { mulberry32 } from "./seededCloud"

/**
 * glean · meaning regions — the space is clustered, retrieval pulls a region.
 *
 * Three loose clusters (plus a few strays) rest uniform. On each play the query
 * lands on any point in the space, its nearest neighbors light graded by
 * distance, and a hairline outline traces the hull of exactly those hits —
 * semantic recall returns a neighborhood of meaning, not scattered literal hits.
 */

const W = 260
const H = 150
const CLUSTER_N = 9

const CENTERS = [
  { x: 64, y: 46, rx: 34, ry: 24 },
  { x: 196, y: 50, rx: 32, ry: 22 },
  { x: 120, y: 112, rx: 38, ry: 22 },
] as const

// hand-placed strays between clusters, so the space reads as continuous
const STRAYS = [
  { x: 132, y: 34 },
  { x: 96, y: 80 },
  { x: 168, y: 86 },
  { x: 228, y: 116 },
  { x: 34, y: 102 },
] as const

type Pt = { x: number; y: number }

const PTS: Pt[] = (() => {
  const rand = mulberry32(0x3c6ef372)
  const pts: Pt[] = []
  CENTERS.forEach((ctr) => {
    let placed = 0
    let guard = 0
    while (placed < CLUSTER_N && guard++ < 2000) {
      // sum of two uniforms: triangular falloff, denser toward the center
      const x = ctr.x + (rand() + rand() - 1) * ctr.rx
      const y = ctr.y + (rand() + rand() - 1) * ctr.ry
      if (pts.every((p) => (p.x - x) ** 2 + (p.y - y) ** 2 > 80)) {
        pts.push({ x, y })
        placed++
      }
    }
  })
  for (const s of STRAYS) pts.push({ x: s.x, y: s.y })
  return pts
})()

// neighbors pulled back per play — enough to read as a region, short of
// swallowing the whole space
const RECALL_N = 9
// how far the traced outline sits outside the points it encloses
const HULL_PAD = 11
// how far each hull radius eases toward the mean — rounds out spikes
const RELAX = 0.35
// Catmull-Rom handle scale; ~1 passes smoothly through every hull point
const TENSION = 1

type Query = { seed: number; x: number; y: number; rank: Map<number, number>; hull: string }

// The query lands on any point in the space, stray or clustered, and recall
// runs over every point — so the lit region is whatever sits nearest in
// meaning, not whatever shares a cluster id.
function pickQuery(prev: number): Query {
  let seed = prev
  for (let t = 0; t < 10 && seed === prev; t++) seed = Math.floor(Math.random() * PTS.length)
  const at = PTS[seed]!
  const { x, y } = at

  const order = PTS.map((p, i) => ({ i, p }))
    .sort((a, b) => (a.p.x - x) ** 2 + (a.p.y - y) ** 2 - ((b.p.x - x) ** 2 + (b.p.y - y) ** 2))
    .slice(0, RECALL_N)

  return {
    seed,
    x,
    y,
    rank: new Map(order.map((o, r) => [o.i, r])),
    hull: regionPath(order.map((o) => o.p)),
  }
}

export function GleanField({ active }: { active?: boolean }) {
  const [q, setQ] = useState<Query | null>(null)

  // a different cluster on each play; clears to neutral when the spotlight
  // leaves. Deferred a frame so the re-roll lands outside render.
  useEffect(() => {
    const id = requestAnimationFrame(() =>
      setQ((cur) => (active ? pickQuery(cur?.seed ?? -1) : null)),
    )
    return () => cancelAnimationFrame(id)
  }, [active])

  return (
    <Field code="gl" viewBox={`0 0 ${W} ${H}`} active={active}>
      {q && <path className="gl-hull is-lit" d={q.hull} pathLength={1} />}

      {PTS.map((p, i) => {
        const r = q?.rank.get(i)
        const isHit = r !== undefined
        return (
          <circle
            key={i}
            cx={p.x}
            cy={p.y}
            r={isHit ? 3.6 : 2.9}
            className={cn("gl-pt", isHit && "is-hit")}
            style={isHit ? ({ "--d": r, "--mix": `${100 - r * 6}%` } as CSSProperties) : undefined}
          />
        )
      })}

      {q && (
        <g className="gl-q">
          <circle className="gl-q-halo" cx={q.x} cy={q.y} r={6} />
          <circle className="gl-q-dot" cx={q.x} cy={q.y} r={3.2} />
        </g>
      )}
    </Field>
  )
}

// ---------------------------------------------------------------------------
// Internal helpers
// ---------------------------------------------------------------------------

/** Andrew's monotone chain — counter-clockwise hull of the recalled points. */
function convexHull(pts: Pt[]): Pt[] {
  const sorted = [...pts].sort((a, b) => a.x - b.x || a.y - b.y)
  if (sorted.length < 3) return sorted

  const cross = (o: Pt, a: Pt, b: Pt) =>
    (a.x - o.x) * (b.y - o.y) - (a.y - o.y) * (b.x - o.x)

  const half = (seq: Pt[]) => {
    const out: Pt[] = []
    for (const p of seq) {
      while (out.length > 1 && cross(out[out.length - 2]!, out[out.length - 1]!, p) <= 0) {
        out.pop()
      }
      out.push(p)
    }
    out.pop()
    return out
  }

  return [...half(sorted), ...half([...sorted].reverse())]
}

/**
 * Closed path hugging the recalled points — the hull pushed outward from its
 * centroid, radii relaxed toward their mean, then run through a closed
 * Catmull-Rom spline so the region reads as a soft blob, not a polygon.
 */
function regionPath(pts: Pt[]): string {
  const hull = convexHull(pts)
  const cx = hull.reduce((a, p) => a + p.x, 0) / hull.length
  const cy = hull.reduce((a, p) => a + p.y, 0) / hull.length

  const polar = hull.map((p) => {
    const dx = p.x - cx
    const dy = p.y - cy
    return { a: Math.atan2(dy, dx), r: Math.hypot(dx, dy) + HULL_PAD }
  })

  // pull the spikiest radii back toward the mean so no one outlier point
  // stretches the boundary into a teardrop
  const meanR = polar.reduce((a, p) => a + p.r, 0) / polar.length
  const ring = polar.map(({ a, r }) => {
    const eased = r + (meanR - r) * RELAX
    return { x: cx + Math.cos(a) * eased, y: cy + Math.sin(a) * eased }
  })

  // degenerate recall (collinear points) — fall back to a circle
  if (ring.length < 3) {
    const r = meanR || HULL_PAD + 6
    return `M ${cx - r} ${cy} a ${r} ${r} 0 1 0 ${r * 2} 0 a ${r} ${r} 0 1 0 ${-r * 2} 0`
  }

  const n = ring.length
  const at = (i: number) => ring[((i % n) + n) % n]!
  const xy = (p: Pt) => `${p.x.toFixed(2)} ${p.y.toFixed(2)}`

  let d = `M ${xy(at(0))}`
  for (let i = 0; i < n; i++) {
    const p0 = at(i - 1)
    const p1 = at(i)
    const p2 = at(i + 1)
    const p3 = at(i + 2)
    const c1 = { x: p1.x + ((p2.x - p0.x) / 6) * TENSION, y: p1.y + ((p2.y - p0.y) / 6) * TENSION }
    const c2 = { x: p2.x - ((p3.x - p1.x) / 6) * TENSION, y: p2.y - ((p3.y - p1.y) / 6) * TENSION }
    d += ` C ${xy(c1)} ${xy(c2)} ${xy(p2)}`
  }
  return `${d} Z`
}
