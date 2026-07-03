import { copyFileSync, existsSync } from "node:fs"
import path from "path"
import tailwindcss from "@tailwindcss/vite"
import react from "@vitejs/plugin-react"
import { defineConfig } from "vite"
import type { ViteReactSSGOptions } from "vite-react-ssg"

// React 19 hoists <title>/<meta>/<link> to the front of the streamed subtree,
// not into <head>. For each SSG page, lift the route's tags up into the head.
function relocateHead(html: string): string {
  const cut = html.indexOf("</head>")
  if (cut < 0) return html
  let head = html.slice(0, cut)
  let body = html.slice(cut)

  const lift = (re: RegExp) => {
    const m = body.match(re)
    if (!m) return
    body = body.replace(re, "")
    head = re.test(head) ? head.replace(re, m[0]) : head + m[0]
  }

  lift(/<title>[\s\S]*?<\/title>/)
  lift(/<meta\b[^>]*\bname="description"[^>]*>/)
  lift(/<link\b[^>]*\brel="canonical"[^>]*>/)

  return head + body
}

const ssgOptions: ViteReactSSGOptions = {
  script: "async",
  dirStyle: "nested",
  includedRoutes: () => ["/", "/about", "/blog", "/terminal", "/404"],
  onPageRendered: (_route, html) => relocateHead(html),
  // Also emit /404.html at the root — the convention most static hosts serve.
  onFinished: (dir) => {
    const nested = path.join(dir, "404", "index.html")
    if (existsSync(nested)) copyFileSync(nested, path.join(dir, "404.html"))
  },
}

// https://vite.dev/config/
export default defineConfig({
  plugins: [react(), tailwindcss()],
  resolve: {
    alias: {
      "@": path.resolve(__dirname, "./src"),
    },
  },
  ssgOptions,
})
