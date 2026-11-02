<script lang="ts">
  import { slide } from "svelte/transition";
  import type { TreeNode } from "../api";
  import { Code, FileCsv, FileText, FolderSimple, PresentationChart } from "phosphor-svelte";
  import { appFor, workspace } from "../state.svelte";
  import FileTree from "./FileTree.svelte";

  let {
    node,
    depth = 0,
    onopen,
  }: { node: TreeNode; depth?: number; onopen: (path: string) => void } = $props();

  // svelte-ignore state_referenced_locally
  let open = $state(depth < 2);
  const reduced =
    typeof window !== "undefined" && window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  const dur = reduced ? 0 : 180;
  const kindIcons = { docs: FileText, sheets: FileCsv, slides: PresentationChart, code: Code } as const;
  const Icon = $derived(node.kind === "directory" ? FolderSimple : kindIcons[(appFor(node.path) ?? "docs") as keyof typeof kindIcons]);
</script>

{#if node.kind === "directory"}
  {#if depth > 0}
    <button
      type="button"
      class="row dir"
      style:padding-left="{0.5 + depth * 0.85}rem"
      aria-expanded={open}
      onclick={() => (open = !open)}
    >
      <svg class="chev" class:open viewBox="0 0 12 12" width="10" height="10" aria-hidden="true"><path d="M4 2l4 4-4 4" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"/></svg>
      <span class="kind"><Icon size={16} weight={open ? "fill" : "regular"} /></span>
      <span class="name">{node.name}</span>
    </button>
  {/if}
  {#if open}
    <div class="children" transition:slide={{ duration: dur }}>
      {#each node.children ?? [] as child (child.path)}
        <div transition:slide={{ duration: dur }}>
          <FileTree node={child} depth={depth + 1} {onopen} />
        </div>
      {/each}
    </div>
  {/if}
{:else}
  <button
    type="button"
    class="row file"
    class:active={workspace.openPath === node.path}
    style:padding-left="{0.5 + depth * 0.85 + 0.9}rem"
    aria-current={workspace.openPath === node.path ? "page" : undefined}
    onclick={() => onopen(node.path)}
  >
    <span class="kind"><Icon size={16} /></span>
    <span class="name">{node.name}</span>
  </button>
{/if}

<style>
  .row {
    display: flex;
    align-items: center;
    gap: 0.4rem;
    width: 100%;
    min-width: 0;
    padding-block: 0.3rem;
    padding-right: 0.5rem;
    border: 0;
    border-radius: var(--radius);
    background: transparent;
    color: var(--sidebar-foreground);
    font: inherit;
    font-size: 0.875rem;
    text-align: left;
    cursor: pointer;
  }
  .row:hover { background: var(--sidebar-accent); }
  .row.active {
    background: var(--sidebar-accent);
    color: var(--sidebar-primary);
    font-weight: 500;
  }
  .row:focus-visible {
    outline: var(--focus-width) solid var(--ring);
    outline-offset: calc(-1 * var(--focus-width));
  }
  .dir { color: var(--muted-foreground); font-weight: 500; }
  .dir .name { color: var(--sidebar-foreground); }
  .chev {
    flex: none;
    transition: transform var(--motion-micro);
  }
  .chev.open { transform: rotate(90deg); }
  .kind { display: inline-flex; flex: none; color: var(--muted-foreground); }
  .row.active .kind { color: var(--sidebar-primary); }
  .name {
    min-width: 0;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }
  .children { display: flex; flex-direction: column; gap: 1px; }
  @media (prefers-reduced-motion: reduce) {
    .chev { transition: none; }
  }
</style>
