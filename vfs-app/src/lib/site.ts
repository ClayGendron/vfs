/** Shared so the number lives once — see `tests` and the `tests` metric. */
const TESTS = 1094

/**
 * One mount row, carrying the union of what both product visuals render:
 * NamespaceTree uses `treePath`/`store`; MountMap uses `mountpoint`/`backend`/
 * `mode`. Fields are optional because a mount may appear in only one visual.
 */
export type SiteMount = {
  treePath?: string
  store?: string
  mountpoint?: string
  backend?: string
  mode?: "in-process" | "mcp"
}

export const SITE = {
  name: "vfs",
  tagline: "Agentic Search on your Database",
  headline: "Agentic Search on\nyour Database",
  description:
    "Compose a fully-featured, Unix-like environment for your agents. VFS is built on one claim: glob, grep, glean, and graph are the four verbs any agent needs to navigate a knowledge base.",
  domain: "vfs.dev",
  repo: { owner: "ClayGendron", name: "vfs" },
  github: "https://github.com/ClayGendron/vfs",
  pypi: "https://pypi.org/project/vfs-py/",
  stage: "alpha",
  milestone: "2026-Q2",
  versionFallback: "v0.0.22",
  install: {
    python: "pip install vfs-py",
    python_postgres: "pip install 'vfs-py[postgres]'",
  },

  /** Green test count on the MCP-native core; drives copy and the metric. */
  tests: TESTS,

  /**
   * Full product topology as one list. Both visuals derive from it:
   * NamespaceTree renders rows with `treePath`, MountMap rows with `mountpoint`.
   */
  mounts: [
    { treePath: "enterprise/", store: "postgres", mountpoint: "/enterprise", backend: "PostgresFileSystem", mode: "in-process" },
    { treePath: "archive/", store: "mssql", mountpoint: "/archive", backend: "MSSQLFileSystem", mode: "in-process" },
    { treePath: "knowledge/", store: "sqlite", mountpoint: "/knowledge", backend: "DatabaseFileSystem · sqlite", mode: "in-process" },
    { treePath: "graph/", store: "rustworkx" },
    { mountpoint: "/agents", backend: "MCP server", mode: "mcp" },
  ] as SiteMount[],

  /**
   * Numbers shown in the spec strip directly under the hero. Keep the units
   * here so any copy that mentions them stays in sync.
   */
  metrics: [
    { label: "tests",     value: `${TESTS}`,                 signal: true },
    { label: "backends",  value: "PG · MSSQL · SQLITE" },
    { label: "retrieval", value: "BM25 · VECTOR" },
    { label: "graph",     value: "RUSTWORKX",                signal: true },
    { label: "runtime",   value: "PYTHON 3.12+" },
    { label: "license",   value: "APACHE 2.0" },
  ],

  /**
   * Ecosystem fit, plain-text grouped. Mirrors the recommendation table —
   * mono labels, square borders, no logo polish.
   */
  integrations: [
    {
      group: "backends",
      items: ["postgres", "mssql", "sqlite", "localfs (soon)"],
    },
    {
      group: "retrieval",
      items: ["bm25", "pgvector", "lexical search", "semantic search"],
    },
    {
      group: "graph",
      items: ["rustworkx", "neighborhood", "pagerank", "betweenness"],
    },
    {
      group: "agents",
      items: ["mcp", "langchain", "langgraph", "deepagents"],
    },
    {
      group: "embeddings",
      items: ["openai", "langchain providers"],
    },
    {
      group: "interfaces",
      items: ["python api", "cli", "async", "sync"],
    },
  ],

  /**
   * Direct positioning matrix. Ordered to clarify the most common
   * misreads first (vector DB, fsspec, retriever, graph DB).
   */
  positioning: [
    {
      already: "a vector database",
      adds:
        "paths, CRUD, lexical search, graph traversal, and CLI pipelines over one result contract.",
    },
    {
      already: "fsspec or object storage",
      adds:
        "search, ranking, and graph operations over mounted data — not just file access.",
    },
    {
      already: "LangChain or LangGraph retrievers",
      adds:
        "a composable context substrate agents query through Unix-like operations.",
    },
    {
      already: "a graph database",
      adds:
        "file-system semantics and retrieval workflows without making graph storage the whole product.",
    },
  ],
} as const

export type ValueArea = {
  id: string
  title: string
  body: string
  note: string
}

/** The six things vfs gives an agent that a vector index or a bespoke tool does not. */
export const VALUE_AREAS: ValueArea[] = [
  {
    id: "01",
    title: "One namespace",
    body:
      "Mount Postgres, MSSQL, SQLite, your retrievers and your graph under a single path tree. Agents learn one addressing scheme, not one per store.",
    note: "/enterprise · /archive · /knowledge",
  },
  {
    id: "02",
    title: "Four verbs, one contract",
    body:
      "glob, grep, glean, graph each return the same VFSResult — a set of paths with scores. Every verb's output is every other verb's input.",
    note: "VFSResult",
  },
  {
    id: "03",
    title: "Pipelines, not bespoke tools",
    body:
      "Compose with pipes and set algebra (& | −) instead of shipping a new tool per query shape. A pipeline is an expression an agent can write.",
    note: "grep … | nbr | pagerank | top 15",
  },
  {
    id: "04",
    title: "Runs on your database",
    body:
      "vfs is the protocol, not the storage. Point it at the database you already run — no migration, no new service, no vector store to operate.",
    note: "postgres · mssql · sqlite",
  },
  {
    id: "05",
    title: "MCP-native",
    body:
      "Serve the same namespace in-process with your app or over MCP. Agents mount vfs the way a machine mounts a disk.",
    note: "mcp · langchain · langgraph",
  },
  {
    id: "06",
    title: "Graph in the loop",
    body:
      "Neighborhood, PageRank and betweenness run over the relations already in your data, so ranking sees structure and not just text.",
    note: "rustworkx",
  },
]

export type SearchVerb = {
  name: "glob" | "grep" | "glean" | "graph"
  dim: string
}

/** One verb per dimension a file carries information along. */
export const SEARCH_VERBS: SearchVerb[] = [
  { name: "glob", dim: "where it sits" },
  { name: "grep", dim: "what it says" },
  { name: "glean", dim: "what it means" },
  { name: "graph", dim: "what it connects to" },
]

export type TermLine = { kind: "out" | "dim" | "hit" | "sig"; text: string }

export type TermCommand = {
  cmd: string
  label: string
  out: TermLine[]
}

/**
 * Canned transcript behind the try-it terminal. The commands are real vfs
 * pipelines; the output is fixed until the live repl lands.
 */
export const TERM_COMMANDS: TermCommand[] = [
  {
    cmd: 'glob "/enterprise/**/*.py"',
    label: "glob",
    out: [
      { kind: "out", text: "/enterprise/auth.py" },
      { kind: "out", text: "/enterprise/session.py" },
      { kind: "out", text: "/enterprise/api/routes.py" },
      { kind: "out", text: "/enterprise/api/deps.py" },
      { kind: "dim", text: "… 212 more · 216 paths in 41ms" },
    ],
  },
  {
    cmd: 'grep "authenticate"',
    label: "grep",
    out: [
      { kind: "hit", text: "/enterprise/auth.py:88      def authenticate(user, token):" },
      { kind: "hit", text: "/enterprise/session.py:14   from .auth import authenticate" },
      { kind: "hit", text: "/archive/2019/legacy.py:301 # authenticate against LDAP" },
      { kind: "dim", text: "3 paths · 9 spans · bm25 ranked · 22ms" },
    ],
  },
  {
    cmd: 'glean "how do sessions expire?"',
    label: "glean",
    out: [
      { kind: "sig", text: "0.91  /enterprise/session.py" },
      { kind: "sig", text: "0.84  /knowledge/rfc/session-ttl.md" },
      { kind: "sig", text: "0.77  /enterprise/auth.py" },
      { kind: "dim", text: "semantic · top 3 of 128 candidates · 64ms" },
    ],
  },
  {
    cmd: "graph nbr /enterprise/auth.py --depth 2",
    label: "graph",
    out: [
      { kind: "out", text: "/enterprise/auth.py" },
      { kind: "out", text: "├── imports → /enterprise/crypto.py" },
      { kind: "out", text: "├── imported-by → /enterprise/session.py" },
      { kind: "out", text: "└── imported-by → /enterprise/api/deps.py" },
      { kind: "dim", text: "11 nodes · 17 edges · depth 2 · 8ms" },
    ],
  },
  {
    cmd: 'grep "authenticate" | nbr | pagerank | top 5',
    label: "pipeline",
    out: [
      { kind: "sig", text: "0.142  /enterprise/auth.py" },
      { kind: "sig", text: "0.098  /enterprise/session.py" },
      { kind: "sig", text: "0.071  /enterprise/crypto.py" },
      { kind: "sig", text: "0.055  /enterprise/api/deps.py" },
      { kind: "sig", text: "0.041  /knowledge/rfc/session-ttl.md" },
      { kind: "dim", text: "grep → neighborhood → pagerank → top 5 · 96ms" },
    ],
  },
]

export const TERM_BANNER = [
  `vfs ${SITE.versionFallback} · sandboxed repl over a sample repo`,
  "pick a command below, or type one yourself",
]

export type SiteDir = {
  path: string
  desc: string
  to?: string
  href?: string
}

export const FS_LISTING: SiteDir[] = [
  { path: "/", desc: "home · what vfs is", to: "/" },
  { path: "/about/", desc: "thesis · lineage · status", to: "/about" },
  { path: "/blog/", desc: "notes from the spec", to: "/blog" },
  { path: "/terminal/", desc: "live vfs repl", to: "/terminal" },
  {
    path: "/github/",
    desc: "source · issues · releases",
    href: "https://github.com/ClayGendron/vfs",
  },
  { path: "/install.sh", desc: "pip install vfs-py" },
]

export type RouteMeta = {
  title: string
  description: string
  canonical?: string
}

/**
 * Per-route document head. Home keeps the full brand title; inner pages use the
 * "<page> — vfs" pattern. Error states carry no canonical. React hoists these.
 */
export const routeMeta = {
  home: {
    title: "vfs: Agentic Search on any SQL Database",
    description: SITE.description,
    canonical: "https://vfs.dev/",
  },
  about: {
    title: "about — vfs",
    description:
      "The context layer for agents — the thesis behind vfs, its Unix lineage, core components, and current alpha status.",
    canonical: "https://vfs.dev/about",
  },
  blog: {
    title: "blog — vfs",
    description:
      "Notes from the spec — essays on filesystems for agents, the one-envelope VFSResult, and graph pushdown into your database.",
    canonical: "https://vfs.dev/blog",
  },
  terminal: {
    title: "terminal — vfs",
    description:
      "A live in-browser vfs repl — explore a virtual filesystem with ls, cd, cat, tree, and stat. No network, every byte local.",
    canonical: "https://vfs.dev/terminal",
  },
  notFound: {
    title: "404 — vfs",
    description: "No such entry — the requested path does not exist in the vfs namespace.",
  },
  error: {
    title: "error — vfs",
    description: "Something threw — an unexpected error occurred while rendering this page.",
  },
} satisfies Record<string, RouteMeta>
