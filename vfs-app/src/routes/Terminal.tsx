import { useEffect, useRef, useState } from "react"
import type { FormEvent, KeyboardEvent, ReactNode } from "react"
import { ScrollArea } from "@/components/ui/scroll-area"
import { Seo } from "@/components/Seo"
import { lookup, listDir, normalize } from "@/lib/fakeFs"
import { routeMeta, SITE } from "@/lib/site"

type LineKind = "out" | "err" | "prompt" | "banner" | "dim"

type Line = { id: number; kind: LineKind; content: ReactNode }

const BANNER = `vfs · virtual filesystem for agents
${SITE.stage} · ${SITE.versionFallback} · ${SITE.milestone}
type \`help\` for commands, \`ls\` to start, \`clear\` to reset.`

const HELP = `commands
  ls [path]              list a directory
  cd <path>              change directory
  pwd                    print working directory
  cat <path>             print file content
  tree [path]            print subtree
  stat <path>            print entry metadata
  whoami                 print current user
  echo <text>            print text
  clear                  clear the screen (alias: cls)
  help                   this message (alias: ?)

paths
  absolute (/workspace) or relative (./auth.py, ../spec)
  ~ aliases to /
  up-arrow / down-arrow walks history
  tab completes commands and paths`

const COMMANDS = ["cat", "cd", "clear", "echo", "help", "ls", "pwd", "stat", "tree", "whoami"]

function treeOf(path: string, depth = 0, prefix = ""): string[] {
  const node = lookup(path)
  if (!node) return [`tree: ${path}: No such path`]
  if (node.kind === "file") return [path]
  const lines: string[] = depth === 0 ? [path] : []
  const names = Object.keys(node.children).sort((a, b) => {
    const ad = node.children[a]?.kind === "dir" ? 0 : 1
    const bd = node.children[b]?.kind === "dir" ? 0 : 1
    if (ad !== bd) return ad - bd
    return a.localeCompare(b)
  })
  names.forEach((name, i) => {
    const last = i === names.length - 1
    const child = node.children[name]
    if (!child) return
    const head = prefix + (last ? "└── " : "├── ")
    const trail = prefix + (last ? "    " : "│   ")
    lines.push(head + name + (child.kind === "dir" ? "/" : ""))
    if (child.kind === "dir") {
      const sub = treeOf(
        (path.endsWith("/") ? path : path + "/") + name,
        depth + 1,
        trail,
      )
      lines.push(...sub)
    }
  })
  return lines
}

export function Terminal() {
  const [cwd, setCwd] = useState("/")
  const [lines, setLines] = useState<Line[]>(() => [
    { id: 0, kind: "banner", content: BANNER },
  ])
  const [input, setInput] = useState("")
  const [history, setHistory] = useState<string[]>([])
  const [histIx, setHistIx] = useState<number | null>(null)
  const idRef = useRef(1)
  const bodyRef = useRef<HTMLDivElement>(null)
  const inputRef = useRef<HTMLInputElement>(null)

  const push = (kind: LineKind, content: ReactNode) => {
    setLines((prev) => [...prev, { id: idRef.current++, kind, content }])
  }

  useEffect(() => {
    // scroll to bottom on any new line
    const el = bodyRef.current
    if (el) el.scrollTop = el.scrollHeight
  }, [lines])

  useEffect(() => {
    // autofocus; re-focus on any click in the shell
    inputRef.current?.focus()
  }, [])

  const resolve = (arg: string) => {
    const expanded = arg === "~" ? "/" : arg.replace(/^~\//, "/")
    return normalize(expanded, cwd)
  }

  const run = (raw: string) => {
    const cmd = raw.trim()
    if (!cmd) {
      push("prompt", <PromptLine cwd={cwd} line="" />)
      return
    }

    // echo the prompt + command
    push("prompt", <PromptLine cwd={cwd} line={cmd} />)

    const [head, ...rest] = cmd.split(/\s+/)
    const arg = rest.join(" ")

    switch (head) {
      case "help":
      case "?":
        push("dim", HELP)
        break
      case "clear":
      case "cls":
        setLines([])
        idRef.current = 0
        break
      case "pwd":
        push("out", cwd)
        break
      case "ls": {
        const target = arg ? resolve(arg) : cwd
        const entries = listDir(target)
        if (!entries) {
          push("err", `ls: ${target}: No such directory`)
          break
        }
        push(
          "out",
          entries.length
            ? entries.map((e) => (e.endsWith("/") ? e : "  " + e)).join("\n")
            : "(empty)",
        )
        break
      }
      case "cd": {
        const target = !arg || arg === "~" ? "/" : resolve(arg)
        const node = lookup(target)
        if (!node) {
          push("err", `cd: ${target}: No such directory`)
        } else if (node.kind !== "dir") {
          push("err", `cd: ${target}: Not a directory`)
        } else {
          setCwd(target)
        }
        break
      }
      case "cat": {
        if (!arg) {
          push("err", "cat: missing operand")
          break
        }
        const target = resolve(arg)
        const node = lookup(target)
        if (!node) {
          push("err", `cat: ${target}: No such file`)
        } else if (node.kind === "dir") {
          push("err", `cat: ${target}: Is a directory`)
        } else {
          push("out", node.content)
        }
        break
      }
      case "tree": {
        const target = arg ? resolve(arg) : cwd
        const lines = treeOf(target)
        push("out", lines.join("\n"))
        break
      }
      case "stat": {
        if (!arg) {
          push("err", "stat: missing operand")
          break
        }
        const target = resolve(arg)
        const node = lookup(target)
        if (!node) {
          push("err", `stat: ${target}: No such entry`)
          break
        }
        const kind = node.kind === "dir" ? "directory" : "file"
        const size =
          node.kind === "file" ? node.content.length : Object.keys(node.children).length
        push(
          "out",
          [
            `path:     ${target}`,
            `kind:     ${kind}`,
            `size:     ${size}${node.kind === "dir" ? " entries" : " bytes"}`,
            `version:  1`,
            `hash:     sha256:${Math.abs(hash(target)).toString(16).padStart(12, "0")}...`,
          ].join("\n"),
        )
        break
      }
      case "whoami":
        push("out", "agent")
        break
      case "echo":
        push("out", arg)
        break
      default:
        push("err", `${head}: command not found (try \`help\`)`)
    }
  }

  const onSubmit = (e: FormEvent) => {
    e.preventDefault()
    const v = input
    run(v)
    if (v.trim()) {
      setHistory((h) => [...h, v])
    }
    setHistIx(null)
    setInput("")
  }

  const onKeyDown = (e: KeyboardEvent<HTMLInputElement>) => {
    if (e.key === "ArrowUp") {
      e.preventDefault()
      if (!history.length) return
      const next = histIx === null ? history.length - 1 : Math.max(0, histIx - 1)
      setHistIx(next)
      setInput(history[next] ?? "")
    } else if (e.key === "ArrowDown") {
      e.preventDefault()
      if (histIx === null) return
      const next = histIx + 1
      if (next >= history.length) {
        setHistIx(null)
        setInput("")
      } else {
        setHistIx(next)
        setInput(history[next] ?? "")
      }
    } else if (e.key === "Tab") {
      e.preventDefault()
      const parts = input.split(/\s+/)
      if (parts.length <= 1) {
        // first token: complete a command name
        const matches = COMMANDS.filter((c) => c.startsWith(parts[0] ?? ""))
        if (matches[0] && matches.length === 1) setInput(matches[0] + " ")
        else if (matches.length > 1) push("out", matches.join("  "))
      } else {
        // later token: complete a path from the fake fs
        const stub = parts[parts.length - 1] ?? ""
        const slash = stub.lastIndexOf("/")
        const dirPart = slash >= 0 ? stub.slice(0, slash + 1) : ""
        const base = slash >= 0 ? stub.slice(slash + 1) : stub
        const entries = listDir(resolve(dirPart || ".")) ?? []
        const matches = entries.filter((e) => e.startsWith(base))
        if (matches[0] && matches.length === 1) {
          parts[parts.length - 1] = dirPart + matches[0]
          setInput(parts.join(" "))
        } else if (matches.length > 1) {
          push("out", matches.join("  "))
        }
      }
    } else if (e.key === "l" && (e.ctrlKey || e.metaKey)) {
      e.preventDefault()
      setLines([])
      idRef.current = 0
    }
  }

  return (
    <section className="vfs-term">
      <Seo {...routeMeta.terminal} />
      <header className="vfs-term-head">
        <h1 className="vfs-term-title">terminal</h1>
        <div className="vfs-term-sub">
          <div>live repl · in-memory vfs</div>
          <div>
            mount · root <span className="signal">/</span>
          </div>
          <div>no network — every byte is local</div>
        </div>
      </header>

      {/* click anywhere focuses the input; keyboard users tab straight to it, so no key handler needed */}
      {/* eslint-disable-next-line jsx-a11y/click-events-have-key-events, jsx-a11y/no-static-element-interactions */}
      <div
        className="vfs-term-shell"
        onClick={() => inputRef.current?.focus()}
      >
        <div className="vfs-term-bar">
          <span>$ vfs --repl</span>
          <span>
            cwd <span className="vfs-term-path">{cwd}</span>
          </span>
        </div>
        <ScrollArea className="flex-1">
          <div className="vfs-term-body" ref={bodyRef}>
            {lines.map((ln) => (
              <div
                key={ln.id}
                className={[
                  "vfs-term-line",
                  ln.kind === "err" && "vfs-term-err",
                  ln.kind === "dim" && "vfs-term-dim",
                  ln.kind === "banner" && "vfs-term-dim",
                ]
                  .filter(Boolean)
                  .join(" ")}
              >
                {ln.content}
              </div>
            ))}
            <form onSubmit={onSubmit} className="vfs-term-inputline">
              <span className="prompt">$</span>
              <span className="input-wrap">
                <span className="mirror" aria-hidden="true">
                  {input}
                </span>
                <input
                  ref={inputRef}
                  className="input"
                  value={input}
                  onChange={(e) => setInput(e.target.value)}
                  onKeyDown={onKeyDown}
                  autoComplete="off"
                  autoCorrect="off"
                  autoCapitalize="off"
                  spellCheck={false}
                  aria-label="terminal input"
                />
                <span className="block-caret" aria-hidden="true" />
              </span>
            </form>
          </div>
        </ScrollArea>
      </div>
    </section>
  )
}

function PromptLine({ cwd, line }: { cwd: string; line: string }) {
  return (
    <>
      <span className="vfs-term-path">{cwd}</span>
      <span className="vfs-term-prompt">$</span>
      <span>{line}</span>
    </>
  )
}

// tiny deterministic hash so `stat` shows stable fake hashes
function hash(s: string): number {
  let h = 0
  for (let i = 0; i < s.length; i++) {
    h = (h << 5) - h + s.charCodeAt(i)
    h |= 0
  }
  return h
}

