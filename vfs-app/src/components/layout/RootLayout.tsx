import { Outlet, ScrollRestoration } from "react-router-dom"
import { Topbar } from "./Topbar"
import { FilesystemFooter } from "./FilesystemFooter"

export function RootLayout() {
  return (
    <div className="min-h-svh flex flex-col bg-[var(--bg)] text-[var(--fg)]">
      <Topbar />
      <main className="flex-1">
        <Outlet />
      </main>
      <FilesystemFooter />
      <ScrollRestoration />
    </div>
  )
}
