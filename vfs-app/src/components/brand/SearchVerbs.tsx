import { memo, useEffect, useRef, useState, useSyncExternalStore } from "react"
import type { ReactNode } from "react"
import { cn } from "@/lib/utils"
import { GlobField } from "./GlobField"
import { GrepField } from "./GrepField"
import { GleanField } from "./GleanField"
import { GraphField } from "./GraphField"

// Memoize field children locally so a tick that flips two cards' `active`
// doesn't re-render the other two. Field files stay untouched.
const MemoGlobField = memo(GlobField)
const MemoGrepField = memo(GrepField)
const MemoGleanField = memo(GleanField)
const MemoGraphField = memo(GraphField)

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
  { verb: "glob", render: (a) => <MemoGlobField active={a} /> },
  { verb: "grep", render: (a) => <MemoGrepField active={a} /> },
  { verb: "glean", render: (a) => <MemoGleanField active={a} /> },
  { verb: "graph", render: (a) => <MemoGraphField active={a} /> },
]

// time each card holds the spotlight before the cycle advances — long enough
// for the slowest diagram (grep's scan) to play out and settle
const DWELL_MS = 2500

const REDUCE_QUERY = "(prefers-reduced-motion: reduce)"

// useSyncExternalStore source so the component re-subscribes to the OS
// setting and reacts live when it's toggled at runtime.
const subscribeReduce = (onChange: () => void) => {
  const mq = window.matchMedia(REDUCE_QUERY)
  mq.addEventListener("change", onChange)
  return () => mq.removeEventListener("change", onChange)
}
const readReduce = () => window.matchMedia(REDUCE_QUERY).matches

export function SearchVerbs() {
  // under reduced motion: no auto-cycle, nothing lit until hover
  const reduce = useSyncExternalStore(subscribeReduce, readReduce, () => false)
  const [active, setActive] = useState(0)
  const [paused, setPaused] = useState(false)
  const [visible, setVisible] = useState(true)
  const wrapRef = useRef<HTMLDivElement | null>(null)

  // Only auto-cycle while the section is on screen, so a scrolled-away or
  // backgrounded landing page goes idle.
  useEffect(() => {
    const el = wrapRef.current
    if (!el) return
    const io = new IntersectionObserver(
      ([entry]) => {
        if (entry) setVisible(entry.isIntersecting)
      },
      { threshold: 0 },
    )
    io.observe(el)
    return () => io.disconnect()
  }, [])

  useEffect(() => {
    if (paused || reduce || !visible) return
    const id = setInterval(
      () => setActive((i) => (i + 1) % VERBS.length),
      DWELL_MS,
    )
    return () => clearInterval(id)
  }, [paused, reduce, visible])

  // Derived, not stored: under reduced motion nothing is lit unless hovered,
  // so a runtime toggle takes effect without a set-state-in-effect sync.
  const shown = reduce && !paused ? -1 : active

  return (
    <div className="vfs-verbs-wrap" ref={wrapRef}>
      <div className="vfs-verbs">
        {VERBS.map((v, i) => (
          <div
            className={cn("vfs-verb", shown === i && "is-active")}
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
            <div className="vfs-verb-art">{v.render(shown === i)}</div>
          </div>
        ))}
      </div>
    </div>
  )
}
