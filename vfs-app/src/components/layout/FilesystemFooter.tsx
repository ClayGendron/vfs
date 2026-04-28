import { Link } from "react-router-dom"
import { FS_LISTING, SITE } from "@/lib/site"
import { useLatestRelease } from "@/hooks/useLatestRelease"

// pad each path so descriptions line up — terminal-style column layout
function pad(s: string, n: number) {
  return s.length >= n ? s : s + " ".repeat(n - s.length)
}

export function FilesystemFooter() {
  const { version } = useLatestRelease()
  const col = Math.max(...FS_LISTING.map((d) => d.path.length)) + 4

  return (
    <footer className="vfs-fs-footer" aria-labelledby="fs-footer-lead">
      <div>
        <div id="fs-footer-lead" className="vfs-fs-footer-lead">
          The homepage <em>is</em> the filesystem.
        </div>
        <p className="vfs-fs-footer-sub">
          Every surface of this site is a path. Navigate by clicking, or open{" "}
          <Link to="/terminal" className="underline underline-offset-4">
            /terminal
          </Link>{" "}
          and type.
        </p>
      </div>

      <pre className="vfs-fs-footer-listing" aria-label="Site directory listing">
        <span className="prompt">$ </span>
        <span>curl {SITE.domain} | sh</span>
        {"\n\n"}
        <span className="desc">{SITE.name} · {SITE.tagline.toLowerCase().replace(/\.$/, "")}</span>
        {"\n"}
        <span className="desc">
          {SITE.stage} · {version} · {SITE.milestone}
        </span>
        {"\n\n"}
        {FS_LISTING.map((d) => (
          <span key={d.path}>
            <span className="path">
              {d.href ? (
                <a href={d.href} target="_blank" rel="noreferrer">
                  {pad(d.path, col)}
                </a>
              ) : d.to ? (
                <Link to={d.to}>{pad(d.path, col)}</Link>
              ) : (
                pad(d.path, col)
              )}
            </span>
            <span className="desc">{d.desc}</span>
            {"\n"}
          </span>
        ))}
        {"\n"}
        <span className="prompt">$ </span>
        <span className="sig">_</span>
      </pre>

      <div className="vfs-fs-footer-baseline">
        <span>© {SITE.name}.dev · apache 2.0</span>
        <span>built with vfs · served from a filesystem</span>
      </div>
    </footer>
  )
}
