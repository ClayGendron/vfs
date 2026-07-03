/**
 * Route-level error boundary. Rendered by the router's `errorElement` whenever
 * a route (or the layout) throws during render or a loader rejects — replacing
 * React Router's unstyled default fallback with the brand's terminal aesthetic.
 *
 * Shows the real message only in dev; production gets a calm, generic line.
 */

import { Link, isRouteErrorResponse, useRouteError } from "react-router-dom"
import { Seo } from "@/components/Seo"
import { routeMeta } from "@/lib/site"

function describe(error: unknown): { status: string; detail: string } {
  if (isRouteErrorResponse(error)) {
    return {
      status: `${error.status} ${error.statusText}`.trim(),
      detail: typeof error.data === "string" ? error.data : "route error",
    }
  }
  if (error instanceof Error) {
    return { status: "uncaught exception", detail: error.message }
  }
  return { status: "uncaught exception", detail: "an unknown error occurred" }
}

export function RouteError() {
  const error = useRouteError()
  const { status, detail } = describe(error)
  const showDetail = import.meta.env.DEV

  return (
    <main className="vfs-404">
      <Seo {...routeMeta.error} />
      <div className="cap">error · something threw</div>
      <h1 className="title">/error</h1>

      <div className="vfs-404-term">
        <div className="line err">vfs: {status}</div>
        {showDetail && <div className="line out">{detail}</div>}
        <div className="line hint">
          reload to retry, or cd home to start over
        </div>
      </div>

      <div className="vfs-linkline" style={{ marginTop: 28 }}>
        <button
          type="button"
          onClick={() => window.location.reload()}
          className="accent"
        >
          reload →
        </button>
        <Link to="/">cd home →</Link>
      </div>
    </main>
  )
}
