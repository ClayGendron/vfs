import { Link, useLocation } from "react-router-dom"

export function NotFound() {
  const loc = useLocation()
  return (
    <section className="px-[8vw] py-24">
      <div className="mono text-[10px] tracking-[0.28em] uppercase text-[var(--quiet)] mb-6">
        404 · no such entry
      </div>
      <h1 className="font-[family-name:var(--font-brand)] font-medium text-[clamp(72px,12vw,160px)] leading-[0.9]">
        /404
      </h1>
      <p className="mt-6 max-w-prose text-[15px] leading-relaxed text-[var(--muted)]">
        <code className="mono">stat: {loc.pathname}: No such entry</code>
      </p>
      <p className="mt-4 max-w-prose text-[15px] leading-relaxed text-[var(--muted)]">
        Every surface of this site is a path, but not every path exists.{" "}
        <Link
          to="/"
          className="underline underline-offset-4 text-[var(--accent)]"
        >
          cd /
        </Link>
      </p>
    </section>
  )
}
