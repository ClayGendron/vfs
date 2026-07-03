import { useEffect, useState } from "react"
import type { CSSProperties } from "react"
import { cn } from "@/lib/utils"
import { pickDistinct, randInt } from "@/lib/pickDistinct"
import { Field } from "./Field"

/**
 * grep · content — literal matches in text.
 *
 * Rows of blank "words" rest neutral. On each play 1–5 of them are chosen at
 * random as matches; a scan line sweeps top-to-bottom and each match lights
 * cobalt as the line reaches it — the feel of a regex pass landing on hits.
 */

const ROW_WIDTHS: number[][] = [
  [26, 34, 18],
  [16, 22, 40, 14],
  [30, 20, 28],
  [18, 24, 16, 30],
  [36, 18, 22],
  [20, 28, 16, 24],
]

const X0 = 16
const GAP = 7
const Y0 = 20
const ROW_H = 22
const WORD_H = 7

type Word = { x: number; y: number; w: number }

// flatten the row widths into positioned word rects once
const WORDS: Word[] = (() => {
  const out: Word[] = []
  ROW_WIDTHS.forEach((row, r) => {
    let x = X0
    const y = Y0 + r * ROW_H
    for (const w of row) {
      out.push({ x, y, w })
      x += w + GAP
    }
  })
  return out
})()

// pick 1–5 words at random, ordered top-to-bottom so the stagger tracks the scan
function pickMatches(): number[] {
  return pickDistinct(randInt(1, 5), WORDS.length).sort(
    (a, b) => WORDS[a]!.y - WORDS[b]!.y || WORDS[a]!.x - WORDS[b]!.x,
  )
}

export function GrepField({ active }: { active: boolean }) {
  const [matches, setMatches] = useState<number[]>([])

  // fresh matches on each play; clears back to neutral when the spotlight leaves.
  // deferred a frame so the re-roll lands outside render, not synchronously.
  useEffect(() => {
    const id = requestAnimationFrame(() => setMatches(active ? pickMatches() : []))
    return () => cancelAnimationFrame(id)
  }, [active])

  // word index → flare order, for the staggered reveal
  const rank = new Map(matches.map((wi, r) => [wi, r]))

  return (
    <Field code="gp" viewBox="0 0 260 150" active={active}>
      {WORDS.map((word, i) => {
        const order = rank.get(i)
        const isMatch = order !== undefined
        return (
          <rect
            key={i}
            className={cn("gp-word", isMatch && "is-match")}
            x={word.x}
            y={word.y}
            width={word.w}
            height={WORD_H}
            rx="2"
            style={isMatch ? ({ "--d": order } as CSSProperties) : undefined}
          />
        )
      })}
      <rect className="gp-scan" x="12" y="14" width="120" height="2" rx="1" />
    </Field>
  )
}
