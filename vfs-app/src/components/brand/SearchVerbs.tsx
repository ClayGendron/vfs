import { useEffect, useState } from "react"
import type { ReactNode } from "react"
import { cn } from "@/lib/utils"
import { GlobField } from "./GlobField"
import { GrepField } from "./GrepField"
import { GleanField } from "./GleanField"
import { GraphField } from "./GraphField"

/**
 * §2 visual — the four search verbs as four structural diagrams.
 *
 * Each verb maps to a dimension a file carries information along. The cards
 * auto-play one after another, each colouring itself in with the cobalt accent
 * — the one signal colour shared across all four. Hovering a card pins it (and
 * pauses the cycle); on leave the cycle resumes from that card.
 */

type Verb = {
  verb: string
  render: (active: boolean) => ReactNode
}

const VERBS: Verb[] = [
  { verb: "glob", render: (a) => <GlobField active={a} /> },
  { verb: "grep", render: (a) => <GrepField active={a} /> },
  { verb: "glean", render: (a) => <GleanField active={a} /> },
  { verb: "graph", render: (a) => <GraphField active={a} /> },
]

// time each card holds the spotlight before the cycle advances — long enough
// for the slowest diagram (grep's scan) to play out and settle
const DWELL_MS = 2500

const prefersReduce = () =>
  typeof window !== "undefined" &&
  window.matchMedia("(prefers-reduced-motion: reduce)").matches

export function SearchVerbs() {
  // under reduced motion: no auto-cycle, nothing lit until hover
  const [reduce] = useState(prefersReduce)
  const [active, setActive] = useState(reduce ? -1 : 0)
  const [paused, setPaused] = useState(false)

  useEffect(() => {
    if (paused || reduce) return
    const id = setInterval(
      () => setActive((i) => (i + 1) % VERBS.length),
      DWELL_MS,
    )
    return () => clearInterval(id)
  }, [paused, reduce])

  return (
    <div className="vfs-verbs-wrap">
      <div className="vfs-verbs">
        {VERBS.map((v, i) => (
          <div
            className={cn("vfs-verb", active === i && "is-active")}
            key={v.verb}
            onMouseEnter={() => {
              setActive(i)
              setPaused(true)
            }}
            onMouseLeave={() => {
              setPaused(false)
              if (reduce) setActive(-1)
            }}
          >
            <span className="vfs-verb-name">{v.verb}</span>
            <div className="vfs-verb-art">{v.render(active === i)}</div>
          </div>
        ))}
      </div>
    </div>
  )
}
