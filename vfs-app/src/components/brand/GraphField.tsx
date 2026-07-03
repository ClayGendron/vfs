import { useEffect, useMemo, useState } from "react"
import { cn } from "@/lib/utils"
import { pickDistinct, randInt } from "@/lib/pickDistinct"
import { Field } from "./Field"
import { ADJ, EDGE_PATHS, GROUPS, N, NODES, VB_H, VB_PAD, VB_W, ekey } from "./graphLayout"

/**
 * graph · connection — a four-community knowledge graph.
 *
 * Delicate styling — tiny nodes, hairline curved edges, no arrowheads. The
 * card rests static; on hover three nodes from three different clusters are
 * chosen and a min-meeting-subgraph traversal lights the shortest paths
 * converging on the node that connects them, routing across the bridges
 * between communities. The frozen layout and precompute live in graphLayout.
 */

const STEP_MS = 140

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
    const u = queue[h]!
    for (const v of ADJ[u] ?? []) {
      if (dist[v] === Infinity) {
        dist[v] = dist[u]! + 1
        parent[v] = u
        queue.push(v)
      }
    }
  }
  return { dist, parent }
}

function solve(sources: number[]): Solved {
  const bs = sources.map(bfs)
  let meeting = sources[0] ?? 0
  let best = Infinity
  for (let n = 0; n < N; n++) {
    if (bs.some((b) => (b.dist[n] ?? Infinity) === Infinity)) continue
    const sum = bs.reduce((acc, b) => acc + (b.dist[n] ?? Infinity), 0)
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

// pick one node from each of three distinct clusters, so the traversal spans
// communities and has to route through the bridges between them
function pick3(): number[] {
  return pickDistinct(3, GROUPS.length).map((g) => {
    const grp = GROUPS[g]
    if (!grp) return 0
    const [lo, hi] = grp
    return randInt(lo, hi)
  })
}

const REDUCE_QUERY = "(prefers-reduced-motion: reduce)"

export function GraphField({ active }: { active: boolean }) {
  const [sel, setSel] = useState<Solved | null>(null)
  const [revealed, setRevealed] = useState(0)
  const [reduced, setReduced] = useState(
    () => typeof window !== "undefined" && window.matchMedia(REDUCE_QUERY).matches,
  )

  // the reveal is a JS timer, so a CSS media query can't suppress it — track the
  // preference here and jump straight to the end state when it's set.
  useEffect(() => {
    const mq = window.matchMedia(REDUCE_QUERY)
    const onChange = () => setReduced(mq.matches)
    mq.addEventListener("change", onChange)
    return () => mq.removeEventListener("change", onChange)
  }, [])

  useEffect(() => {
    if (!active) {
      const clear = requestAnimationFrame(() => {
        setSel(null)
        setRevealed(0)
      })
      return () => cancelAnimationFrame(clear)
    }
    const next = solve(pick3())
    const raf = requestAnimationFrame(() => {
      setSel(next)
      setRevealed(reduced ? next.maxDepth : 0)
    })
    if (reduced) return () => cancelAnimationFrame(raf)
    let step = 0
    const id = setInterval(() => {
      step += 1
      setRevealed(step)
      if (step >= next.maxDepth) clearInterval(id)
    }, STEP_MS)
    return () => {
      cancelAnimationFrame(raf)
      clearInterval(id)
    }
  }, [active, reduced])

  const sourceSet = useMemo(() => new Set(sel?.sources ?? []), [sel])

  return (
    <Field code="gr" viewBox={`${-VB_PAD} ${-VB_PAD} ${VB_W + 2 * VB_PAD} ${VB_H + 2 * VB_PAD}`}>
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
            r={isSource && active ? 6.8 : 4.6}
            className={cn(
              "gr-node",
              lit && "is-lit",
              isSource && active && "is-source",
              isMeeting && "is-meeting",
            )}
          />
        )
      })}
    </Field>
  )
}
