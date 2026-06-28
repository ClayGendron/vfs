import { useEffect, useMemo, useState } from "react"
import { cn } from "@/lib/utils"

/**
 * graph · connection — a four-community knowledge graph.
 *
 * The layout was computed once by d3-force (candidate F: four clusters, 48
 * nodes, ring-bridged) and frozen here, so the network is stable and renders
 * as crisp SVG with no runtime graph library. Delicate styling — tiny nodes,
 * hairline curved edges, no arrowheads. The card rests static; on hover three
 * nodes from three different clusters are chosen and a min-meeting-subgraph
 * traversal lights the shortest paths converging on the node that connects
 * them, routing across the bridges between communities.
 */

const VB_W = 413.1
const VB_H = 215.4
// breathing room so edge nodes (and the curves that bow past them) aren't clipped
const VB_PAD = 14

// frozen d3-force positions
const NODES: ReadonlyArray<{ x: number; y: number }> = [
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
const GROUPS: ReadonlyArray<readonly [number, number]> = [[0, 11], [12, 23], [24, 35], [36, 47]]

const N = NODES.length
const STEP_MS = 140
const ekey = (a: number, b: number) => (a < b ? `${a}-${b}` : `${b}-${a}`)

const ADJ: number[][] = NODES.map(() => [])
for (const [a, b] of EDGES) {
  ADJ[a].push(b)
  ADJ[b].push(a)
}

// pre-rendered curved edge paths (positions are frozen, so compute once)
const EDGE_PATHS = EDGES.map(([a, b]) => {
  const s = NODES[a]
  const t = NODES[b]
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

type Solved = {
  sources: number[]
  meeting: number
  edgeDepth: Map<string, number>
  nodeDepth: Map<number, number>
  maxDepth: number
}

function bfs(src: number) {
  const dist = Array<number>(N).fill(Infinity)
  const parent = Array<number>(N).fill(-1)
  dist[src] = 0
  const queue = [src]
  for (let h = 0; h < queue.length; h++) {
    const u = queue[h]
    for (const v of ADJ[u]) {
      if (dist[v] === Infinity) {
        dist[v] = dist[u] + 1
        parent[v] = u
        queue.push(v)
      }
    }
  }
  return { dist, parent }
}

function solve(sources: number[]): Solved {
  const bs = sources.map(bfs)
  let meeting = sources[0]
  let best = Infinity
  for (let n = 0; n < N; n++) {
    if (bs.some((b) => b.dist[n] === Infinity)) continue
    const sum = bs.reduce((acc, b) => acc + b.dist[n], 0)
    const penalty = sources.includes(n) ? 2 : 0
    if (sum + penalty < best) {
      best = sum + penalty
      meeting = n
    }
  }
  const edgeDepth = new Map<string, number>()
  const nodeDepth = new Map<number, number>()
  let maxDepth = 0
  sources.forEach((s, si) => {
    nodeDepth.set(s, 0)
    const { parent, dist } = bs[si]
    let cur = meeting
    while (cur !== s && parent[cur] !== -1) {
      const p = parent[cur]
      edgeDepth.set(ekey(p, cur), Math.min(dist[cur], edgeDepth.get(ekey(p, cur)) ?? Infinity))
      nodeDepth.set(cur, Math.min(dist[cur], nodeDepth.get(cur) ?? Infinity))
      maxDepth = Math.max(maxDepth, dist[cur])
      cur = p
    }
  })
  nodeDepth.set(meeting, nodeDepth.get(meeting) ?? maxDepth)
  return { sources, meeting, edgeDepth, nodeDepth, maxDepth }
}

// pick one node from each of three distinct clusters, so the traversal spans
// communities and has to route through the bridges between them
function pick3(): number[] {
  const groups = [0, 1, 2, 3]
  const chosen: number[] = []
  while (chosen.length < 3) {
    const g = groups[Math.floor(Math.random() * groups.length)]
    if (!chosen.includes(g)) chosen.push(g)
  }
  return chosen.map((g) => {
    const [lo, hi] = GROUPS[g]
    return lo + Math.floor(Math.random() * (hi - lo + 1))
  })
}

export function GraphField({ active }: { active: boolean }) {
  const [sel, setSel] = useState<Solved | null>(null)
  const [revealed, setRevealed] = useState(0)

  useEffect(() => {
    if (!active) {
      setSel(null)
      setRevealed(0)
      return
    }
    const next = solve(pick3())
    setSel(next)
    setRevealed(0)
    let step = 0
    const id = setInterval(() => {
      step += 1
      setRevealed(step)
      if (step >= next.maxDepth) clearInterval(id)
    }, STEP_MS)
    return () => clearInterval(id)
  }, [active])

  const sourceSet = useMemo(() => new Set(sel?.sources ?? []), [sel])

  return (
    <svg
      viewBox={`${-VB_PAD} ${-VB_PAD} ${VB_W + 2 * VB_PAD} ${VB_H + 2 * VB_PAD}`}
      className="vfs-field gr"
      preserveAspectRatio="xMidYMid meet"
      aria-hidden="true"
    >
      {EDGE_PATHS.map((e, i) => {
        const depth = sel?.edgeDepth.get(e.key)
        const lit = depth !== undefined && revealed >= depth
        return <path key={i} className={cn("gr-edge", lit && "is-lit")} d={e.d} />
      })}

      {NODES.map((n, i) => {
        const depth = sel?.nodeDepth.get(i)
        const lit = depth !== undefined && revealed >= depth
        const isSource = sourceSet.has(i)
        const isMeeting = i === sel?.meeting && lit
        return (
          <circle
            key={i}
            cx={n.x}
            cy={n.y}
            r={isMeeting ? 6.5 : isSource && active ? 5.2 : 3.4}
            className={cn(
              "gr-node",
              lit && "is-lit",
              isSource && active && "is-source",
              isMeeting && "is-meeting",
            )}
          />
        )
      })}
    </svg>
  )
}
