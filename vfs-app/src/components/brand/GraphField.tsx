import { cn } from "@/lib/utils"
import { Field } from "./Field"
import { useMeetingReveal } from "./useMeetingReveal"
import { CN_EDGE_PATHS, CN_LAYOUT, CN_VB } from "./constellationLayout"

/**
 * graph · constellation — organic clumped communities of uniform nodes.
 *
 * Four force-directed clumps of different sizes rest as a quiet substrate:
 * every node the same plain dot, so structure comes from where they sit and
 * what they connect to, with faint hard-bowed bridges between clumps. On each
 * play the shared meeting traversal lights three sources from three
 * communities and converges on the node that connects them, ringed on arrival.
 */

const NODE_R = 2.7

export function GraphField({ active }: { active?: boolean }) {
  const { sel, revealed, sourceSet } = useMeetingReveal(CN_LAYOUT, active)

  const meetingLit = sel !== null && revealed >= (sel.nodeDepth.get(sel.meeting) ?? 0)
  const mNode = sel ? CN_LAYOUT.nodes[sel.meeting] : undefined

  return (
    <Field code="gr" viewBox={CN_VB} active={active}>
      {CN_EDGE_PATHS.map((e) => {
        const depth = sel?.edgeDepth.get(e.key)
        const lit = depth !== undefined && revealed >= depth
        return (
          <path
            key={e.key}
            className={cn("gr-edge", e.bridge && "is-bridge", lit && "is-lit")}
            d={e.d}
          />
        )
      })}

      {mNode && (
        <circle
          className={cn("gr-mring", meetingLit && "is-lit")}
          cx={mNode.x}
          cy={mNode.y}
          r={10}
        />
      )}

      {CN_LAYOUT.nodes.map((n, i) => {
        const depth = sel?.nodeDepth.get(i)
        const lit = depth !== undefined && revealed >= depth
        const isSource = sourceSet.has(i) && active
        return (
          <circle
            key={i}
            className={cn(
              "gr-node",
              lit && "is-lit",
              isSource && "is-source",
              i === sel?.meeting && lit && "is-meeting",
            )}
            cx={n.x}
            cy={n.y}
            r={isSource ? NODE_R + 2 : NODE_R}
          />
        )
      })}
    </Field>
  )
}
