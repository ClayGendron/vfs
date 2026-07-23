/**
 * Seeded point-cloud helpers for the mock glean field variants.
 *
 * Resting layouts must be identical on the server and first client render,
 * so all at-rest randomness comes from a fixed-seed PRNG; only the query
 * chosen on activation uses Math.random.
 */

export type CloudPt = { x: number; y: number }

// Deterministic PRNG so resting layouts are hydration-safe.
export function mulberry32(seed: number): () => number {
  return () => {
    seed = (seed + 0x6d2b79f5) | 0
    let t = Math.imul(seed ^ (seed >>> 15), 1 | seed)
    t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296
  }
}

// Uniform scatter with min-distance rejection, so the cloud stays legible.
export function uniformCloud(
  seed: number,
  n: number,
  w: number,
  h: number,
  pad: number,
  minD2 = 150,
): CloudPt[] {
  const rand = mulberry32(seed)
  const pts: CloudPt[] = []
  let guard = 0
  while (pts.length < n && guard++ < 4000) {
    const x = pad + rand() * (w - 2 * pad)
    const y = pad + rand() * (h - 2 * pad)
    if (pts.every((p) => (p.x - x) ** 2 + (p.y - y) ** 2 > minD2)) pts.push({ x, y })
  }
  return pts
}

// Indices of the k points nearest to q, nearest first.
export function nearestTo(pts: readonly CloudPt[], q: CloudPt, k: number, exclude = -1): number[] {
  return pts
    .map((p, i) => ({ i, d: (p.x - q.x) ** 2 + (p.y - q.y) ** 2 }))
    .filter((o) => o.i !== exclude)
    .sort((a, b) => a.d - b.d)
    .slice(0, k)
    .map((o) => o.i)
}
