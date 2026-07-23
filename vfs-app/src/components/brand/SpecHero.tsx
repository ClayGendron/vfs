import type { ReactNode } from "react"
import { InstallCta } from "./InstallCta"

/**
 * Centered spec-sheet hero — status eyebrow, headline, lede, call to action.
 *
 * The verb strip sits directly under it on the landing page, so the hero
 * stays short: one claim, one paragraph, three ways in.
 */
export function SpecHero({
  eyebrow,
  headline,
  lede,
}: {
  eyebrow?: ReactNode
  headline: ReactNode
  lede: ReactNode
}) {
  return (
    <section className="vfs-hero">
      {eyebrow && (
        <div className="vfs-hero-eyebrow">
          <span className="dot" aria-hidden="true" />
          {eyebrow}
        </div>
      )}
      <h1 className="vfs-hero-headline">{headline}</h1>
      <p className="vfs-hero-lede">{lede}</p>
      <InstallCta />
    </section>
  )
}
