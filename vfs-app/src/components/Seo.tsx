/**
 * Per-route document head. React 19 hoists <title>, <meta>, and <link> rendered
 * anywhere in the tree into <head>, so a route just renders <Seo {...meta} />.
 *
 *   <Seo {...routeMeta.about} />
 */

import type { RouteMeta } from "@/lib/site"

export function Seo({ title, description, canonical }: RouteMeta) {
  return (
    <>
      <title>{title}</title>
      <meta name="description" content={description} />
      {canonical ? <link rel="canonical" href={canonical} /> : null}
    </>
  )
}
