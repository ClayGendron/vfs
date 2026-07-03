import { NavLink } from "react-router-dom"
import { ThemeToggle } from "./ThemeToggle"
import { SITE } from "@/lib/site"
import { useLatestRelease } from "@/hooks/useLatestRelease"

const RELEASES_URL = "https://github.com/ClayGendron/vfs/releases/"

const nav = [
  { to: "/", label: "home", end: true },
  { to: "/about", label: "about" },
  { to: "/blog", label: "blog" },
  { to: "/terminal", label: "terminal" },
]

export function Topbar() {
  const { version, url } = useLatestRelease()

  return (
    <header className="vfs-chrome">
      <NavLink to="/" end className="vfs-spec-word" aria-label="vfs home">
        <span className="word">vfs</span>
      </NavLink>

      <nav className="vfs-spec-nav" aria-label="Primary">
        {nav.map((item) => (
          <NavLink
            key={item.to}
            to={item.to}
            end={item.end}
            className={({ isActive }) =>
              isActive ? "cell active" : "cell"
            }
          >
            <span className="dot" aria-hidden="true" />
            <span>{item.label}</span>
          </NavLink>
        ))}
        <a
          href={SITE.github}
          target="_blank"
          rel="noopener noreferrer"
          className="cell"
        >
          <span className="dot" aria-hidden="true" />
          <span>github</span>
        </a>
      </nav>

      <div className="vfs-spec-right">
        <a
          href={url ?? RELEASES_URL}
          target="_blank"
          rel="noreferrer"
          className="vfs-spec-ver"
          title="Releases on GitHub"
        >
          {version}
        </a>
        <ThemeToggle />
      </div>
    </header>
  )
}
