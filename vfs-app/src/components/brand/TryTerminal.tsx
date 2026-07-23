import { useEffect, useRef, useState } from "react"
import type { FormEvent } from "react"
import { cn } from "@/lib/utils"
import { TERM_BANNER, TERM_COMMANDS } from "@/lib/site"
import type { TermLine } from "@/lib/site"

/**
 * Mac-window terminal on the landing page — the four verbs, driveable.
 *
 * Runs against the canned transcript in `site` — a command either matches
 * a known entry and replays its output, or falls through to a friendly miss.
 * The real repl swaps in behind the same shell.
 */

type Block = { id: number; cmd: string; out: TermLine[] }

const MISS: TermLine[] = [
  { kind: "dim", text: "not wired up yet — try one of the commands below." },
]

export function TryTerminal({
  title = "agent@vfs — ~/enterprise",
  className,
  rows = 14,
}: {
  title?: string
  className?: string
  /** Height of the scroll body, in terminal rows. */
  rows?: number
}) {
  const [blocks, setBlocks] = useState<Block[]>([])
  const [value, setValue] = useState("")
  const nextId = useRef(0)
  const bodyRef = useRef<HTMLDivElement | null>(null)

  useEffect(() => {
    const el = bodyRef.current
    if (el) el.scrollTop = el.scrollHeight
  }, [blocks])

  const run = (cmd: string) => {
    const trimmed = cmd.trim()
    if (!trimmed) return
    if (trimmed === "clear") {
      setBlocks([])
      setValue("")
      return
    }
    const match = TERM_COMMANDS.find((c) => c.cmd === trimmed)
    setBlocks((prev) => [
      ...prev,
      { id: nextId.current++, cmd: trimmed, out: match ? match.out : MISS },
    ])
    setValue("")
  }

  const submit = (e: FormEvent) => {
    e.preventDefault()
    run(value)
  }

  return (
    <div className={cn("vfs-term", className)}>
      <div className="vfs-term-bar">
        <span className="vfs-term-lights" aria-hidden="true">
          <i className="r" />
          <i className="y" />
          <i className="g" />
        </span>
        <span className="vfs-term-title">{title}</span>
        <span className="vfs-term-tag">demo</span>
      </div>

      <div
        className="vfs-term-body"
        ref={bodyRef}
        style={{ height: `calc(${rows} * 1.6em + 32px)` }}
      >
        {TERM_BANNER.map((line) => (
          <div key={line} className="vfs-term-line dim">
            {line}
          </div>
        ))}

        {blocks.map((b) => (
          <div key={b.id} className="vfs-term-block">
            <div className="vfs-term-line">
              <span className="vfs-term-prompt">vfs&nbsp;$</span>
              <span className="vfs-term-cmd">{b.cmd}</span>
            </div>
            {b.out.map((l, i) => (
              <div key={i} className={cn("vfs-term-line", l.kind)}>
                {l.text}
              </div>
            ))}
          </div>
        ))}

        <form className="vfs-term-line vfs-term-input" onSubmit={submit}>
          <label className="vfs-term-prompt" htmlFor="vfs-term-field">
            vfs&nbsp;$
          </label>
          <input
            id="vfs-term-field"
            value={value}
            onChange={(e) => setValue(e.target.value)}
            spellCheck={false}
            autoComplete="off"
            placeholder="try a command…"
            aria-label="vfs command"
          />
        </form>
      </div>

      <div className="vfs-term-suggest">
        <span className="vfs-term-suggest-label">try</span>
        {TERM_COMMANDS.map((c) => (
          <button
            key={c.cmd}
            type="button"
            className="vfs-term-chip"
            onClick={() => run(c.cmd)}
            title={c.cmd}
          >
            {c.label}
          </button>
        ))}
      </div>
    </div>
  )
}
