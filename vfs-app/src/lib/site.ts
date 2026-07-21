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
