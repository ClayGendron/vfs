// In-memory fake VFS used by the /terminal route.
// Mirrors the path layout from the README: user namespace + /.vfs/... __meta__ tree.

export type Node =
  | { kind: "file"; content: string }
  | { kind: "dir"; children: Record<string, Node> }

const README = `# vfs
Agentic Search on any SQL Database.

  pip install vfs-py

An in-process file system that mounts data from multiple sources
to enable agentic search and operations through a Unix-like
interface.

Everything is addressable by path. Files live in the user namespace.
Metadata lives under /.vfs/<path>/__meta__/... and is opt-in — ls,
glob, and search operate on user paths by default.

Try:
  $ ls
  $ cat /workspace/auth.py
  $ tree /.vfs/workspace/auth.py/__meta__
  $ help
`

const INSTALL_SH = `#!/usr/bin/env sh
# install vfs-py
pip install vfs-py                 # core
pip install 'vfs-py[postgres]'     # postgres + pgvector
pip install 'vfs-py[mssql]'        # mssql
pip install 'vfs-py[all]'          # everything
`

const AUTH_PY = `from vfs import VFSClient
from vfs.backends import PostgresFileSystem


class AuthService:
    """Authenticate users against the enterprise identity store."""

    def __init__(self, g: VFSClient) -> None:
        self.g = g

    def login(self, user: str, password: str) -> bool:
        # resolve the policy from the mounted enterprise FS
        policy = self.g.read("/enterprise/security-policy.md")
        return authenticate(user, password, policy)
`

const SESSION_PY = `from vfs import VFSClient


def current_session(g: VFSClient, user: str) -> dict | None:
    result = g.grep(pattern=f"user={user}", path="/workspace/sessions")
    return result.top(1).first()
`

const UTILS_PY = `def authenticate(user: str, password: str, policy: str) -> bool:
    # placeholder — real impl lives elsewhere
    return bool(user and password and policy)
`

const SECURITY_POLICY_MD = `# Security Policy

## Authentication
- Sessions expire after 12h of inactivity.
- MFA required for admin roles.
- Service accounts must rotate keys every 90 days.

## Data access
- Read-only agents cannot invoke /enterprise/runbook/*.
- All reads are audited. All writes are versioned.
`

const ONBOARDING_MD = `# Onboarding

Welcome to the enterprise namespace. Files here are read-only for agents
unless explicitly granted write via capability negotiation.

See /enterprise/security-policy.md for the full policy.
`

const RUNBOOK_MD = `# Runbook

## Incident response
1. grep the symptom against /workspace logs.
2. nbr to expand through graph neighbors (imports, calls, refs).
3. pagerank to surface the likely culprit.
4. open an edit proposal — every write is reversible.
`

const FSP_MD = `# FSP — Filesystem Protocol

Status: draft · 2026-Q2

## Operations
  fs.read    MUST    return Entry with content, version, content_hash
  fs.write   MUST    create or update; optimistic concurrency via if_version
  fs.list    MUST    enumerate a directory
  fs.stat    MUST    return Entry without content
  fs.grep    SHOULD  pattern search, case-sensitive by default
  fs.glob    SHOULD  path pattern match
  fs.watch   SHOULD  stream change notifications

## Envelope
Every response is a VFSResult:
  {
    "function":    "fs.read",
    "success":     true,
    "entries":     [...],
    "candidates":  [...],
    "next_cursor": null
  }
`

const VFSRESULT_MD = `# VFSResult

One envelope for every operation. One set of rules for combining them.

  a & b       # intersection
  a | b       # union
  a - b       # difference
  a.top(n)    # rank-ordered slice
  a.first()   # convenience

This is what makes pipelines composable:

  g.cli('search "auth" | glob "/workspace/**/*.py" | nbr | pagerank')
`

const CHUNK_LOGIN = `# chunk: login
kind: function
path: /workspace/auth.py
line_start: 11
line_end: 14
hash: sha256:a1b2...e9f0
`

const CHUNK_AUTHSERVICE = `# chunk: AuthService
kind: class
path: /workspace/auth.py
line_start: 4
line_end: 14
hash: sha256:b2c3...f0a1
`

const VERSION_1 = `version: 1
kind: snapshot
created_at: 2026-04-20T12:01:04Z
`

const VERSION_2 = `version: 2
kind: diff
created_at: 2026-04-22T09:44:12Z
parent: 1
`

export const ROOT: Node = {
  kind: "dir",
  children: {
    "README.md": { kind: "file", content: README },
    "install.sh": { kind: "file", content: INSTALL_SH },
    spec: {
      kind: "dir",
      children: {
        "fsp-001.md": { kind: "file", content: FSP_MD },
        "vfs-result.md": { kind: "file", content: VFSRESULT_MD },
      },
    },
    workspace: {
      kind: "dir",
      children: {
        "auth.py": { kind: "file", content: AUTH_PY },
        "session.py": { kind: "file", content: SESSION_PY },
        "utils.py": { kind: "file", content: UTILS_PY },
      },
    },
    enterprise: {
      kind: "dir",
      children: {
        "onboarding.md": { kind: "file", content: ONBOARDING_MD },
        "security-policy.md": { kind: "file", content: SECURITY_POLICY_MD },
        "runbook.md": { kind: "file", content: RUNBOOK_MD },
      },
    },
    ".vfs": {
      kind: "dir",
      children: {
        workspace: {
          kind: "dir",
          children: {
            "auth.py": {
              kind: "dir",
              children: {
                __meta__: {
                  kind: "dir",
                  children: {
                    chunks: {
                      kind: "dir",
                      children: {
                        login: { kind: "file", content: CHUNK_LOGIN },
                        AuthService: {
                          kind: "file",
                          content: CHUNK_AUTHSERVICE,
                        },
                      },
                    },
                    versions: {
                      kind: "dir",
                      children: {
                        "1": { kind: "file", content: VERSION_1 },
                        "2": { kind: "file", content: VERSION_2 },
                      },
                    },
                    edges: {
                      kind: "dir",
                      children: {
                        out: {
                          kind: "dir",
                          children: {
                            imports: {
                              kind: "dir",
                              children: {
                                "workspace": {
                                  kind: "dir",
                                  children: {
                                    "utils.py": {
                                      kind: "file",
                                      content:
                                        "# edge: workspace/auth.py -> workspace/utils.py (imports)\n",
                                    },
                                  },
                                },
                              },
                            },
                          },
                        },
                      },
                    },
                  },
                },
              },
            },
          },
        },
      },
    },
  },
}

export function normalize(path: string, cwd: string): string {
  const raw = path.startsWith("/") ? path : joinPath(cwd, path)
  const parts: string[] = []
  for (const seg of raw.split("/")) {
    if (!seg || seg === ".") continue
    if (seg === "..") {
      parts.pop()
      continue
    }
    parts.push(seg)
  }
  return "/" + parts.join("/")
}

function joinPath(a: string, b: string): string {
  if (a.endsWith("/")) return a + b
  return a + "/" + b
}

export function lookup(path: string): Node | null {
  const parts = path.split("/").filter(Boolean)
  let node: Node = ROOT
  for (const part of parts) {
    if (node.kind !== "dir") return null
    const next = node.children[part]
    if (!next) return null
    node = next
  }
  return node
}

export function listDir(path: string): string[] | null {
  const node = lookup(path)
  if (!node || node.kind !== "dir") return null
  // dirs first, alpha within each group
  const entries = Object.entries(node.children)
  entries.sort((a, b) => {
    const ad = a[1].kind === "dir" ? 0 : 1
    const bd = b[1].kind === "dir" ? 0 : 1
    if (ad !== bd) return ad - bd
    return a[0].localeCompare(b[0])
  })
  return entries.map(([name, n]) => (n.kind === "dir" ? name + "/" : name))
}
