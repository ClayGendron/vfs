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

// Shared across all consumers so N hooks make at most one fetch per TTL window.
let memory: Cached | null = null
let inflight: Promise<Cached> | null = null

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

// Fresh value from memory first, then localStorage — never a stale entry.
function getFresh(): Cached | null {
  if (typeof window === "undefined") return null
  if (memory && Date.now() - memory.at <= TTL_MS) return memory
  const cached = readCache()
  if (cached) memory = cached
  return cached
}

function fetchRelease(): Promise<Cached> {
  const fresh = getFresh()
  if (fresh) return Promise.resolve(fresh)
  if (inflight) return inflight
  const { owner, name } = SITE.repo
  inflight = fetch(
    `https://api.github.com/repos/${owner}/${name}/releases/latest`,
    { headers: { Accept: "application/vnd.github+json" } },
  )
    .then((r) => {
      if (!r.ok) throw new Error(`GitHub API ${r.status}`)
      return r.json() as Promise<{ tag_name: string; html_url: string }>
    })
    .then((data) => {
      const value: Cached = {
        version: data.tag_name,
        url: data.html_url,
        at: Date.now(),
      }
      memory = value
      writeCache(value)
      inflight = null
      return value
    })
    .catch((e) => {
      inflight = null
      throw e
    })
  return inflight
}

function initialState(): ReleaseState {
  const cached = getFresh()
  if (cached) {
    return {
      version: cached.version,
      url: cached.url,
      loading: false,
      fromCache: true,
      error: null,
    }
  }
  return {
    version: SITE.versionFallback,
    url: `${SITE.github}/releases/latest`,
    loading: true,
    fromCache: false,
    error: null,
  }
}

/**
 * Pulls the latest release tag from GitHub. Caches 15 min in localStorage,
 * de-duped module-wide so many consumers share one fetch per TTL window.
 * Falls back to SITE.versionFallback on error or before the first fetch lands.
 */
export function useLatestRelease(): ReleaseState {
  const [state, setState] = useState<ReleaseState>(initialState)

  useEffect(() => {
    if (!state.loading) return
    let mounted = true
    fetchRelease()
      .then((value) => {
        if (!mounted) return
        setState({
          version: value.version,
          url: value.url,
          loading: false,
          fromCache: false,
          error: null,
        })
      })
      .catch((e) => {
        if (!mounted) return
        setState((s) => ({
          ...s,
          loading: false,
          error: e instanceof Error ? e : new Error(String(e)),
        }))
      })
    return () => {
      mounted = false
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  return state
}
