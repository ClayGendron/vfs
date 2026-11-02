<script lang="ts">
  import { CaretLeft, CaretRight, Code, FileCsv, FileText, FolderSimple, PresentationChart } from "phosphor-svelte";
  import type { TreeNode } from "../api";
  import { appFor, workspace } from "../state.svelte";

  let { title, onopen, children }: { title: string; onopen: (path: string) => void; children?: import("svelte").Snippet } = $props();

  const kindIcons = { docs: FileText, sheets: FileCsv, slides: PresentationChart, code: Code } as const;
  const Icon = $derived(kindIcons[(workspace.app in kindIcons ? workspace.app : "docs") as keyof typeof kindIcons]);

  // One folder at a time, like a column browser: the open file's folder to begin with.
  let folder = $state("/");
  let followed = $state<string | null>(null);
  $effect(() => {
    const open = workspace.openPath;
    if (open && open !== followed) {
      followed = open;
      folder = parentOf(open);
    }
  });

  function parentOf(path: string): string {
    const i = path.lastIndexOf("/");
    return i <= 0 ? "/" : path.slice(0, i);
  }

  function find(node: TreeNode | null, path: string): TreeNode | null {
    if (!node) return null;
    if (node.path === path) return node;
    for (const child of node.children ?? []) {
      const hit = find(child, path);
      if (hit) return hit;
    }
    return null;
  }

  /** Whether a folder holds, anywhere beneath it, a file this app can open. */
  function holdsApp(node: TreeNode): boolean {
    return (node.children ?? []).some((c) => (c.kind === "directory" ? holdsApp(c) : appFor(c.path) === workspace.app));
  }

  function countApp(node: TreeNode): number {
    return (node.children ?? []).reduce(
      (n, c) => n + (c.kind === "directory" ? countApp(c) : appFor(c.path) === workspace.app ? 1 : 0),
      0,
    );
  }

  const node = $derived(find(workspace.tree, folder) ?? workspace.tree);
  const folders = $derived((node?.children ?? []).filter((c) => c.kind === "directory" && holdsApp(c)));
  const files = $derived((node?.children ?? []).filter((c) => c.kind === "file" && appFor(c.path) === workspace.app));
  const here = $derived(folder === "/" ? "Halyard" : folder.slice(folder.lastIndexOf("/") + 1));

  $effect(() => {
    if (workspace.tree && !find(workspace.tree, folder)) folder = "/";
  });

  function label(name: string): string {
    return name.replace(/\.(md|csv|rs)$/, "");
  }
</script>

<aside class="list" aria-label="{title} files">
  <div class="head">
    <span class="title">{title}</span>
    <span class="who">as {workspace.current?.name ?? "…"}</span>
  </div>
  {#if children}
    <div class="actions">{@render children()}</div>
  {/if}
  <div class="where">
    {#if folder !== "/"}
      <button type="button" class="up" onclick={() => (folder = parentOf(folder))} aria-label="Up to {parentOf(folder) === '/' ? 'Halyard' : parentOf(folder).slice(1)}">
        <CaretLeft size={14} />
      </button>
    {/if}
    <span class="here"><FolderSimple size={16} weight="fill" />{here}</span>
  </div>
  <div class="rows">
    {#each folders as sub (sub.path)}
      <button type="button" class="row dir" onclick={() => (folder = sub.path)}>
        <span class="glyph"><FolderSimple size={16} /></span>
        <span class="name">{sub.name}</span>
        <span class="meta">{countApp(sub)}</span>
        <span class="go"><CaretRight size={12} /></span>
      </button>
    {/each}
    {#each files as file (file.path)}
      <button
        type="button"
        class="row"
        class:active={workspace.openPath === file.path}
        aria-current={workspace.openPath === file.path ? "page" : undefined}
        onclick={() => onopen(file.path)}
      >
        <span class="glyph"><Icon size={16} /></span>
        <span class="name">{label(file.name)}</span>
      </button>
    {/each}
    {#if folders.length === 0 && files.length === 0 && !workspace.loading}
      <p class="empty">Nothing here that you can see.</p>
    {/if}
  </div>
</aside>

<style>
  .list {
    display: flex;
    flex-direction: column;
    min-height: 0;
    min-width: 0;
    width: 280px;
    border-right: var(--line-width) solid var(--sidebar-border);
    background: var(--sidebar);
    font-family: "Geist Variable", system-ui, sans-serif;
  }
  .head {
    display: flex;
    justify-content: space-between;
    align-items: baseline;
    padding: 0.85rem 1rem 0.5rem;
  }
  .title { font-size: 1rem; font-weight: 600; letter-spacing: -0.01em; }
  .who { color: var(--muted-foreground); font-size: 0.75rem; }
  .actions { padding: 0 1rem 0.5rem; }
  .where {
    display: flex;
    align-items: center;
    gap: 0.35rem;
    margin: 0 0.5rem;
    padding: 0.3rem 0.4rem;
    border-bottom: var(--line-width) solid var(--sidebar-border);
  }
  .up {
    display: inline-flex;
    padding: 0.25rem;
    border: 0;
    border-radius: var(--radius);
    background: transparent;
    color: var(--muted-foreground);
    cursor: pointer;
  }
  .up:hover { background: var(--sidebar-accent); color: var(--foreground); }
  .here {
    display: inline-flex;
    align-items: center;
    gap: 0.4rem;
    min-width: 0;
    color: var(--foreground);
    font-size: 0.85rem;
    font-weight: 600;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }
  .here :global(svg) { color: var(--primary); flex: none; }
  .rows { flex: 1; min-height: 0; overflow: auto; padding: 0.4rem 0.5rem 1rem; display: flex; flex-direction: column; gap: 1px; }
  .row {
    display: flex;
    align-items: center;
    gap: 0.5rem;
    width: 100%;
    min-width: 0;
    padding: 0.4rem 0.6rem;
    border: 0;
    border-radius: var(--radius);
    background: transparent;
    color: var(--sidebar-foreground);
    font: inherit;
    font-size: 0.875rem;
    text-align: left;
    cursor: pointer;
  }
  .glyph { display: inline-flex; flex: none; color: var(--muted-foreground); }
  .dir .glyph { color: var(--primary); }
  .name { min-width: 0; flex: 1; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
  .meta { color: var(--muted-foreground); font-size: 0.75rem; font-variant-numeric: tabular-nums; }
  .go { display: inline-flex; color: var(--muted-foreground); }
  .row:hover { background: var(--sidebar-accent); }
  .row.active { background: var(--raised); color: var(--foreground); font-weight: 500; box-shadow: 0 1px 2px var(--elevation-shadow); }
  .row.active .glyph { color: var(--primary); }
  .row:focus-visible, .up:focus-visible { outline: var(--focus-width) solid var(--ring); outline-offset: calc(-1 * var(--focus-width)); }
  .empty { padding: 0.5rem; color: var(--muted-foreground); font-size: 0.85rem; }
  @media (max-width: 900px) {
    .list { width: 100%; border-right: 0; }
  }
</style>
