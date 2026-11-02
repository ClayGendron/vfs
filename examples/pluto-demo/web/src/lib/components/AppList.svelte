<script lang="ts">
  import { filesFor, workspace } from "../state.svelte";

  let { title, onopen, children }: { title: string; onopen: (path: string) => void; children?: import("svelte").Snippet } = $props();

  const groups = $derived(filesFor(workspace.tree, workspace.app));

  function folderName(folder: string): string {
    return folder === "/" ? "Workspace" : folder.slice(1).replace(/\//g, " / ");
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
  <div class="groups">
    {#each groups as group (group.folder)}
      <section class="group">
        <h2 class="folder">{folderName(group.folder)}</h2>
        {#each group.files as file (file.path)}
          <button
            type="button"
            class="file"
            class:active={workspace.openPath === file.path}
            aria-current={workspace.openPath === file.path ? "page" : undefined}
            onclick={() => onopen(file.path)}
          >
            {file.name.replace(/\.(md|csv|rs)$/, "")}
          </button>
        {/each}
      </section>
    {/each}
    {#if groups.length === 0 && !workspace.loading}
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
  .groups { flex: 1; min-height: 0; overflow: auto; padding: 0 0.5rem 1rem; }
  .group { margin-top: 0.5rem; }
  .folder {
    margin: 0;
    padding: 0.35rem 0.5rem 0.2rem;
    color: var(--muted-foreground);
    font-size: 0.72rem;
    font-weight: 500;
  }
  .file {
    display: block;
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
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
    cursor: pointer;
  }
  .file:hover { background: var(--sidebar-accent); }
  .file.active { background: var(--raised); color: var(--foreground); font-weight: 500; box-shadow: 0 1px 2px var(--elevation-shadow); }
  .file:focus-visible { outline: var(--focus-width) solid var(--ring); outline-offset: calc(-1 * var(--focus-width)); }
  .empty { padding: 0.5rem; color: var(--muted-foreground); font-size: 0.85rem; }
  @media (max-width: 900px) {
    .list { width: 100%; border-right: 0; }
  }
</style>
