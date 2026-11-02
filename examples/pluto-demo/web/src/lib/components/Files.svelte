<script lang="ts">
  import { CaretRight, Code, FileCsv, FileText, FolderSimple, HouseSimple, PresentationChart, Rows, SquaresFour } from "phosphor-svelte";
  import type { TreeNode } from "../api";
  import { appFor, workspace } from "../state.svelte";
  import FileTree from "./FileTree.svelte";

  let { onopen }: { onopen: (path: string) => void } = $props();

  type View = "icons" | "list";
  let view = $state<View>("icons");
  let folder = $state("/");
  let selected = $state<string | null>(null);

  const kindIcons = { docs: FileText, sheets: FileCsv, slides: PresentationChart, code: Code } as const;
  const kindNames = { docs: "Document", sheets: "Sheet", slides: "Deck", code: "Code" } as const;

  function find(node: TreeNode | null, path: string): TreeNode | null {
    if (!node) return null;
    if (node.path === path) return node;
    for (const child of node.children ?? []) {
      const hit = find(child, path);
      if (hit) return hit;
    }
    return null;
  }

  // The folder being looked at; when the principal changes and it vanishes, go home.
  const node = $derived(find(workspace.tree, folder) ?? workspace.tree);
  const entries = $derived(node?.children ?? []);
  const crumbs = $derived(
    folder === "/" ? [] : folder.slice(1).split("/").map((name, i, all) => ({ name, path: "/" + all.slice(0, i + 1).join("/") })),
  );

  $effect(() => {
    if (workspace.tree && !find(workspace.tree, folder)) folder = "/";
  });

  function go(path: string) {
    folder = path;
    selected = null;
  }

  function open(entry: TreeNode) {
    if (entry.kind === "directory") go(entry.path);
    else onopen(entry.path);
  }

  function iconFor(entry: TreeNode) {
    if (entry.kind === "directory") return FolderSimple;
    return kindIcons[(appFor(entry.path) ?? "docs") as keyof typeof kindIcons];
  }

  function kindOf(entry: TreeNode): string {
    if (entry.kind === "directory") return `${entry.children?.length ?? 0} items`;
    return kindNames[(appFor(entry.path) ?? "docs") as keyof typeof kindNames];
  }

  function onKey(e: KeyboardEvent, entry: TreeNode) {
    if (e.key === "Enter") open(entry);
  }
</script>

<section class="files" aria-label="Files">
  <header class="bar">
    <nav class="crumbs" aria-label="Folder path">
      <button type="button" class="crumb" class:current={folder === "/"} onclick={() => go("/")}>
        <HouseSimple size={16} weight={folder === "/" ? "fill" : "regular"} />
        <span>Halyard</span>
      </button>
      {#each crumbs as crumb (crumb.path)}
        <span class="sep" aria-hidden="true"><CaretRight size={12} /></span>
        <button type="button" class="crumb" class:current={crumb.path === folder} onclick={() => go(crumb.path)}>{crumb.name}</button>
      {/each}
    </nav>
    <div class="views" role="group" aria-label="View">
      <button type="button" class="view" class:active={view === "icons"} aria-pressed={view === "icons"} title="Icons" onclick={() => (view = "icons")}>
        <SquaresFour size={18} weight={view === "icons" ? "fill" : "regular"} />
      </button>
      <button type="button" class="view" class:active={view === "list"} aria-pressed={view === "list"} title="List" onclick={() => (view = "list")}>
        <Rows size={18} weight={view === "list" ? "fill" : "regular"} />
      </button>
    </div>
  </header>

  {#if view === "icons"}
    <div class="grid" role="listbox" aria-label="Items in {folder}" tabindex="-1">
      {#each entries as entry (entry.path)}
        {@const Icon = iconFor(entry)}
        <button
          type="button"
          class="item"
          class:selected={selected === entry.path}
          class:folder={entry.kind === "directory"}
          role="option"
          aria-selected={selected === entry.path}
          onclick={() => (selected = entry.path)}
          ondblclick={() => open(entry)}
          onkeydown={(e) => onKey(e, entry)}
        >
          <span class="glyph"><Icon size={52} weight={entry.kind === "directory" ? "fill" : "duotone"} /></span>
          <span class="name">{entry.name}</span>
          <span class="kind">{kindOf(entry)}</span>
        </button>
      {/each}
      {#if entries.length === 0 && !workspace.loading}
        <p class="empty">Nothing here that you can see.</p>
      {/if}
    </div>
  {:else}
    <div class="tree">
      {#if node}
        <FileTree {node} {onopen} />
      {:else if !workspace.loading}
        <p class="empty">Nothing here that you can see.</p>
      {/if}
    </div>
  {/if}
</section>

<style>
  .files {
    display: flex;
    flex-direction: column;
    height: 100%;
    min-width: 0;
    overflow: hidden;
  }
  .bar {
    display: flex;
    align-items: center;
    gap: 0.75rem;
    padding: 0.6rem 1.25rem;
    border-bottom: var(--line-width) solid var(--border);
    background: var(--card);
  }
  .crumbs { display: flex; align-items: center; gap: 0.2rem; min-width: 0; overflow: hidden; }
  .crumb {
    display: inline-flex;
    align-items: center;
    gap: 0.35rem;
    padding: 0.3rem 0.5rem;
    border: 0;
    border-radius: var(--radius);
    background: transparent;
    color: var(--muted-foreground);
    font: inherit;
    font-size: 0.9rem;
    cursor: pointer;
    white-space: nowrap;
  }
  .crumb:hover { background: var(--accent); color: var(--foreground); }
  .crumb.current { color: var(--foreground); font-weight: 600; }
  .crumb:focus-visible, .view:focus-visible, .item:focus-visible {
    outline: var(--focus-width) solid var(--ring);
    outline-offset: var(--focus-offset);
  }
  .sep { display: inline-flex; color: var(--muted-foreground); }
  .views {
    margin-left: auto;
    display: inline-flex;
    padding: 2px;
    border-radius: var(--radius);
    background: var(--muted);
  }
  .view {
    display: inline-flex;
    padding: 0.3rem 0.5rem;
    border: 0;
    border-radius: calc(var(--radius) - 2px);
    background: transparent;
    color: var(--muted-foreground);
    cursor: pointer;
  }
  .view.active { background: var(--card); color: var(--foreground); box-shadow: 0 1px 2px var(--elevation-shadow); }
  .grid {
    display: grid;
    grid-template-columns: repeat(auto-fill, minmax(7.5rem, 1fr));
    gap: 0.5rem 0.25rem;
    align-content: start;
    flex: 1;
    min-height: 0;
    padding: 1.25rem;
    overflow: auto;
  }
  .item {
    display: flex;
    flex-direction: column;
    align-items: center;
    gap: 0.2rem;
    padding: 0.75rem 0.5rem 0.6rem;
    border: 0;
    border-radius: calc(var(--radius) * 1.5);
    background: transparent;
    color: var(--foreground);
    font: inherit;
    cursor: default;
    user-select: none;
  }
  .item:hover { background: var(--accent); }
  .item.selected { background: color-mix(in srgb, var(--primary) 14%, transparent); }
  .item.selected .name { background: var(--primary); color: var(--primary-foreground); }
  .glyph { display: inline-flex; color: var(--muted-foreground); }
  .item.folder .glyph { color: var(--primary); }
  .name {
    max-width: 100%;
    padding: 0.1rem 0.4rem;
    border-radius: 0.3rem;
    font-size: 0.8rem;
    line-height: 1.3;
    text-align: center;
    overflow-wrap: anywhere;
  }
  .kind { color: var(--muted-foreground); font-size: 0.7rem; }
  .tree {
    flex: 1;
    min-height: 0;
    padding: 0.75rem 1rem;
    overflow: auto;
  }
  .empty { grid-column: 1 / -1; margin: 0; padding: 1rem; color: var(--muted-foreground); font-size: 0.9rem; }
  @media (max-width: 900px) {
    .bar { padding: 0.5rem 0.75rem; }
    .grid { grid-template-columns: repeat(auto-fill, minmax(6rem, 1fr)); padding: 0.75rem; }
  }
</style>
