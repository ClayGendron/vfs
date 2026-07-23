import { memo, useEffect, useRef, useState, useSyncExternalStore } from "react"
import { cn } from "@/lib/utils"
import { SEARCH_VERBS } from "@/lib/site"
import { GlobField } from "./GlobField"
import { GrepField } from "./GrepField"
import { GleanField } from "./GleanField"
import { GraphField } from "./GraphField"

/**
 * The four search verbs as one ruled strip — a cell per dimension a file
 * carries information along, with the composed pipeline along the foot.
 *
 * Cells light in turn, each playing its own diagram. Hovering a cell pins it
 * and pauses the cycle; on leave the cycle resumes from there. Under reduced
 * motion nothing auto-plays and nothing is lit until hover.
 */

// memoized so a tick that flips two cells doesn't re-render the other two
const ART = [memo(GlobField), memo(GrepField), memo(GleanField), memo(GraphField)]

// time a cell holds the spotlight — long enough for the slowest diagram to
// play out and settle
const DWELL_MS = 2800

const REDUCE_QUERY = "(prefers-reduced-motion: reduce)"

const subscribeReduce = (onChange: () => void) => {
  const mq = window.matchMedia(REDUCE_QUERY)
  mq.addEventListener("change", onChange)
  return () => mq.removeEventListener("change", onChange)
}
const readReduce = () => window.matchMedia(REDUCE_QUERY).matches

export function VerbStrip() {
  const reduce = useSyncExternalStore(subscribeReduce, readReduce, () => false)
  const [active, setActive] = useState(0)
  const [paused, setPaused] = useState(false)
  const [visible, setVisible] = useState(true)
  const wrapRef = useRef<HTMLDivElement | null>(null)

  // only cycle while on screen, so a scrolled-away page goes idle
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
      () => setActive((i) => (i + 1) % SEARCH_VERBS.length),
      DWELL_MS,
    )
    return () => clearInterval(id)
  }, [paused, reduce, visible])

  // derived, not stored: under reduced motion nothing is lit unless hovered
  const shown = reduce && !paused ? -1 : active

  return (
    <div className="vfs-verbstrip" id="four-verbs" ref={wrapRef}>
      {SEARCH_VERBS.map((v, i) => {
        const Art = ART[i]
        return (
          <div
            key={v.name}
            className={cn("vfs-verb", shown === i && "is-active")}
            onMouseEnter={() => {
              setActive(i)
              setPaused(true)
            }}
            onMouseLeave={() => {
              setPaused(false)
              if (reduce) setActive(-1)
            }}
          >
            <span className="vfs-verb-name">{v.name}</span>
            <span className="vfs-verb-dim">{v.dim}</span>
            <div className="vfs-verb-art">{Art && <Art active={shown === i} />}</div>
          </div>
        )
      })}
      <div className="vfs-verbstrip-foot">
        <span className="p">vfs $</span>
        <span>grep &quot;authenticate&quot; | nbr | pagerank | top 15</span>
      </div>
    </div>
  )
}
