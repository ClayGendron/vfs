import { useEffect, useState } from "react"
import { SITE } from "@/lib/site"

type ReleaseState = {
  version: string
  url: string
  loading: boolean
  fromCache: boolean
  error: Error | null
}

const CACHE_KEY = "vfs:latest-release"
const TTL_MS = 15 * 60 * 1000 // 15 min — friendly to GitHub's 60 req/hr anon limit

type Cached = { version: string; url: string; at: number }

function readCache(): Cached | null {
  try {
    const raw = localStorage.getItem(CACHE_KEY)
    if (!raw) return null
    const parsed = JSON.parse(raw) as Cached
    if (Date.now() - parsed.at > TTL_MS) return null
    return parsed
  } catch {
    return null
  }
}

function writeCache(v: Cached) {
  try {
    localStorage.setItem(CACHE_KEY, JSON.stringify(v))
  } catch {
    // storage full / denied — non-fatal
  }
}

/**
 * Pulls the latest release tag from GitHub. Caches 15 min in localStorage.
 * Falls back to SITE.versionFallback on error or before the first fetch lands.
 */
export function useLatestRelease(): ReleaseState {
  const cached = typeof window !== "undefined" ? readCache() : null
  const [version, setVersion] = useState(cached?.version ?? SITE.versionFallback)
  const [url, setUrl] = useState(
    cached?.url ?? `${SITE.github}/releases/latest`,
  )
  const [loading, setLoading] = useState(!cached)
  const [error, setError] = useState<Error | null>(null)

  useEffect(() => {
    if (cached) {
      setLoading(false)
      return
    }
    const ctrl = new AbortController()
    const { owner, name } = SITE.repo
    fetch(`https://api.github.com/repos/${owner}/${name}/releases/latest`, {
      headers: { Accept: "application/vnd.github+json" },
      signal: ctrl.signal,
    })
      .then((r) => {
        if (!r.ok) throw new Error(`GitHub API ${r.status}`)
        return r.json() as Promise<{ tag_name: string; html_url: string }>
      })
      .then((data) => {
        setVersion(data.tag_name)
        setUrl(data.html_url)
        setLoading(false)
        writeCache({ version: data.tag_name, url: data.html_url, at: Date.now() })
      })
      .catch((e) => {
        if (e.name === "AbortError") return
        setError(e instanceof Error ? e : new Error(String(e)))
        setLoading(false)
      })
    return () => ctrl.abort()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  return { version, url, loading, fromCache: !!cached, error }
}
