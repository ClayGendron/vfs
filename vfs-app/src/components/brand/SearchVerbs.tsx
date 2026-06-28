import { useState } from "react"
import type { CSSProperties, ReactNode } from "react"
import { cn } from "@/lib/utils"
import { GlobField } from "./GlobField"
import { GrepField } from "./GrepField"
import { GleanField } from "./GleanField"
import { GraphField } from "./GraphField"

/**
 * §2 visual — the four search verbs as four structural diagrams.
 *
 * Each verb maps to a dimension a file carries information along. The diagrams
 * rest static; hovering a card runs that verb's motion (and lights the
 * matching token in the compose pipeline below). One signal stroke per verb is
 * the section's single moment of pillar color.
 */

type Verb = {
  verb: string
  dim: string
  gloss: string
  color: string
  render: (active: boolean) => ReactNode
}

const VERBS: Verb[] = [
  {
    verb: "glob",
    dim: "location",
    gloss: "where it sits in the namespace",
    color: "var(--sig-cyan)",
    render: (a) => <GlobField active={a} />,
  },
  {
    verb: "grep",
    dim: "content",
    gloss: "literal strings and regular expressions",
    color: "var(--accent)",
    render: (a) => <GrepField active={a} />,
  },
  {
    verb: "glean",
    dim: "meaning",
    gloss: "semantic and lexical relevance",
    color: "var(--sig-violet)",
    render: (a) => <GleanField active={a} />,
  },
  {
    verb: "graph",
    dim: "connection",
    gloss: "traversal and centrality across edges",
    color: "var(--sig-ember)",
    render: (a) => <GraphField active={a} />,
  },
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
            style={{ "--verb": v.color } as CSSProperties}
            onMouseEnter={() => setHover(i)}
            onMouseLeave={() => setHover((h) => (h === i ? null : h))}
          >
            <span className="vfs-verb-dim">{v.dim}</span>
            <span className="vfs-verb-name">{v.verb}</span>
            <div className="vfs-verb-art">{v.render(hover === i)}</div>
            <span className="vfs-verb-gloss">{v.gloss}</span>
          </div>
        ))}
      </div>
      <div className="vfs-verbs-compose" aria-label="Verbs compose into one pipeline">
        <span className="vfs-verbs-prompt">$ </span>
        <span className={cn("vfs-verbs-cmd", hover !== null && VERBS[hover].verb === "glob" && "is-lit")}>glob</span>
        <span className="vfs-verbs-str"> "/**"</span>
        <span className="vfs-verbs-pipe"> | </span>
        <span className={cn("vfs-verbs-cmd", hover !== null && VERBS[hover].verb === "grep" && "is-lit")}>grep</span>
        <span className="vfs-verbs-str"> "auth"</span>
        <span className="vfs-verbs-pipe"> | </span>
        <span className={cn("vfs-verbs-cmd", hover !== null && VERBS[hover].verb === "glean" && "is-lit")}>glean</span>
        <span className="vfs-verbs-pipe"> | </span>
        <span className={cn("vfs-verbs-cmd", hover !== null && VERBS[hover].verb === "graph" && "is-lit")}>graph</span>
        <span className="vfs-verbs-pipe"> | </span>
        <span className="vfs-verbs-cmd">top</span>
        <span className="vfs-verbs-arg"> 15</span>
      </div>
    </div>
  )
}
