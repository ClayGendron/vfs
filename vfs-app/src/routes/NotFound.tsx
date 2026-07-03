import { useEffect, useRef, useState } from "react"
import type { KeyboardEvent } from "react"
import { useLocation, useNavigate } from "react-router-dom"
import { Seo } from "@/components/Seo"
import { routeMeta, SITE } from "@/lib/site"

type Line =
  | { kind: "echo"; text: string }
  | { kind: "echo-bare"; text: string }
  | { kind: "out"; text: string }
  | { kind: "err"; text: string }
  | { kind: "hint"; text: string }

const ROUTES: Record<string, string> = {
  "/": "/",
  "home": "/",
  "/home": "/",
  "about": "/about",
  "/about": "/about",
  "blog": "/blog",
  "/blog": "/blog",
  "terminal": "/terminal",
  "/terminal": "/terminal",
}

const ALLOWED = [
  "cd /",
  "cd home",
  "cd about",
  "cd blog",
  "cd terminal",
  "cd github",
]

export function NotFound() {
  const loc = useLocation()
  const navigate = useNavigate()
  const path = loc.pathname

  const [history, setHistory] = useState<Line[]>(() => [
    { kind: "echo-bare", text: `cd ${path}` },
    { kind: "err", text: "vfs: No such file or directory" },
    { kind: "hint", text: "type `help` to list available commands" },
  ])
  const [value, setValue] = useState("")
  const [recall, setRecall] = useState<string[]>([])
  const [recallIdx, setRecallIdx] = useState(-1)
  const inputRef = useRef<HTMLInputElement>(null)
  const scrollRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    inputRef.current?.focus()
  }, [])

  useEffect(() => {
    if (scrollRef.current) {
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight
    }
  }, [history])

  const append = (entries: Line[]) => setHistory((h) => [...h, ...entries])

  const run = (raw: string) => {
    const cmd = raw.trim()
    const echo: Line = { kind: "echo", text: raw }
    if (!cmd) {
      append([echo])
      return
    }

    setRecall((r) => [...r, cmd])
    setRecallIdx(-1)

    if (cmd === "help" || cmd === "ls" || cmd === "ls /") {
      append([
        echo,
        { kind: "out", text: "available commands:" },
        ...ALLOWED.map<Line>((c) => ({ kind: "out", text: "  " + c })),
      ])
      return
    }
    if (cmd === "clear") {
      setHistory([])
      return
    }
    if (cmd === "pwd") {
      append([echo, { kind: "out", text: path }])
      return
    }

    const m = cmd.match(/^cd\s+(.+)$/)
    if (m) {
      const target = (m[1] ?? "").trim()
      if (target === "github" || target === "/github") {
        append([echo, { kind: "out", text: "→ opening github.com/ClayGendron/vfs" }])
        window.open(SITE.github, "_blank", "noopener,noreferrer")
        return
      }
      const to = ROUTES[target]
      if (to) {
        append([echo, { kind: "out", text: `→ ${to}` }])
        setTimeout(() => navigate(to), 220)
        return
      }
      append([echo, { kind: "err", text: "vfs: No such file or directory" }])
      return
    }

    append([echo, { kind: "err", text: `vfs: ${cmd} command not found, try help` }])
  }

  const onKey = (e: KeyboardEvent<HTMLInputElement>) => {
    if (e.key === "Enter") {
      e.preventDefault()
      run(value)
      setValue("")
      return
    }
    if (e.key === "ArrowUp") {
      e.preventDefault()
      if (!recall.length) return
      const next = recallIdx < 0 ? recall.length - 1 : Math.max(0, recallIdx - 1)
      setRecallIdx(next)
      setValue(recall[next] ?? "")
      return
    }
    if (e.key === "ArrowDown") {
      e.preventDefault()
      if (recallIdx < 0) return
      const next = recallIdx + 1
      if (next >= recall.length) {
        setRecallIdx(-1)
        setValue("")
      } else {
        setRecallIdx(next)
        setValue(recall[next] ?? "")
      }
      return
    }
    if (e.key === "Tab") {
      e.preventDefault()
      const m = value.match(/^cd\s+(.*)$/)
      if (!m) return
      const stub = m[1] ?? ""
      const targets = ["/", "home", "about", "blog", "terminal", "github"]
      const matches = targets.filter((t) => t.startsWith(stub))
      if (matches[0] && matches.length === 1) setValue("cd " + matches[0])
    }
  }

  return (
    // click anywhere focuses the input; keyboard users tab straight to it, so no key handler needed
    // eslint-disable-next-line jsx-a11y/click-events-have-key-events, jsx-a11y/no-noninteractive-element-interactions
    <main className="vfs-404" onClick={() => inputRef.current?.focus()}>
      <Seo {...routeMeta.notFound} />
      <div className="cap">404 · no such entry</div>
      <h1 className="title">/404</h1>

      <div className="vfs-404-term" ref={scrollRef}>
        {history.map((line, i) => {
          if (line.kind === "echo") {
            return (
              <div key={i} className="line">
                <span className="prompt">$</span>
                <span className="cmd">{line.text}</span>
              </div>
            )
          }
          if (line.kind === "echo-bare") {
            return (
              <div key={i} className="line cmd-bare">
                {line.text}
              </div>
            )
          }
          if (line.kind === "err") {
            return (
              <div key={i} className="line err">
                {line.text}
              </div>
            )
          }
          if (line.kind === "hint") {
            return (
              <div key={i} className="line hint">
                {line.text}
              </div>
            )
          }
          return (
            <div key={i} className="line out">
              {line.text}
            </div>
          )
        })}
        <div className="line input-line">
          <span className="prompt">$</span>
          <span className="input-wrap">
            <span className="mirror" aria-hidden="true">
              {value}
            </span>
            <input
              ref={inputRef}
              className="input"
              type="text"
              spellCheck={false}
              autoCapitalize="off"
              autoCorrect="off"
              value={value}
              onChange={(e) => setValue(e.target.value)}
              onKeyDown={onKey}
              aria-label="terminal input"
            />
            <span className="block-caret" aria-hidden="true" />
          </span>
        </div>
      </div>
    </main>
  )
}
