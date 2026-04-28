import { NavLink } from "react-router-dom"
import { GithubLogoIcon } from "@phosphor-icons/react"
import { ThemeToggle } from "./ThemeToggle"
import { SITE } from "@/lib/site"
import { useLatestRelease } from "@/hooks/useLatestRelease"

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
      <NavLink to="/" end className="vfs-chrome-brand">
        vfs<span className="vfs-chrome-brand-dot" aria-hidden />
      </NavLink>

      <nav className="vfs-chrome-nav" aria-label="Primary">
        {nav.map((item) => (
          <NavLink key={item.to} to={item.to} end={item.end}>
            {item.label}
          </NavLink>
        ))}
      </nav>

      <div className="vfs-chrome-right">
        <a
          href={url}
          target="_blank"
          rel="noreferrer"
          className="vfs-chrome-meta hidden md:inline hover:text-[var(--fg)] transition-colors"
          title="Latest release on GitHub"
        >
          alpha · {version}
        </a>
        <a
          href={SITE.github}
          target="_blank"
          rel="noreferrer"
          className="vfs-chrome-icon"
          aria-label="GitHub"
          title="GitHub"
        >
          <GithubLogoIcon className="size-4" weight="regular" />
        </a>
        <ThemeToggle />
      </div>
    </header>
  )
}
