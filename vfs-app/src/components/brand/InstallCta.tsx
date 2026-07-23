import { useEffect, useRef, useState } from "react"
import { cn } from "@/lib/utils"
import { SITE } from "@/lib/site"

/**
 * Hero call-to-action row — read the docs, copy the install, jump to the
 * four-verb strip. The install button copies on click and confirms in place.
 */

const DOCS_URL = "https://vfs.dev/docs"

export function InstallCta({ className }: { className?: string }) {
  const [copied, setCopied] = useState(false)
  const timer = useRef<ReturnType<typeof setTimeout> | null>(null)

  // clear any pending reset on unmount so setCopied never fires detached
  useEffect(() => () => { if (timer.current) clearTimeout(timer.current) }, [])

  const copy = async () => {
    try {
      await navigator.clipboard.writeText(SITE.install.python)
      setCopied(true)
      if (timer.current) clearTimeout(timer.current)
      timer.current = setTimeout(() => setCopied(false), 1200)
    } catch {
      // clipboard denied — leave the label alone
    }
  }

  return (
    <div className={cn("vfs-cta", className)}>
      <a className="vfs-btn primary" href={DOCS_URL}>
        read the docs
        <span className="sig">→</span>
      </a>

      <button
        type="button"
        className={cn("vfs-btn", copied && "is-copied")}
        onClick={copy}
        title="Click to copy"
        aria-label={`Copy install command: ${SITE.install.python}`}
      >
        <span className="sig">$</span>
        <span>{SITE.install.python}</span>
        <span className="copy-status">{copied ? "copied" : ""}</span>
      </button>

      <a className="vfs-btn ghost" href="#four-verbs">
        read about the four verbs →
      </a>
    </div>
  )
}
