<script lang="ts">
  import { workspace } from "../state.svelte";
  import FileTree from "./FileTree.svelte";

  let { onopen }: { onopen: (path: string) => void } = $props();

  const counts = $derived.by(() => {
    let files = 0;
    let folders = 0;
    const walk = (node: { kind: string; children?: { kind: string; children?: unknown[] }[] }) => {
      for (const child of node.children ?? []) {
        if (child.kind === "directory") {
          folders += 1;
          walk(child as typeof node);
        } else files += 1;
      }
    };
    if (workspace.tree) walk(workspace.tree);
    return { files, folders };
  });
</script>

<section class="files" aria-label="Files">
  <header class="head">
    <div>
      <h1 class="title">Files</h1>
      <p class="sub">
        Everything in the workspace as {workspace.current?.name ?? "you"} can see it: {counts.files} files in {counts.folders} folders. Open a file and it lands in its app.
      </p>
    </div>
  </header>
  <div class="tree">
    {#if workspace.tree}
      <FileTree node={workspace.tree} {onopen} />
    {:else if !workspace.loading}
      <p class="empty">Nothing here that you can see.</p>
    {/if}
  </div>
</section>

<style>
  .files {
    display: flex;
    flex-direction: column;
    gap: 1.25rem;
    height: 100%;
    min-width: 0;
    padding: 2rem 2.5rem;
    overflow: auto;
  }
  .head { max-width: 60ch; }
  .title { margin: 0; font-size: 1.5rem; font-weight: 600; letter-spacing: -0.02em; }
  .sub { margin: 0.35rem 0 0; color: var(--muted-foreground); font-size: 0.9rem; line-height: 1.5; }
  .tree {
    max-width: 44rem;
    padding: 0.5rem;
    border: var(--line-width) solid var(--border);
    border-radius: calc(var(--radius) * 1.5);
    background: var(--card);
  }
  .empty { margin: 0; padding: 1rem; color: var(--muted-foreground); font-size: 0.9rem; }
  @media (max-width: 900px) {
    .files { padding: 1.25rem 1rem; }
  }
</style>
