<script lang="ts">
  import { onMount } from "svelte";
  import "../app.css";
  import AppList from "#lib/components/AppList.svelte";
  import Files from "#lib/components/Files.svelte";
  import Chat from "#lib/components/Chat.svelte";
  import Code from "#lib/components/Code.svelte";
  import Editor from "#lib/components/Editor.svelte";
  import Ribbon from "#lib/components/Ribbon.svelte";
  import Sheets from "#lib/components/Sheets.svelte";
  import Shell from "#lib/components/Shell.svelte";
  import Slides from "#lib/components/Slides.svelte";
  import TopBar from "#lib/components/TopBar.svelte";
  import { APPS, appFor, filesFor, workspace, type AppId } from "#lib/state.svelte";

  let editor = $state<Editor | null>(null);
  let sheets = $state<Sheets | null>(null);
  let slides = $state<Slides | null>(null);
  let code = $state<Code | null>(null);
  let shell = $state<Shell | null>(null);
  let listOpen = $state(false);
  let mobileAtlas = $state(false);

  const appName = $derived(APPS.find((a) => a.id === workspace.app)?.name ?? "");

  onMount(() => {
    workspace.initTheme();
    workspace.setTheme(workspace.theme);
    let timer: ReturnType<typeof setInterval> | undefined;
    (async () => {
      await workspace.refresh();
      await workspace.pollLog();
      timer = setInterval(() => workspace.pollLog(), 2000);
    })();
    return () => {
      if (timer) clearInterval(timer);
    };
  });

  // Each app remembers the file it had open; switching apps reopens the first file when it has none.
  const lastOpen: Partial<Record<AppId, string>> = { docs: "/docs/handbook.md" };

  async function openFile(path: string) {
    const app = appFor(path);
    if (!app) return;
    if (workspace.app !== app) workspace.openApp(app);
    lastOpen[app] = path;
    listOpen = false;
    await Promise.resolve();
    if (app === "docs") await editor?.open(path);
    else if (app === "sheets") await sheets?.open(path);
    else if (app === "slides") await slides?.open(path);
    else if (app === "code") await code?.open(path);
  }

  $effect(() => {
    const app = workspace.app;
    if (app === "terminal" || app === "files") return;
    const remembered = lastOpen[app];
    const first = filesFor(workspace.tree, app)[0]?.files[0]?.path;
    const target = remembered ?? first;
    if (target && workspace.openPath !== target) openFile(target);
  });

  function onKey(e: KeyboardEvent) {
    const target = e.target as HTMLElement | null;
    const typing = target && (target.isContentEditable || /^(INPUT|TEXTAREA)$/.test(target.tagName));
    if (e.key === "`" && !typing) {
      e.preventDefault();
      workspace.openApp("terminal");
      setTimeout(() => shell?.focus(), 0);
    }
  }

  function refreshTree() {
    workspace.refresh();
  }
</script>

<svelte:window onkeydown={onKey} />

<div class="app" class:atlas={workspace.atlasOpen}>
  <Ribbon />

  <div class="main">
    <TopBar />

    {#if workspace.error}
      <div class="offline" role="alert">
        The workspace server is not answering. Start it with <code>examples/pluto-demo/run.sh</code>, then reload.
        <span class="offline-detail">{workspace.error}</span>
      </div>
    {/if}

    <div class="work">
      {#if workspace.app !== "terminal" && workspace.app !== "files"}
        <button type="button" class="list-toggle" onclick={() => (listOpen = !listOpen)} aria-expanded={listOpen}>
          {appName} files
        </button>
        <div class="list" class:open={listOpen}>
          <AppList title={appName} onopen={openFile} />
        </div>
      {/if}

      <div class="content">
        {#if workspace.app === "files"}
          <Files onopen={openFile} />
        {:else if workspace.app === "docs"}
          <Editor bind:this={editor} onsaved={refreshTree} />
        {:else if workspace.app === "sheets"}
          <Sheets bind:this={sheets} />
        {:else if workspace.app === "slides"}
          <Slides bind:this={slides} />
        {:else if workspace.app === "code"}
          <Code bind:this={code} />
        {:else}
          <div class="terminal">
            <div class="terminal-head">
              <span class="terminal-title">Terminal</span>
              <span class="terminal-hint">One shell for people and agents. Every command goes through the same gate.</span>
            </div>
            <Shell bind:this={shell} onchanged={refreshTree} />
          </div>
        {/if}
      </div>
    </div>

    <footer class="foot">A Pluto Systems product</footer>
  </div>

  {#if workspace.atlasOpen}
    <aside class="agent" class:mobile-open={mobileAtlas}>
      <Chat onchanged={refreshTree} onclose={() => (workspace.atlasOpen = false)} />
    </aside>
  {/if}
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
    display: grid;
    grid-template-columns: 64px minmax(0, 1fr);
    height: 100%;
    overflow: hidden;
  }
  .app.atlas { grid-template-columns: 64px minmax(0, 1fr) 380px; }
  .main { display: flex; flex-direction: column; min-height: 0; min-width: 0; }
  .offline {
    padding: 0.6rem 1rem;
    background: var(--caution);
    color: var(--caution-foreground);
    font-size: 0.85rem;
  }
  .offline code { font-family: "JetBrains Mono Variable", ui-monospace, monospace; }
  .offline-detail { display: block; opacity: 0.7; font-size: 0.75rem; }
  .work { flex: 1; min-height: 0; display: flex; }
  .list-toggle { display: none; }
  .list { display: flex; min-height: 0; }
  .content { flex: 1; min-width: 0; min-height: 0; display: flex; flex-direction: column; }
  .terminal { display: flex; flex-direction: column; height: 100%; min-height: 0; }
  .terminal-head {
    display: flex;
    align-items: baseline;
    gap: 0.75rem;
    padding: 1.25rem 2rem 0.75rem;
    background: var(--background);
  }
  .terminal-title { font-size: 1.5rem; font-weight: 600; letter-spacing: -0.02em; }
  .terminal-hint { color: var(--muted-foreground); font-size: 0.85rem; }
  .terminal :global(.shell) { flex: 1; height: auto !important; }
  .terminal :global(.grip) { display: none; }
  .agent { min-height: 0; min-width: 0; }
  .foot {
    padding: 0.3rem 1rem;
    border-top: var(--line-width) solid var(--border);
    color: var(--muted-foreground);
    font-size: 0.7rem;
  }
  @media (max-width: 900px) {
    .app, .app.atlas { grid-template-columns: minmax(0, 1fr); grid-template-rows: minmax(0, 1fr) auto; }
    .app :global(.ribbon) { order: 3; }
    .main { order: 1; }
    .work { flex-direction: column; }
    .list-toggle {
      display: block;
      margin: 0.5rem 1rem 0;
      padding: 0.4rem 0.7rem;
      border: var(--line-width) solid var(--border);
      border-radius: var(--radius);
      background: var(--raised);
      color: var(--foreground);
      font: inherit;
      font-size: 0.85rem;
      text-align: left;
    }
    .list { display: none; max-height: 45vh; border-bottom: var(--line-width) solid var(--border); }
    .list.open { display: flex; }
    .agent { position: fixed; inset: 0 0 56px; z-index: 5; background: var(--background); order: 2; }
    .agent :global(.chat) { border-left: 0; }
    .foot, .terminal-hint { display: none; }
    .terminal-head { padding: 0.75rem 1rem 0.5rem; }
  }
</style>
