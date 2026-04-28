import { SITE } from "@/lib/site"

type Post = {
  slug: string
  title: string
  date: string
  lede: string
  read: string
}

// stubs for v1 — real posts will come in as markdown or MDX later
const POSTS: Post[] = [
  {
    slug: "why-a-filesystem-for-agents",
    title: "Why a filesystem for agents",
    date: "2026-04-24",
    lede: "Unix won the context war in the 70s. Agents need the same primitives — paths, composition, versioning — over enterprise data, not files on disk.",
    read: "6 min",
  },
  {
    slug: "vfsresult-one-envelope",
    title: "One envelope, every operation",
    date: "2026-04-17",
    lede: "Every vfs op returns the same VFSResult. Set algebra (& | -), CLI pipes, re-ranking — how a single type collapses half a retrieval pipeline into one line.",
    read: "4 min",
  },
  {
    slug: "graph-pushdown-postgres",
    title: "Pushing graph traversal into Postgres",
    date: "2026-04-10",
    lede: "PageRank over pg_graph, CONTAINS-driven grep, pgvector retrieval — why the right database is the right place for retrieval, not a sidecar.",
    read: "7 min",
  },
]

export function Blog() {
  return (
    <section className="vfs-blog">
      <header className="vfs-blog-head">
        <h1 className="vfs-blog-title">blog</h1>
        <div className="vfs-blog-meta">
          <div>notes from the spec</div>
          <div>
            {SITE.stage} · {SITE.milestone}
          </div>
          <div className="signal">3 posts</div>
        </div>
      </header>

      <div className="vfs-blog-list">
        {POSTS.map((p) => (
          <article
            key={p.slug}
            className="vfs-blog-item"
            role="link"
            tabIndex={-1}
            aria-disabled
            title="Coming soon"
          >
            <div className="vfs-blog-item-date">{p.date}</div>
            <div>
              <div className="vfs-blog-item-title">{p.title}</div>
              <div className="vfs-blog-item-sub">{p.lede}</div>
            </div>
            <div className="vfs-blog-item-cta">{p.read} · soon</div>
          </article>
        ))}
      </div>
    </section>
  )
}
