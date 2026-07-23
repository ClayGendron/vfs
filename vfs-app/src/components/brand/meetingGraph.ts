import { pickDistinct, randInt } from "@/lib/pickDistinct"

/**
 * Shared meeting-subgraph traversal for the mock graph field variants.
 *
 * The behavior mirrors the shipping graph field: pick one node from each of
 * three distinct communities, then light the shortest paths converging on the
 * node that best connects them. What varies across the variants is the layout
 * and its rendering; the traversal solve here stays identical.
 */

export type MeetingLayout = {
  nodes: ReadonlyArray<{ x: number; y: number }>
  edges: ReadonlyArray<readonly [number, number]>
  groups: ReadonlyArray<readonly [number, number]>
  adj: ReadonlyArray<ReadonlyArray<number>>
}

export type Meeting = {
  sources: number[]
  meeting: number
  edgeDepth: Map<string, number>
  nodeDepth: Map<number, number>
  maxDepth: number
}

export const ekey = (a: number, b: number) => (a < b ? `${a}-${b}` : `${b}-${a}`)

export function buildAdj(n: number, edges: ReadonlyArray<readonly [number, number]>): number[][] {
  const adj: number[][] = Array.from({ length: n }, () => [])
  for (const [a, b] of edges) {
    adj[a]!.push(b)
    adj[b]!.push(a)
  }
  return adj
}

// one node from each of three distinct communities, so the traversal spans
// the graph and has to route through the bridges between them
export function pickSources(layout: MeetingLayout): number[] {
  return pickDistinct(3, layout.groups.length).map((g) => {
    const grp = layout.groups[g]
    if (!grp) return 0
    const [lo, hi] = grp
    return randInt(lo, hi)
  })
}

export function solveMeeting(layout: MeetingLayout, sources: number[]): Meeting {
  const n = layout.nodes.length
  const bs = sources.map((s) => bfs(layout, s))
  let meeting = sources[0] ?? 0
  let best = Infinity
  for (let v = 0; v < n; v++) {
    if (bs.some((b) => (b.dist[v] ?? Infinity) === Infinity)) continue
    const sum = bs.reduce((acc, b) => acc + (b.dist[v] ?? Infinity), 0)
    const penalty = sources.includes(v) ? 2 : 0
    if (sum + penalty < best) {
      best = sum + penalty
      meeting = v
    }
  }
  const edgeDepth = new Map<string, number>()
  const nodeDepth = new Map<number, number>()
  let maxDepth = 0
  sources.forEach((s, si) => {
    nodeDepth.set(s, 0)
    const b = bs[si]
    if (!b) return
    const { parent, dist } = b
    let cur = meeting
    while (cur !== s) {
      const p = parent[cur]
      const dc = dist[cur]
      if (p === undefined || p === -1 || dc === undefined) break
      edgeDepth.set(ekey(p, cur), Math.min(dc, edgeDepth.get(ekey(p, cur)) ?? Infinity))
      nodeDepth.set(cur, Math.min(dc, nodeDepth.get(cur) ?? Infinity))
      maxDepth = Math.max(maxDepth, dc)
      cur = p
    }
  })
  nodeDepth.set(meeting, nodeDepth.get(meeting) ?? maxDepth)
  return { sources, meeting, edgeDepth, nodeDepth, maxDepth }
}

// ---------------------------------------------------------------------------
// Internal helpers
// ---------------------------------------------------------------------------

function bfs(layout: MeetingLayout, src: number): { dist: number[]; parent: number[] } {
  const n = layout.nodes.length
  const dist = Array<number>(n).fill(Infinity)
  const parent = Array<number>(n).fill(-1)
  dist[src] = 0
  const queue = [src]
  for (let h = 0; h < queue.length; h++) {
    const u = queue[h]!
    for (const v of layout.adj[u] ?? []) {
      if (dist[v] === Infinity) {
        dist[v] = dist[u]! + 1
        parent[v] = u
        queue.push(v)
      }
    }
  }
  return { dist, parent }
}
