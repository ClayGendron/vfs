# docs-app

The vfs docs site: a static Svelte app that draws the Markdown pages of `../documentation/` and the public API, read from the docstrings, with the Pluto Systems design system.

## Commands

Run these from the repository root. They need `uv` and `bun`.

```bash
scripts/docs.sh dev      # preview locally; a changed page reloads, a changed docstring needs the command run again
scripts/docs.sh build    # the static site, in docs-app/build
scripts/docs.sh check    # build, type check and tests: run it before committing a docs change
scripts/docs.sh export   # the API export alone, docs-app/src/lib/generated/api.json
```

## Where things are

| Path | What it is |
|---|---|
| `../documentation/` | The pages, as Markdown, and `navigation.json`, which lists them. |
| `../scripts/docs_export.py` | Reads the public API from `../src/vfs` and writes the export. The export is never stored. |
| `src/lib/docs/` | The only app code written here: the page loader, the renderer, the layout pieces and the prose styles. |
| `src/lib/` (everything else) | Design-system items, installed as source. They are not edited here. |
| `src/routes/` | The landing page, the not-found page, and one route that serves every Markdown page. |
| `tests/build.test.ts` | What the build writes and what it refuses, run by `bun test`. |
| `tests/layout.spec.ts` | The layout rules that need a browser, run by Playwright in Chromium. |

## The design system

The items come from the design system's registry at release tag **`v0.11.0`**. An app installs an item and owns its source, so the files are in this folder, and they stay as installed: a change an item needs is made in the design system and installed from its next tag.

The first install, which also writes the theme into `src/app.css`:

```bash
cd docs-app
REGISTRY_URL=https://raw.githubusercontent.com/plutosystemsco/design-system/v0.11.0/static/r \
  bunx --bun shadcn-svelte@1.7.1 add theme sidebar breadcrumb code-block table alert tabs collapsible button separator -y -o
```

To move to a later tag, run the same command with the new tag and read the diff. Leave out `-o` to be asked before a file is overwritten.

The browser tests need Chromium once: `bunx --bun playwright install chromium`.

## What a page may hold

A page is Markdown: headings, paragraphs, fenced code, tables, lists, block quotes, links, and local SVG images, which are placed inline. Anything else, raw HTML included, stops the build with the page named. A page has exactly one first-level heading, which is its title, and it must be listed once in `navigation.json`.

A line of the form `::: vfs.Name`, alone in its own paragraph, pulls an exported name into a page: its signature, its docstring and its public members. Every name `vfs.__all__` exports must be pulled into exactly one page.
