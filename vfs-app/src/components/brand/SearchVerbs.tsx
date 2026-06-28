import { useState } from "react"
import type { ReactNode } from "react"
import { cn } from "@/lib/utils"
import { GlobField } from "./GlobField"
import { GrepField } from "./GrepField"
import { GleanField } from "./GleanField"
import { GraphField } from "./GraphField"

/**
 * §2 visual — the four search verbs as four structural diagrams.
 *
 * Each verb maps to a dimension a file carries information along. The diagrams
 * rest fully neutral; hovering a card runs that verb's motion and colours it in
 * with the cobalt accent — the one signal colour shared across all four.
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

export function SearchVerbs() {
  const [hover, setHover] = useState<number | null>(null)

  return (
    <div className="vfs-verbs-wrap">
      <div className="vfs-verbs">
        {VERBS.map((v, i) => (
          <div
            className={cn("vfs-verb", hover === i && "is-active")}
            key={v.verb}
            onMouseEnter={() => setHover(i)}
            onMouseLeave={() => setHover((h) => (h === i ? null : h))}
          >
            <span className="vfs-verb-name">{v.verb}</span>
            <div className="vfs-verb-art">{v.render(hover === i)}</div>
          </div>
        ))}
      </div>
    </div>
  )
}
