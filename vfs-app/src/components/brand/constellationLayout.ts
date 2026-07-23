import { buildAdj, ekey } from "./meetingGraph"
import type { MeetingLayout } from "./meetingGraph"

/**
 * Frozen layout for the constellation graph variant.
 *
 * Four organically clumped communities of different sizes — a big cluster
 * lower-left, two mid clusters top and right, a small satellite lower-right —
 * with long curved bridges between them. Computed once by a seeded spring
 * pass and frozen, so degrees, adjacency, and curved edge paths derive here.
 */

export const CN_VB = "-4 -4 268 158"

const NODES: ReadonlyArray<{ x: number; y: number }> = [
  { x: 60, y: 100 }, { x: 73.4, y: 99.5 }, { x: 66.2, y: 76.2 }, { x: 46.6, y: 119.2 },
  { x: 58.1, y: 125.6 }, { x: 91.5, y: 76 }, { x: 37.5, y: 98.7 }, { x: 89, y: 110.7 },
  { x: 27.3, y: 117.1 }, { x: 95.2, y: 92.2 }, { x: 74.2, y: 121.2 }, { x: 54, y: 87.9 },
  { x: 22.5, y: 81.8 }, { x: 126, y: 34 }, { x: 152.5, y: 45.6 }, { x: 140.9, y: 36.4 },
  { x: 109.4, y: 36.5 }, { x: 126.3, y: 20.4 }, { x: 93.6, y: 43.9 }, { x: 109.3, y: 17.3 },
  { x: 125.9, y: 51.3 }, { x: 147.5, y: 14 }, { x: 99.6, y: 27.2 }, { x: 210, y: 66 },
  { x: 193, y: 70.5 }, { x: 194.7, y: 48.2 }, { x: 215.3, y: 79.5 }, { x: 227.6, y: 70.1 },
  { x: 235.1, y: 44 }, { x: 182, y: 63.5 }, { x: 194.2, y: 83.5 }, { x: 216.6, y: 51 },
  { x: 235, y: 86.1 }, { x: 231.4, y: 57.5 }, { x: 194, y: 130 }, { x: 179, y: 131.8 },
  { x: 210.8, y: 126.1 }, { x: 189.5, y: 117.7 }, { x: 204.5, y: 139.4 }, { x: 167.5, y: 125.3 },
]

const EDGES: ReadonlyArray<readonly [number, number]> = [
  [0, 1], [0, 6], [0, 7], [0, 8], [0, 9], [0, 10], [0, 12], [2, 11], [3, 4], [5, 9],
  [6, 11], [7, 10], [3, 8], [4, 10], [0, 11], [6, 12], [2, 7], [1, 11], [13, 14],
  [13, 15], [13, 17], [13, 18], [13, 19], [13, 20], [13, 22], [14, 15], [16, 22],
  [16, 18], [19, 22], [17, 21], [18, 22], [16, 19], [23, 24], [23, 26], [23, 30],
  [23, 31], [23, 32], [23, 33], [24, 29], [25, 29], [27, 33], [28, 33], [24, 30],
  [31, 33], [27, 32], [25, 26], [25, 30], [34, 35], [34, 37], [35, 39], [36, 38],
  [34, 38], [36, 37], [35, 38], [5, 18], [14, 29], [30, 37], [9, 39], [5, 29],
]

const GROUPS: ReadonlyArray<readonly [number, number]> = [[0, 12], [13, 22], [23, 33], [34, 39]]

export const CN_LAYOUT: MeetingLayout = {
  nodes: NODES,
  edges: EDGES,
  groups: GROUPS,
  adj: buildAdj(NODES.length, EDGES),
}

export const CN_DEG: number[] = CN_LAYOUT.adj.map((n) => n.length)

// degree-scaled radius: hubs read instantly, leaves stay delicate
export const cnRadius = (i: number) => Math.min(6, 1.9 + (CN_DEG[i] ?? 1) * 0.5)

// the clear community hubs — they carry a resting halo ring
export const CN_HUBS: ReadonlySet<number> = new Set(
  CN_DEG.flatMap((d, i) => (d >= 6 ? [i] : [])),
)

const commOf = (i: number) => GROUPS.findIndex(([lo, hi]) => i >= lo && i <= hi)

// bridges bow harder and rest fainter than intra-community edges
export const CN_EDGE_PATHS = EDGES.map(([a, b]) => {
  const s = NODES[a]!
  const t = NODES[b]!
  const bridge = commOf(a) !== commOf(b)
  const dx = t.x - s.x
  const dy = t.y - s.y
  const dr = Math.hypot(dx, dy) || 1
  const off = bridge ? Math.min(22, dr * 0.2) : Math.min(8, dr * 0.12)
  const cx = (s.x + t.x) / 2 + (-dy / dr) * off
  const cy = (s.y + t.y) / 2 + (dx / dr) * off
  return { key: ekey(a, b), bridge, d: `M${s.x},${s.y} Q${cx},${cy} ${t.x},${t.y}` }
})
