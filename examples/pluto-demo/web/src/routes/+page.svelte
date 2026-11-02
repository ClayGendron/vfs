<script lang="ts">
  import { onMount } from "svelte";
  import "../app.css";
  import Chat from "#lib/components/Chat.svelte";
  import Editor from "#lib/components/Editor.svelte";
  import FileTree from "#lib/components/FileTree.svelte";
  import Shell from "#lib/components/Shell.svelte";
  import TopBar from "#lib/components/TopBar.svelte";
  import { workspace } from "#lib/state.svelte";

  let editor = $state<Editor | null>(null);
  let shell = $state<Shell | null>(null);
  let pane = $state<"files" | "document" | "agent">("document");

  onMount(() => {
    workspace.initTheme();
    workspace.setTheme(workspace.theme);
    let timer: ReturnType<typeof setInterval> | undefined;
    (async () => {
      await workspace.refresh();
      await workspace.pollLog();
      if (workspace.tree && !workspace.openPath) await editor?.open("/docs/handbook.md");
      timer = setInterval(() => workspace.pollLog(), 2000);
    })();
    return () => {
      if (timer) clearInterval(timer);
    };
  });

  function onKey(e: KeyboardEvent) {
    const target = e.target as HTMLElement | null;
    const typing = target && (target.isContentEditable || /^(INPUT|TEXTAREA)$/.test(target.tagName));
    if (e.key === "`" && !typing) {
      e.preventDefault();
      workspace.shellOpen = !workspace.shellOpen;
      if (workspace.shellOpen) setTimeout(() => shell?.focus(), 0);
    }
  }

  function openFile(path: string) {
    editor?.open(path);
    pane = "document";
  }

  function refreshTree() {
    workspace.refresh();
  }
</script>

<svelte:window onkeydown={onKey} />

<div class="app">
  <TopBar />

  {#if workspace.error}
    <div class="offline" role="alert">
      The workspace server is not answering. Start it with <code>examples/pluto-demo/run.sh</code>, then reload.
      <span class="offline-detail">{workspace.error}</span>
    </div>
  {/if}

  <nav class="panes" aria-label="Panes">
    <button type="button" class:active={pane === "files"} onclick={() => (pane = "files")}>Files</button>
    <button type="button" class:active={pane === "document"} onclick={() => (pane = "document")}>Document</button>
    <button type="button" class:active={pane === "agent"} onclick={() => (pane = "agent")}>Atlas</button>
  </nav>

  <main class="work" data-pane={pane}>
    <aside class="files" aria-label="Files">
      <div class="files-head">
        <span>Files</span>
        <span class="files-who">as {workspace.current?.name ?? "…"}</span>
      </div>
      <div class="tree">
        {#if workspace.tree}
          <FileTree node={workspace.tree} onopen={openFile} />
        {:else if workspace.loading}
          <p class="muted">Loading the workspace</p>
        {/if}
      </div>
    </aside>

    <section class="center">
      <div class="doc-area">
        <Editor bind:this={editor} onsaved={refreshTree} />
      </div>
      <div class="shell-bar">
        <button
          type="button"
          class="shell-toggle"
          aria-expanded={workspace.shellOpen}
          onclick={() => (workspace.shellOpen = !workspace.shellOpen)}
        >
          Shell
          <kbd>`</kbd>
        </button>
        <span class="shell-hint">One shell for people and agents. Every command goes through the same gate.</span>
      </div>
      {#if workspace.shellOpen}
        <Shell bind:this={shell} onchanged={refreshTree} />
      {/if}
    </section>

    <aside class="agent">
      <Chat onchanged={refreshTree} />
    </aside>
  </main>

  <footer class="foot">A Pluto Systems product</footer>
</div>

<style>
  :global(html), :global(body) {
    height: 100%;
    margin: 0;
    background: var(--background);
    color: var(--foreground);
    font-family: "Geist Variable", system-ui, sans-serif;
    -webkit-font-smoothing: antialiased;
  }
  :global(*), :global(*::before), :global(*::after) { box-sizing: border-box; }
  .app {
    display: flex;
    flex-direction: column;
    height: 100%;
    overflow: hidden;
  }
  .offline {
    padding: 0.6rem max(16px, env(safe-area-inset-right, 0px)) 0.6rem max(16px, env(safe-area-inset-left, 0px));
    background: var(--caution);
    color: var(--caution-foreground);
    font-size: 0.85rem;
  }
  .offline code { font-family: "JetBrains Mono Variable", ui-monospace, monospace; }
  .offline-detail { display: block; opacity: 0.7; font-size: 0.75rem; }
  .panes { display: none; }
  .work {
    flex: 1;
    min-height: 0;
    display: grid;
    grid-template-columns: 260px minmax(0, 1fr) 380px;
  }
  .files {
    display: flex;
    flex-direction: column;
    min-height: 0;
    min-width: 0;
    border-right: var(--line-width) solid var(--sidebar-border);
    background: var(--sidebar);
  }
  .files-head {
    display: flex;
    justify-content: space-between;
    align-items: baseline;
    padding: 0.7rem 1rem 0.4rem;
    font-size: 0.85rem;
    font-weight: 600;
  }
  .files-who { color: var(--muted-foreground); font-weight: 400; font-size: 0.75rem; }
  .tree {
    flex: 1;
    min-height: 0;
    overflow: auto;
    padding: 0 0.5rem 1rem;
  }
  .muted { color: var(--muted-foreground); font-size: 0.85rem; padding: 0.5rem; }
  .center {
    display: flex;
    flex-direction: column;
    min-height: 0;
    min-width: 0;
  }
  .doc-area { flex: 1; min-height: 0; }
  .shell-bar {
    display: flex;
    align-items: center;
    gap: 0.75rem;
    padding: 0.25rem 0.75rem;
    border-top: var(--line-width) solid var(--border);
    background: var(--background);
  }
  .shell-toggle {
    display: inline-flex;
    align-items: center;
    gap: 0.4rem;
    padding: 0.25rem 0.55rem;
    border: 0;
    border-radius: var(--radius);
    background: transparent;
    color: var(--foreground);
    font: inherit;
    font-size: 0.8rem;
    font-weight: 500;
    cursor: pointer;
  }
  .shell-toggle:hover { background: var(--accent); }
  .shell-toggle:focus-visible { outline: var(--focus-width) solid var(--ring); outline-offset: var(--focus-offset); }
  .shell-toggle kbd {
    padding: 0 0.35rem;
    border: var(--line-width) solid var(--border);
    border-radius: 4px;
    background: var(--muted);
    font-family: "JetBrains Mono Variable", ui-monospace, monospace;
    font-size: 0.7rem;
  }
  .shell-hint { color: var(--muted-foreground); font-size: 0.75rem; }
  .agent { min-height: 0; min-width: 0; }
  .foot {
    padding: 0.35rem max(16px, env(safe-area-inset-right, 0px)) max(0.35rem, env(safe-area-inset-bottom, 0px)) max(16px, env(safe-area-inset-left, 0px));
    border-top: var(--line-width) solid var(--border);
    color: var(--muted-foreground);
    font-size: 0.72rem;
  }
  @media (max-width: 900px) {
    .panes {
      display: flex;
      gap: 0.25rem;
      padding: 0.35rem max(16px, env(safe-area-inset-right, 0px)) 0.35rem max(16px, env(safe-area-inset-left, 0px));
      border-bottom: var(--line-width) solid var(--border);
    }
    .panes button {
      padding: 0.35rem 0.7rem;
      border: 0;
      border-radius: var(--radius);
      background: transparent;
      color: var(--muted-foreground);
      font: inherit;
      font-size: 0.85rem;
      cursor: pointer;
    }
    .panes button.active { background: var(--muted); color: var(--foreground); font-weight: 500; }
    .work { grid-template-columns: minmax(0, 1fr); }
    .files, .center, .agent { display: none; }
    .work[data-pane="files"] .files { display: flex; border-right: 0; }
    .work[data-pane="document"] .center { display: flex; }
    .work[data-pane="agent"] .agent { display: block; }
    .agent :global(.chat) { border-left: 0; }
    .shell-hint { display: none; }
    .foot { display: none; }
  }
</style>
