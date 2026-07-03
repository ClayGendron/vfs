import { cn } from "@/lib/utils"
import { SITE } from "@/lib/site"

/**
 * §4 lead visual — VFS as the protocol, not the database.
 *
 * An `/etc/fstab`-style map: each mountpoint binds a backend, run either
 * in-process or as an MCP server. The `mode` column makes the deployment
 * claim visible — same namespace whether VFS lives inside your app or
 * behind the wire.
 */

const MOUNTS = SITE.mounts.filter((m) => m.mountpoint)

export function MountMap() {
  return (
    <div className="vfs-mounts" role="table" aria-label="VFS mount table">
      <div className="vfs-mounts-head" role="row">
        <div role="columnheader">mountpoint</div>
        <div role="columnheader">backend</div>
        <div role="columnheader">mode</div>
      </div>
      {MOUNTS.map((m) => (
        <div className="vfs-mounts-row" role="row" key={m.mountpoint}>
          <div className="vfs-mounts-mount" role="cell">
            <span className="vfs-mounts-arrow" aria-hidden="true">
              →
            </span>
            <span>{m.mountpoint}</span>
          </div>
          <div className="vfs-mounts-backend" role="cell">
            {m.backend}
          </div>
          <div className="vfs-mounts-modecell" role="cell">
            <span
              className={cn("vfs-mounts-tag", m.mode === "mcp" && "is-mcp")}
            >
              {m.mode}
            </span>
          </div>
        </div>
      ))}
    </div>
  )
}
