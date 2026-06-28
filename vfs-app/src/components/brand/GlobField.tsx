import type { CSSProperties } from "react"
import { cn } from "@/lib/utils"

/**
 * glob · location — a file tree.
 *
 * A directory listing with tree guides, static by default with the matched
 * file faintly lit. On hover the path from the root down to the match
 * resolves segment by segment in colour — a glob landing on a file.
 */

type Row = {
  prefix: string
  name: string
  dir?: boolean
  match?: boolean
  step?: number // present when the row is on the resolved path
}

const ROWS: Row[] = [
  { prefix: "", name: "enterprise/", dir: true, step: 0 },
  { prefix: "├─ ", name: "auth/", dir: true, step: 1 },
  { prefix: "│  ├─ ", name: "login.py" },
  { prefix: "│  └─ ", name: "tokens.py", match: true, step: 2 },
  { prefix: "├─ ", name: "models/", dir: true },
  { prefix: "│  └─ ", name: "user.py" },
  { prefix: "└─ ", name: "policy.md" },
]

export function GlobField({ active }: { active: boolean }) {
  return (
    <div className={cn("gb", active && "is-on")} aria-hidden="true">
      {ROWS.map((r, i) => {
        const onPath = r.step !== undefined
        return (
          <div className="gb-row" key={i}>
            <span className="gb-prefix">{r.prefix}</span>
            <span
              className={cn(
                "gb-name",
                r.dir && "is-dir",
                r.match && "is-match",
                onPath && "is-path",
              )}
              style={onPath ? ({ "--d": r.step } as CSSProperties) : undefined}
            >
              {r.name}
            </span>
          </div>
        )
      })}
    </div>
  )
}
