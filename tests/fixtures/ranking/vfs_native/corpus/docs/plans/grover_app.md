# GroverApp Implementation Plan

## Context

Grover has no developer tooling for visually inspecting filesystem contents. We're building `GroverApp`: a React + FastAPI developer debugging tool. The React frontend is pre-built and ships inside the pip package — end users do `pip install grover[app]` and never touch Node/bun.

## Target API

```python
from grover.app import GroverApp
from grover import Grover, GroverAsync
from grover.backends import DatabaseFileSystem

g = GroverAsync()
await g.add_mount("docs", DatabaseFileSystem(engine=e1))
await g.add_mount("code", DatabaseFileSystem(engine=e2))

app = GroverApp(g)
app.serve()  # blocks, opens browser at localhost:3900
```

Sync wrapper also works (extracts `._async`):
```python
g = Grover()
g.add_mount("docs", DatabaseFileSystem(engine=e1))
GroverApp(g).serve()
```

**No `.serve()` on Grover/GroverAsync** — only `GroverApp.serve()`.

## V1 Scope (read-only)

1. Mount sidebar — mounted paths with filesystem type
2. File tree — virtualized, keyboard-navigable (react-arborist)
3. Code viewer — Monaco (read-only), minimap, line numbers, syntax highlighting
4. File info panel — metadata card
5. Command palette — Cmd+K search with glob/grep (shadcn Command)
6. Resizable panels — drag to resize (shadcn Resizable)

---

## Architecture

### Pre-built React shipped in pip (Dagster/Gradio pattern)

```
Dev build flow:
  frontend/src/*.tsx  →  bun run build  →  src/grover/app/static/  →  hatch build  →  wheel

End user:
  pip install grover[app]  →  GroverApp(g).serve()  →  browser opens
```

Static files live at `src/grover/app/static/` — gitignored but included in the wheel via hatchling `artifacts`.

---

## Design System (from Grover Brand Lookbook)

### Colors — neutral dark base, brand accents

The lookbook uses a forest green palette for marketing. For the app (per user feedback), we use **neutral dark backgrounds** with green only as accent/border tint.

**Brand hex → shadcn CSS variables (oklch):**

```css
.dark {
  /* Backgrounds — bark/stone neutrals, NOT green */
  --background: oklch(0.145 0.005 85);        /* #1A1A18 bark */
  --foreground: oklch(0.95 0.01 145);          /* #F0FAF4 daylight */
  --card: oklch(0.195 0.005 85);               /* #2A2A27 stone */
  --card-foreground: oklch(0.95 0.01 145);
  --popover: oklch(0.195 0.005 85);
  --popover-foreground: oklch(0.95 0.01 145);

  /* Primary — ember (action, selection) */
  --primary: oklch(0.65 0.17 35);              /* #E8734A ember */
  --primary-foreground: oklch(0.98 0 0);

  /* Secondary — elevated surface */
  --secondary: oklch(0.24 0.005 85);           /* #333330 elevated */
  --secondary-foreground: oklch(0.95 0.01 145);

  /* Muted — dust tones */
  --muted: oklch(0.24 0.005 85);
  --muted-foreground: oklch(0.58 0.005 85);    /* #8A8A82 dust */

  /* Accent — hover/active states */
  --accent: oklch(0.28 0.01 85);
  --accent-foreground: oklch(0.95 0.01 145);

  /* Destructive */
  --destructive: oklch(0.55 0.20 25);
  --destructive-foreground: oklch(0.95 0 0);

  /* Borders — subtle green tint from brand */
  --border: oklch(0.35 0.02 155);              /* rgba(122,174,142,0.12) equivalent */
  --input: oklch(0.30 0.01 155);
  --ring: oklch(0.65 0.17 35);                 /* ember focus ring */

  /* Sidebar — slightly different surface */
  --sidebar-background: oklch(0.17 0.005 85);
  --sidebar-foreground: oklch(0.85 0.01 145);
  --sidebar-primary: oklch(0.65 0.17 35);      /* ember */
  --sidebar-primary-foreground: oklch(0.98 0 0);
  --sidebar-accent: oklch(0.22 0.01 85);
  --sidebar-accent-foreground: oklch(0.95 0.01 145);
  --sidebar-border: oklch(0.30 0.02 155);
  --sidebar-ring: oklch(0.65 0.17 35);

  /* Chart colors — brand accents */
  --chart-1: oklch(0.65 0.17 35);              /* ember */
  --chart-2: oklch(0.55 0.15 300);             /* violet #8B6CC1 */
  --chart-3: oklch(0.70 0.14 200);             /* cyan #4ABCE8 */
  --chart-4: oklch(0.75 0.15 85);              /* amber #E8B44A */
  --chart-5: oklch(0.50 0.12 155);             /* fern #4A7C5C */
}
```

### Typography (from lookbook)

```css
@theme {
  --font-display: 'DM Serif Display', Georgia, serif;
  --font-sans: 'Instrument Sans', -apple-system, sans-serif;
  --font-mono: 'JetBrains Mono', 'Fira Code', monospace;
}
```

Load via Google Fonts in `index.html`.

---

## Tech Stack

### Frontend (dev-time, ships as static files)

| Library | Purpose | Notes |
|---|---|---|
| React 19 | UI framework | |
| Vite | Build tool | Outputs self-contained static files |
| shadcn/ui | Component library | Base UI primitives (NOT Radix) — see init command below |
| Tailwind CSS v4 | Styling | CSS-first `@theme`, oklch colors |
| Monaco Editor | Code viewer | `@monaco-editor/react`, custom `grover-dark` theme |
| react-arborist | File tree | Virtualized, keyboard nav, custom nodes |
| TanStack Query | Data fetching | Caching, loading states |
| lucide-react | Icons | Already shadcn's default icon library |

**shadcn/ui uses Base UI (`@base-ui/react`) as its headless primitive layer, NOT Radix UI.** The `--base base` flag in the init command ensures all components use Base UI primitives. The shadcn CLI handles installing the correct dependencies automatically when adding components — no manual `@base-ui/react` or `@radix-ui/*` installs needed. The 5 available Base UI visual styles are: `base-vega`, `base-nova`, `base-maia`, `base-lyra`, `base-mira`.

**Init + add components:**
```bash
bunx --bun shadcn@latest init --preset b0 --base base --template vite
bunx --bun shadcn@latest add command card badge input scroll-area separator tooltip resizable sidebar tabs button skeleton
```

Note: `resizable` wraps `react-resizable-panels`, `command` wraps `cmdk` — shadcn installs these as dependencies automatically.

### Backend (pip dependency)

```toml
app = ["fastapi>=0.115", "uvicorn[standard]>=0.34"]
```

---

## File Structure

### Python (ships in pip)

```
src/grover/app/
    __init__.py          # GroverApp class
    server.py            # FastAPI app + SPAStaticFiles + uvicorn
    api.py               # API routes (/api/mounts, /api/tree, /api/read, etc.)
    tree.py              # Flat-to-hierarchical conversion (pure logic, testable)
    static/              # Pre-built React (gitignored, in wheel via artifacts)
```

### Frontend (dev-time, NOT in pip)

```
frontend/
    package.json
    bun.lock
    vite.config.ts
    tsconfig.json
    components.json                # shadcn config
    index.html
    src/
        main.tsx                   # Entry, QueryClient, ThemeProvider
        App.tsx                    # Root layout
        app.css                    # Tailwind + @theme + shadcn vars
        lib/
            api.ts                 # Fetch wrapper + types
            utils.ts               # cn() helper (shadcn)
        hooks/
            use-mounts.ts          # GET /api/mounts
            use-file-tree.ts       # GET /api/tree/{path}
            use-file-content.ts    # GET /api/read/{path}
            use-search.ts          # GET /api/glob, /api/grep
        components/
            ui/                    # shadcn primitives (auto-generated)
            app-sidebar.tsx        # shadcn Sidebar: mounts + file tree
            file-tree.tsx          # react-arborist wrapper
            file-tree-node.tsx     # Custom node renderer
            code-viewer.tsx        # Monaco wrapper + tab bar
            file-info.tsx          # Right panel metadata (shadcn Card)
            command-palette.tsx    # shadcn Command: Cmd+K search
            explorer-layout.tsx    # shadcn Resizable three-panel layout
```

---

## Detailed Design

### Python: `__init__.py`

```python
class GroverApp:
    def __init__(
        self,
        grover: GroverFileSystem,
        *,
        port: int = 3900,
        host: str = "127.0.0.1",
        open_browser: bool = True,
    ) -> None:
        from grover.client import Grover
        self._grover = grover._async if isinstance(grover, Grover) else grover
        self._port = port
        self._host = host
        self._open_browser = open_browser

    def serve(self) -> None:
        import uvicorn, webbrowser, threading
        from grover.app.server import create_app
        app = create_app(self._grover)
        if self._open_browser:
            url = f"http://{self._host}:{self._port}"
            threading.Timer(1.0, webbrowser.open, args=[url]).start()
        uvicorn.run(app, host=self._host, port=self._port, log_level="warning")
```

### Python: `server.py`

```python
STATIC_DIR = Path(__file__).parent / "static"

class SPAStaticFiles(StaticFiles):
    """React SPA fallback — non-API 404s serve index.html."""
    async def get_response(self, path, scope):
        try:
            return await super().get_response(path, scope)
        except (HTTPException, StarletteHTTPException) as ex:
            if ex.status_code == 404:
                return await super().get_response("index.html", scope)
            raise

def create_app(grover) -> FastAPI:
    app = FastAPI(title="Grover", docs_url="/api/docs")
    app.state.grover = grover
    from grover.app.api import router
    app.include_router(router, prefix="/api")  # API first
    if STATIC_DIR.exists():
        app.mount("/", SPAStaticFiles(directory=str(STATIC_DIR), html=True))  # SPA last
    return app
```

### Python: `api.py`

Routes: `GET /api/mounts`, `GET /api/tree/{path}`, `GET /api/read/{path}`, `GET /api/glob?pattern=`, `GET /api/grep?pattern=`

All routes access `request.app.state.grover` (the GroverAsync instance), call the corresponding async method, and return JSON-serializable dicts from Candidate fields.

### Python: `tree.py`

Pure logic function `build_tree_nodes(candidates) -> list[dict]`. Converts Grover's flat sorted `tree()` output into nested dicts with `id`, `name`, `isDirectory`, `children`, `size` for react-arborist. No web dependencies — independently testable.

### Frontend: `explorer-layout.tsx`

Three-panel layout using shadcn Resizable:

```tsx
<ResizablePanelGroup direction="horizontal" className="h-[calc(100vh-48px)]">
  <ResizablePanel defaultSize={20} minSize={15} maxSize={35}>
    <AppSidebar />  {/* shadcn Sidebar with file tree inside */}
  </ResizablePanel>
  <ResizableHandle withHandle />
  <ResizablePanel defaultSize={55} minSize={30}>
    <CodeViewer />  {/* Monaco, read-only */}
  </ResizablePanel>
  <ResizableHandle withHandle />
  <ResizablePanel defaultSize={25} minSize={15} collapsible collapsedSize={0}>
    <FileInfo />    {/* shadcn Card with metadata */}
  </ResizablePanel>
</ResizablePanelGroup>
```

### Frontend: `code-viewer.tsx`

Monaco editor with custom grover-dark theme:

```tsx
<Editor
  height="100%"
  language={detectLanguage(filename)}
  value={content}
  theme="grover-dark"
  options={{
    readOnly: true, domReadOnly: true,
    minimap: { enabled: true },
    fontSize: 13,
    fontFamily: "'JetBrains Mono', monospace",
    automaticLayout: true,  // CRITICAL for resizable panels
    scrollBeyondLastLine: false,
  }}
  loading={<Skeleton className="h-full w-full" />}
/>
```

Custom Monaco theme defined in `onMount` to match brand colors (bark background, mint/violet/amber syntax tokens).

### Frontend: `file-tree.tsx`

react-arborist tree styled with Tailwind + shadcn CSS variables:

```tsx
<Tree data={data} width="100%" rowHeight={28} openByDefault={false}>
  {({ node, style, dragHandle }) => (
    <div ref={dragHandle} style={style}
         className={cn("flex items-center gap-1.5 px-2 py-0.5 text-sm rounded-sm",
                       "hover:bg-accent hover:text-accent-foreground",
                       node.isSelected && "bg-accent text-accent-foreground")}>
      {/* chevron + icon + name + size badge */}
    </div>
  )}
</Tree>
```

### Frontend: `command-palette.tsx`

shadcn Command (wraps cmdk) — Cmd+K opens, search dispatches to `/api/glob` or `/api/grep`:

```tsx
<CommandDialog open={open} onOpenChange={setOpen}>
  <CommandInput placeholder="Search files..." />
  <CommandList>
    <CommandGroup heading="Files">
      {results.map(r => (
        <CommandItem key={r.path} onSelect={() => selectFile(r.path)}>
          <FileIcon className="mr-2 h-4 w-4" />
          {r.path}
          <Badge variant="outline" className="ml-auto">{r.score}</Badge>
        </CommandItem>
      ))}
    </CommandGroup>
  </CommandList>
</CommandDialog>
```

---

## Configuration Changes

### `pyproject.toml`

```toml
[tool.hatch.build]
artifacts = ["src/grover/app/static/"]

[project.optional-dependencies]
app = ["fastapi>=0.115", "uvicorn[standard]>=0.34"]
# Update 'all' to include 'app'
```

### `.gitignore` addition

```
src/grover/app/static/
```

### `frontend/vite.config.ts`

```typescript
export default defineConfig({
  plugins: [react(), tailwindcss()],
  base: "./",
  build: {
    outDir: "../src/grover/app/static",
    emptyDir: true,
  },
  server: {
    port: 5173,
    proxy: { "/api": { target: "http://localhost:3900" } },
  },
});
```

---

## Dev Workflow

```bash
# Terminal 1: FastAPI backend
python dev_server.py  # :3900

# Terminal 2: Vite dev server (hot reload)
cd frontend && bun run dev  # :5173, proxies /api → :3900
```

### Release build

```bash
cd frontend && bun install && bun run build   # → src/grover/app/static/
hatch build                                     # → dist/grover-*.whl
```

---

## Implementation Order

### Phase 1: Python backend
1. Add `app` extra + `artifacts` to `pyproject.toml`
2. Create `src/grover/app/__init__.py` — GroverApp
3. Create `src/grover/app/server.py` — FastAPI + SPAStaticFiles
4. Create `src/grover/app/api.py` — routes (mounts, tree, read, glob, grep)
5. Create `src/grover/app/tree.py` — flat-to-hierarchical
6. Tests: `test_app_tree.py`, `test_app_api.py`, `test_app.py`

### Phase 2: Frontend scaffold
7. Init frontend with Base UI (not Radix): `bunx --bun shadcn@latest init --preset b0 --base base --template vite`
8. Add shadcn components (CLI auto-installs Base UI deps): `bunx --bun shadcn@latest add command card badge input scroll-area separator tooltip resizable sidebar tabs button skeleton`
9. Install non-shadcn deps: `bun add react-arborist @monaco-editor/react @tanstack/react-query`
10. Set up brand colors in `app.css` (oklch dark theme vars)
11. Load Google Fonts (DM Serif Display, Instrument Sans, JetBrains Mono)

### Phase 3: Core UI
12. `explorer-layout.tsx` — three-panel Resizable
13. `app-sidebar.tsx` — shadcn Sidebar with mount list
14. `file-tree.tsx` + `file-tree-node.tsx` — react-arborist
15. `code-viewer.tsx` — Monaco with grover-dark theme
16. `file-info.tsx` — shadcn Card with metadata

### Phase 4: Search + wiring
17. `command-palette.tsx` — Cmd+K with glob/grep
18. TanStack Query hooks (use-mounts, use-file-tree, use-file-content, use-search)
19. Wire selection flow: tree click → content load → info update
20. Build and test full `pip install grover[app]` flow

## Testing

- `tests/test_app_tree.py` — pure logic (no web deps)
- `tests/test_app_api.py` — FastAPI routes with `httpx.AsyncClient`
- `tests/test_app.py` — GroverApp construction

## Verification

1. `pip install -e ".[app]"` + `cd frontend && bun run build`
2. Run test script: write sample files → `GroverApp(g).serve()`
3. Browser at `localhost:3900`: sidebar with mounts, expandable tree
4. Click `.py` file → Monaco with syntax highlighting + minimap
5. Right panel shows size, lines, timestamps
6. Cmd+K → type `*.py` → glob results, click to navigate
7. Drag panel borders → sizes persist
8. `uv run pytest tests/test_app_tree.py tests/test_app_api.py tests/test_app.py`
