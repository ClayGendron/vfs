# vfs-app

Marketing and landing site for **vfs** — the virtual file system for agents —
served at [vfs.dev](https://vfs.dev). A small single-page app that explains what
vfs is and lets visitors try a fake, in-browser vfs REPL.

## Routes

- `/` — home: what vfs is, spec strip, integrations, positioning.
- `/about` — thesis, lineage, project status.
- `/blog` — notes from the spec.
- `/terminal` — a simulated in-browser vfs REPL (no backend; nothing is sent
  anywhere).

Unmatched paths render a branded 404, and render-time errors render a branded
error page.

## Stack

- [Vite 7](https://vite.dev) + [React 19](https://react.dev) + TypeScript
- [react-router 7](https://reactrouter.com) for client-side routing
- [Tailwind v4](https://tailwindcss.com) via `@tailwindcss/vite`
- shadcn-style UI primitives built on [`@base-ui/react`](https://base-ui.com)
- [bun](https://bun.sh) as package manager and script runner

## Develop

```bash
bun install        # install dependencies (uses bun.lock)
bun run dev        # start the Vite dev server
bun run lint       # eslint .
bun run typecheck  # tsc --noEmit
bun run test       # vitest run
bun run build      # tsc -b && vite build
bun run preview    # serve the production build locally
bun run format     # prettier --write over ts/tsx
```

## Source layout

- `src/routes/` — one component per route (`Home`, `About`, `Blog`, `Terminal`,
  `NotFound`, `RouteError`).
- `src/components/brand/` — the visual identity components (hero, spec strip,
  integrations grid, terminal tape, and the field/tree visualizations).
- `src/components/layout/` — shell chrome: `RootLayout`, `Topbar`,
  `FilesystemFooter`, `ThemeToggle`.
- `src/lib/site.ts` — the single source of site copy and data (name, tagline,
  metrics, integrations, positioning, directory listing).
- `src/styles/brand.css` — the ported design system (tokens, fonts, brand
  utilities).

## Design history

Design & brand handoff and the strategy memos behind this site live in
[`context/product/vfs-app/`](../context/product/vfs-app/).

## CI

[`.github/workflows/vfs-app.yml`](../.github/workflows/vfs-app.yml) runs lint,
typecheck, and build with bun on every push to `main` and pull request that
touches `vfs-app/`.
