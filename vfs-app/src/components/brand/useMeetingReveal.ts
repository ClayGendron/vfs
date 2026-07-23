import { useEffect, useMemo, useState } from "react"
import { pickSources, solveMeeting } from "./meetingGraph"
import type { Meeting, MeetingLayout } from "./meetingGraph"

/**
 * Reveal driver shared by the mock graph variants — the same step feel as the
 * shipping graph field: solve fresh sources on activation, reveal one BFS
 * depth per tick, clear back to neutral on rest, and jump straight to the lit
 * end state when reduced motion is preferred.
 */

// one BFS depth per tick — paced to the 0.2s lit transitions in the CSS so a
// hop finishes colouring before the next one starts
const STEP_MS = 200
const REDUCE_QUERY = "(prefers-reduced-motion: reduce)"

export function useMeetingReveal(
  layout: MeetingLayout,
  active?: boolean,
): { sel: Meeting | null; revealed: number; sourceSet: Set<number> } {
  const [sel, setSel] = useState<Meeting | null>(null)
  const [revealed, setRevealed] = useState(0)
  const [reduced, setReduced] = useState(
    () => typeof window !== "undefined" && window.matchMedia(REDUCE_QUERY).matches,
  )

  // the reveal is a JS timer, so a CSS media query can't suppress it — track
  // the preference here and jump straight to the end state when it's set.
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
    const next = solveMeeting(layout, pickSources(layout))
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
  }, [active, reduced, layout])

  const sourceSet = useMemo(() => new Set(sel?.sources ?? []), [sel])
  return { sel, revealed, sourceSet }
}
