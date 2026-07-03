/**
 * Frozen layout and precompute for the graph field.
 *
 * The layout was computed once by d3-force (candidate F: four clusters, 48
 * nodes, ring-bridged) and frozen here, so the network is stable and renders
 * as crisp SVG with no runtime graph library. Positions never change, so the
 * adjacency list and curved edge paths are derived once at module scope.
 */

export const VB_W = 413.1
export const VB_H = 215.4
// breathing room so edge nodes (and the curves that bow past them) aren't clipped
export const VB_PAD = 14

// frozen d3-force positions
export const NODES: ReadonlyArray<{ x: number; y: number }> = [
  { x: 279.1, y: 184.7 }, { x: 253.9, y: 175 }, { x: 252.8, y: 111.8 }, { x: 300.5, y: 167.6 },
  { x: 206.7, y: 160.3 }, { x: 236.3, y: 163.9 }, { x: 223.8, y: 40.3 }, { x: 235.7, y: 187.4 },
  { x: 312.8, y: 212.8 }, { x: 252.6, y: 207.1 }, { x: 359.5, y: 215.4 }, { x: 297.5, y: 208.9 },
  { x: 329.5, y: 126.8 }, { x: 362.1, y: 96.3 }, { x: 340.1, y: 64.1 }, { x: 287.7, y: 53.9 },
  { x: 401.1, y: 119.5 }, { x: 343.6, y: 45.6 }, { x: 268.2, y: 137 }, { x: 360, y: 131.9 },
  { x: 413.1, y: 92.9 }, { x: 293, y: 122.1 }, { x: 376, y: 21 }, { x: 316.9, y: 82.6 },
  { x: 40.4, y: 155.2 }, { x: 36.1, y: 124.8 }, { x: 109.9, y: 130 }, { x: 44.3, y: 176.4 },
  { x: 0.2, y: 175.7 }, { x: 200.7, y: 86 }, { x: 88.8, y: 174.2 }, { x: 77.8, y: 141.2 },
  { x: 148.4, y: 162.5 }, { x: 0, y: 152.5 }, { x: 6.9, y: 201.8 }, { x: 197.3, y: 52.1 },
  { x: 75.9, y: 79.5 }, { x: 43.6, y: 50.6 }, { x: 42.9, y: 12.4 }, { x: 65.3, y: 30.5 },
  { x: 106.5, y: 57.9 }, { x: 96.2, y: 0 }, { x: 10.8, y: 24.4 }, { x: 15.1, y: 57.8 },
  { x: 133.5, y: 33.3 }, { x: 131.3, y: 116.2 }, { x: 64.2, y: 101.9 }, { x: 165, y: 4.7 },
]

const EDGES: ReadonlyArray<readonly [number, number]> = [
  [1, 0], [2, 0], [3, 1], [4, 1], [5, 0], [6, 2], [7, 4], [8, 0], [9, 8], [10, 8], [11, 3],
  [0, 9], [4, 5], [11, 0], [7, 3], [9, 4], [13, 12], [14, 13], [15, 14], [16, 13], [17, 13],
  [18, 12], [19, 16], [20, 13], [21, 13], [22, 17], [23, 15], [12, 23], [18, 21], [21, 19],
  [15, 17], [19, 12], [16, 20], [25, 24], [26, 24], [27, 25], [28, 24], [29, 26], [30, 24],
  [31, 26], [32, 27], [33, 24], [34, 27], [35, 29], [28, 33], [34, 28], [30, 31], [30, 32],
  [27, 28], [27, 33], [37, 36], [38, 37], [39, 36], [40, 36], [41, 38], [42, 39], [43, 42],
  [44, 40], [45, 36], [46, 45], [47, 41], [39, 41], [43, 38], [46, 43], [4, 18], [3, 12],
  [15, 29], [21, 32], [25, 36], [31, 46], [45, 4], [47, 6],
]

// four communities of 12 nodes
export const GROUPS: ReadonlyArray<readonly [number, number]> = [[0, 11], [12, 23], [24, 35], [36, 47]]

export const N = NODES.length
export const ekey = (a: number, b: number) => (a < b ? `${a}-${b}` : `${b}-${a}`)

export const ADJ: number[][] = NODES.map(() => [])
for (const [a, b] of EDGES) {
  ADJ[a]!.push(b)
  ADJ[b]!.push(a)
}

// pre-rendered curved edge paths (positions are frozen, so compute once)
export const EDGE_PATHS = EDGES.map(([a, b]) => {
  const s = NODES[a]!
  const t = NODES[b]!
  const dx = t.x - s.x
  const dy = t.y - s.y
  const dr = Math.hypot(dx, dy) || 1
  const mx = (s.x + t.x) / 2
  const my = (s.y + t.y) / 2
  const off = Math.min(13, dr * 0.15)
  const cx = mx + (-dy / dr) * off
  const cy = my + (dx / dr) * off
  return { key: ekey(a, b), d: `M${s.x},${s.y} Q${cx},${cy} ${t.x},${t.y}` }
})
