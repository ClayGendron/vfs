# The probe behind the docs app memo

The scripts and recorded outputs [the docs app memo](../../2026-11-14-a-svelte-app-built-from-the-design-system-renders-the-docs-and-the-api-export-as-static-pages.md) cites, written for the state check of [the docs site spec](../../../specifications/active/2026-11-14-the-docs-site-is-a-svelte-app-in-this-repository-built-from-the-design-system.md) and run on 2026-11-14 in a scratch folder outside this checkout.

| File | What it is |
|---|---|
| `experiments/results.txt` | Every command of the probe and what it printed. |
| `experiments/export_api.py` | The trial export: Griffe reads `src/vfs` without importing it and writes the public API as JSON. |
| `experiments/app/docs.server.ts` | The trial page loader: Markdown to tokens, links to routes, headings to anchors, code highlighted at build time. |
| `experiments/app/Markdown.svelte` | The trial renderer: one token, one design-system component. |
| `experiments/app/page.server.ts`, `page.svelte` | The trial route for a documentation page. |
| `experiments/app/api-page.server.ts`, `api-page.svelte` | The trial route for one exported name. |

The probe's code is a trial and is not the design. The design-system components it installed are not copied here.
