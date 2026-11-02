<script lang="ts">
  import { api } from "../api";
  import { workspace } from "../state.svelte";

  let text = $state("");
  let path = $state<string | null>(null);
  let dirty = $state(false);
  let status = $state("");
  let gutter = $state<HTMLElement | null>(null);
  let area = $state<HTMLTextAreaElement | null>(null);

  export async function open(p: string) {
    const body = await api.file(p);
    text = body.content;
    path = p;
    workspace.openPath = p;
    dirty = false;
    status = "";
  }

  async function save() {
    if (!path) return;
    status = "Saving";
    try {
      const reply = await api.save(path, text);
      if (!reply.ok) throw new Error(reply.output);
      dirty = false;
      status = "Saved";
    } catch (e) {
      status = e instanceof Error ? e.message : "Save failed";
    }
  }

  function onKey(e: KeyboardEvent) {
    if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === "s") {
      e.preventDefault();
      save();
    } else if (e.key === "Tab" && area) {
      e.preventDefault();
      const { selectionStart, selectionEnd } = area;
      text = text.slice(0, selectionStart) + "    " + text.slice(selectionEnd);
      dirty = true;
      requestAnimationFrame(() => area?.setSelectionRange(selectionStart + 4, selectionStart + 4));
    }
  }

  function sync() {
    if (gutter && area) gutter.scrollTop = area.scrollTop;
  }

  const lines = $derived(text.split("\n").length);
  const title = $derived(path ? path.split("/").pop()! : "");
  const language = $derived(path?.endsWith(".rs") ? "Rust" : "Plain text");
</script>

<section class="code">
  {#if path}
    <header class="head">
      <div>
        <h1 class="title">{title}</h1>
        <p class="meta">{language}, {lines} lines</p>
      </div>
      <div class="tools">
        <span class="status" class:ok={status === "Saved"} aria-live="polite">{status}</span>
        <button type="button" class="save" onclick={save} disabled={!dirty && status !== ""}>Save</button>
      </div>
    </header>
    <div class="editor">
      <div class="gutter" bind:this={gutter} aria-hidden="true">
        {#each { length: lines } as _, i (i)}<span class="ln">{i + 1}</span>{/each}
      </div>
      <textarea
        id="code-text"
        class="text"
        bind:this={area}
        bind:value={text}
        oninput={() => { dirty = true; status = ""; }}
        onkeydown={onKey}
        onscroll={sync}
        spellcheck="false"
        wrap="off"
        aria-label="Source of {title}"
      ></textarea>
    </div>
  {:else}
    <div class="empty"><p>Pick a file from the list.</p></div>
  {/if}
</section>

<style>
  .code { display: flex; flex-direction: column; min-height: 0; min-width: 0; height: 100%; background: var(--raised); font-family: "Geist Variable", system-ui, sans-serif; }
  .head { display: flex; justify-content: space-between; align-items: flex-end; gap: 1rem; padding: 1.5rem 2rem 1rem; border-bottom: var(--line-width) solid var(--border); }
  .title { margin: 0; font-family: "JetBrains Mono Variable", ui-monospace, monospace; font-size: 1.2rem; font-weight: 600; }
  .meta { margin: 0.2rem 0 0; color: var(--muted-foreground); font-size: 0.85rem; font-variant-numeric: tabular-nums; }
  .tools { display: flex; align-items: center; gap: 0.5rem; }
  .status { color: var(--muted-foreground); font-size: 0.8rem; }
  .status.ok { color: var(--success); }
  .save { padding: 0.4rem 0.9rem; border: 0; border-radius: var(--radius); background: var(--primary); color: var(--primary-foreground); font: inherit; font-size: 0.85rem; font-weight: 500; cursor: pointer; }
  .save:disabled { opacity: 0.5; cursor: default; }
  .save:focus-visible { outline: var(--focus-width) solid var(--ring); outline-offset: var(--focus-offset); }
  .editor { flex: 1; min-height: 0; display: grid; grid-template-columns: 3.5rem minmax(0, 1fr); font-family: "JetBrains Mono Variable", ui-monospace, monospace; font-size: 0.85rem; line-height: 1.6; }
  .gutter { overflow: hidden; padding: 1rem 0; background: var(--background); color: var(--muted-foreground); text-align: right; font-variant-numeric: tabular-nums; user-select: none; }
  .ln { display: block; padding-right: 0.75rem; }
  .text { padding: 1rem 1.25rem; border: 0; resize: none; background: transparent; color: var(--foreground); font: inherit; outline: none; white-space: pre; overflow: auto; tab-size: 4; }
  .text:focus-visible { box-shadow: inset var(--focus-width) 0 0 var(--ring); }
  .empty { flex: 1; display: grid; place-content: center; color: var(--muted-foreground); }
</style>
