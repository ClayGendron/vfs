<script lang="ts">
  import { marked } from "marked";
  import TurndownService from "turndown";
  import { api } from "../api";
  import { workspace } from "../state.svelte";

  let { onsaved }: { onsaved: (path: string) => void } = $props();

  type Doc = { path: string; html: string; dirty: boolean };
  let docs = $state<Doc[]>([]);
  let article = $state<HTMLElement | null>(null);
  let status = $state<"idle" | "saving" | "saved" | "error">("idle");
  let statusText = $state("");
  let naming = $state(false);
  let newPath = $state("/docs/untitled.md");
  let loadError = $state<string | null>(null);

  const turndown = new TurndownService({ headingStyle: "atx", codeBlockStyle: "fenced", bulletListMarker: "-" });
  marked.setOptions({ gfm: true, breaks: false });

  const active = $derived(docs.find((d) => d.path === workspace.openPath) ?? null);

  export async function open(path: string) {
    const existing = docs.find((d) => d.path === path);
    if (!existing) {
      try {
        const body = await api.file(path);
        const html = await marked.parse(body.content);
        docs = [...docs, { path, html, dirty: false }];
        loadError = null;
      } catch (e) {
        loadError = `Could not open ${path}. ${e instanceof Error ? e.message : ""}`;
        return;
      }
    }
    workspace.openPath = path;
    status = "idle";
  }

  function close(path: string) {
    docs = docs.filter((d) => d.path !== path);
    if (workspace.openPath === path) workspace.openPath = docs.at(-1)?.path ?? null;
  }

  // While a document is being typed into, the DOM owns its text: re-rendering it would reset the caret.
  const drafts: Record<string, string> = {};

  function onInput() {
    if (!active || !article) return;
    drafts[active.path] = article.innerHTML;
    active.dirty = true;
    if (status === "saved") status = "idle";
  }

  async function save() {
    if (!active || !article) return;
    status = "saving";
    const markdown = turndown.turndown(article.innerHTML);
    try {
      const reply = await api.save(active.path, markdown);
      if (!reply.ok) throw new Error(reply.output);
      active.dirty = false;
      status = "saved";
      statusText = "Saved";
      onsaved(active.path);
      setTimeout(() => {
        if (status === "saved") status = "idle";
      }, 2000);
    } catch (e) {
      status = "error";
      statusText = e instanceof Error ? e.message : "Save failed";
    }
  }

  function createDoc() {
    const path = newPath.trim().startsWith("/") ? newPath.trim() : `/docs/${newPath.trim()}`;
    if (!path.endsWith(".md")) {
      statusText = "A document path ends in .md";
      status = "error";
      return;
    }
    if (!docs.find((d) => d.path === path)) {
      const title = path.split("/").pop()!.replace(/\.md$/, "").replace(/[-_]/g, " ");
      docs = [...docs, { path, html: `<h1>${title}</h1><p></p>`, dirty: true }];
    }
    workspace.openPath = path;
    naming = false;
    status = "idle";
  }

  function exec(command: string, value?: string) {
    article?.focus();
    document.execCommand(command, false, value);
    onInput();
  }

  function onKey(e: KeyboardEvent) {
    if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === "s") {
      e.preventDefault();
      save();
    }
  }

  const tools: { label: string; run: () => void }[] = [
    { label: "Heading", run: () => exec("formatBlock", "h1") },
    { label: "Subheading", run: () => exec("formatBlock", "h2") },
    { label: "Body", run: () => exec("formatBlock", "p") },
    { label: "Bold", run: () => exec("bold") },
    { label: "Italic", run: () => exec("italic") },
    { label: "Bulleted list", run: () => exec("insertUnorderedList") },
    { label: "Code", run: () => exec("formatBlock", "pre") },
  ];
</script>

<!-- svelte-ignore a11y_no_static_element_interactions -->
<section class="editor" onkeydown={onKey}>
  <div class="tabs" role="tablist" aria-label="Open documents">
    {#each docs as doc (doc.path)}
      <div class="tab" class:active={doc.path === workspace.openPath} role="presentation">
        <button
          type="button"
          role="tab"
          aria-selected={doc.path === workspace.openPath}
          class="tab-name"
          onclick={() => (workspace.openPath = doc.path)}
        >
          {doc.path.split("/").pop()}{#if doc.dirty}<span class="dirty" aria-label="unsaved"></span>{/if}
        </button>
        <button type="button" class="tab-close" aria-label="Close {doc.path}" onclick={() => close(doc.path)}>×</button>
      </div>
    {/each}
    <button type="button" class="new" onclick={() => (naming = !naming)} aria-expanded={naming}>New document</button>
    {#if naming}
      <form class="naming" onsubmit={(e) => { e.preventDefault(); createDoc(); }}>
        <label class="naming-label" for="new-doc-path">Path</label>
        <input id="new-doc-path" class="naming-input" bind:value={newPath} spellcheck="false" />
        <button type="submit" class="naming-go">Create</button>
      </form>
    {/if}
  </div>

  {#if active}
    <div class="toolbar" role="toolbar" aria-label="Formatting">
      {#each tools as tool (tool.label)}
        <button type="button" class="tool" onmousedown={(e) => e.preventDefault()} onclick={tool.run}>{tool.label}</button>
      {/each}
      <span class="path">{active.path}</span>
      <span class="status" class:ok={status === "saved"} class:bad={status === "error"} aria-live="polite">
        {status === "saving" ? "Saving" : status === "idle" ? "" : statusText}
      </span>
      <button type="button" class="save" onclick={save} disabled={status === "saving"}>Save</button>
    </div>
    <div class="paper">
      {#key active.path}
        <article
          class="doc"
          contenteditable="true"
          bind:this={article}
          oninput={onInput}
          spellcheck="false"
          aria-label="Document body"
        >
          <!-- eslint-disable-next-line svelte/no-at-html-tags -->
          {@html drafts[active.path] ?? active.html}
        </article>
      {/key}
    </div>
  {:else}
    <div class="empty">
      <p class="empty-title">Open a document from the files on the left, or start a new one.</p>
      {#if loadError}<p class="empty-error">{loadError}</p>{/if}
    </div>
  {/if}
</section>

<style>
  .editor {
    display: flex;
    flex-direction: column;
    min-height: 0;
    min-width: 0;
    height: 100%;
    background: var(--background);
    font-family: "Geist Variable", system-ui, sans-serif;
  }
  .tabs {
    display: flex;
    align-items: center;
    gap: 0.25rem;
    flex-wrap: wrap;
    min-height: 2.5rem;
    padding: 0.35rem 0.75rem 0;
    border-bottom: var(--line-width) solid var(--border);
  }
  .tab {
    display: inline-flex;
    align-items: center;
    border-radius: var(--radius) var(--radius) 0 0;
    color: var(--muted-foreground);
    font-size: 0.85rem;
  }
  .tab.active {
    color: var(--foreground);
    background: var(--raised);
    box-shadow: inset 0 -2px 0 var(--primary);
  }
  .tab-name {
    display: inline-flex;
    align-items: center;
    gap: 0.4rem;
    padding: 0.45rem 0.5rem 0.45rem 0.75rem;
    border: 0;
    background: transparent;
    color: inherit;
    font: inherit;
    cursor: pointer;
  }
  .dirty {
    width: 0.4rem;
    height: 0.4rem;
    border-radius: 999px;
    background: var(--caution);
  }
  .tab-close {
    padding: 0.2rem 0.5rem 0.2rem 0.2rem;
    border: 0;
    background: transparent;
    color: var(--muted-foreground);
    font: inherit;
    cursor: pointer;
  }
  .tab-close:hover { color: var(--destructive); }
  .new {
    margin-left: 0.25rem;
    padding: 0.35rem 0.6rem;
    border: var(--line-width) dashed var(--input);
    border-radius: var(--radius);
    background: transparent;
    color: var(--muted-foreground);
    font: inherit;
    font-size: 0.8rem;
    cursor: pointer;
  }
  .new:hover { color: var(--foreground); border-style: solid; }
  .naming {
    display: inline-flex;
    align-items: center;
    gap: 0.4rem;
    margin-left: 0.5rem;
    font-size: 0.8rem;
  }
  .naming-label { color: var(--muted-foreground); }
  .naming-input {
    width: 16rem;
    padding: 0.3rem 0.5rem;
    border: var(--line-width) solid var(--input);
    border-radius: var(--radius);
    background: var(--raised);
    color: var(--foreground);
    font-family: "JetBrains Mono Variable", ui-monospace, monospace;
    font-size: 0.8rem;
  }
  .naming-go {
    padding: 0.3rem 0.6rem;
    border: 0;
    border-radius: var(--radius);
    background: var(--primary);
    color: var(--primary-foreground);
    font: inherit;
    font-size: 0.8rem;
    cursor: pointer;
  }
  .toolbar {
    display: flex;
    align-items: center;
    gap: 0.25rem;
    flex-wrap: wrap;
    padding: 0.4rem 0.75rem;
    border-bottom: var(--line-width) solid var(--border);
    background: var(--background);
  }
  .tool {
    padding: 0.3rem 0.55rem;
    border: 0;
    border-radius: var(--radius);
    background: transparent;
    color: var(--foreground);
    font: inherit;
    font-size: 0.8rem;
    cursor: pointer;
  }
  .tool:hover { background: var(--accent); }
  .path {
    margin-left: auto;
    color: var(--muted-foreground);
    font-family: "JetBrains Mono Variable", ui-monospace, monospace;
    font-size: 0.75rem;
  }
  .status {
    min-width: 3rem;
    color: var(--muted-foreground);
    font-size: 0.8rem;
    text-align: right;
  }
  .status.ok { color: var(--success); }
  .status.bad { color: var(--destructive); }
  .save {
    padding: 0.35rem 0.8rem;
    border: 0;
    border-radius: var(--radius);
    background: var(--primary);
    color: var(--primary-foreground);
    font: inherit;
    font-size: 0.8rem;
    font-weight: 500;
    cursor: pointer;
  }
  .save:disabled { opacity: 0.6; cursor: default; }
  .paper {
    flex: 1;
    min-height: 0;
    overflow: auto;
    padding: 2.5rem max(16px, env(safe-area-inset-right, 0px)) 4rem max(16px, env(safe-area-inset-left, 0px));
    background: var(--raised);
  }
  .doc {
    max-width: 72ch;
    margin-inline: auto;
    min-height: 60vh;
    outline: none;
    color: var(--card-foreground);
    font-family: "IBM Plex Sans Variable", Georgia, serif;
    font-size: 1.05rem;
    line-height: 1.65;
  }
  .doc:focus-visible { box-shadow: 0 0 0 var(--focus-width) var(--ring); border-radius: 2px; }
  .doc :global(h1) {
    font-family: "Geist Variable", system-ui, sans-serif;
    font-size: 2rem;
    font-weight: 600;
    letter-spacing: -0.02em;
    line-height: 1.15;
    margin: 0 0 1.25rem;
    text-wrap: balance;
  }
  .doc :global(h2) {
    font-family: "Geist Variable", system-ui, sans-serif;
    font-size: 1.35rem;
    font-weight: 600;
    letter-spacing: -0.01em;
    margin: 2rem 0 0.6rem;
    text-wrap: balance;
  }
  .doc :global(h3) {
    font-family: "Geist Variable", system-ui, sans-serif;
    font-size: 1.05rem;
    font-weight: 600;
    margin: 1.5rem 0 0.4rem;
  }
  .doc :global(p) { margin: 0 0 1rem; }
  .doc :global(ul), .doc :global(ol) { margin: 0 0 1rem; padding-left: 1.4rem; }
  .doc :global(li) { margin-bottom: 0.3rem; }
  .doc :global(pre) {
    margin: 0 0 1rem;
    padding: 0.9rem 1rem;
    border-radius: var(--radius);
    background: var(--code-background);
    color: var(--code-foreground);
    font-family: "JetBrains Mono Variable", ui-monospace, monospace;
    font-size: 0.85rem;
    line-height: 1.5;
    overflow-x: auto;
    white-space: pre-wrap;
  }
  .doc :global(code) {
    font-family: "JetBrains Mono Variable", ui-monospace, monospace;
    font-size: 0.9em;
  }
  .doc :global(table) { border-collapse: collapse; margin: 0 0 1rem; font-size: 0.95rem; }
  .doc :global(th), .doc :global(td) {
    padding: 0.4rem 0.7rem;
    border: var(--line-width) solid var(--border);
    text-align: left;
    font-variant-numeric: tabular-nums;
  }
  .doc :global(th) { background: var(--muted); font-weight: 600; }
  .doc :global(blockquote) {
    margin: 0 0 1rem;
    padding-left: 1rem;
    border-left: 3px solid var(--border);
    color: var(--muted-foreground);
  }
  .doc :global(a) { color: var(--primary); }
  .doc :global(hr) { border: 0; border-top: var(--line-width) solid var(--border); margin: 2rem 0; }
  .empty {
    flex: 1;
    display: grid;
    place-content: center;
    padding: 2rem;
    text-align: center;
    color: var(--muted-foreground);
  }
  .empty-title { max-width: 32ch; margin: 0; font-size: 1rem; }
  .empty-error { color: var(--destructive); font-size: 0.85rem; }
  .tool:focus-visible, .save:focus-visible, .new:focus-visible, .tab-name:focus-visible,
  .tab-close:focus-visible, .naming-go:focus-visible, .naming-input:focus-visible {
    outline: var(--focus-width) solid var(--ring);
    outline-offset: var(--focus-offset);
  }
</style>
