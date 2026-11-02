<script lang="ts">
  import { marked } from "marked";
  import TurndownService from "turndown";
  import { api } from "../api";
  import { workspace } from "../state.svelte";

  type Slide = { html: string };
  let slides = $state<Slide[]>([]);
  let path = $state<string | null>(null);
  let index = $state(0);
  let dirty = $state(false);
  let status = $state("");
  let stage = $state<HTMLElement | null>(null);

  const turndown = new TurndownService({ headingStyle: "atx", codeBlockStyle: "fenced", bulletListMarker: "-" });

  export async function open(p: string) {
    const body = await api.file(p);
    const parts = body.content.split(/\r?\n---\r?\n/);
    slides = await Promise.all(parts.map(async (md) => ({ html: await marked.parse(md.trim()) })));
    path = p;
    index = 0;
    workspace.openPath = p;
    dirty = false;
    status = "";
  }

  function go(to: number) {
    if (slides.length === 0) return;
    index = Math.max(0, Math.min(slides.length - 1, to));
  }

  function onInput() {
    if (!stage) return;
    slides[index].html = stage.innerHTML;
    dirty = true;
    status = "";
  }

  async function save() {
    if (!path) return;
    status = "Saving";
    const markdown = slides.map((s) => turndown.turndown(s.html).trim()).join("\n\n---\n\n") + "\n";
    try {
      const reply = await api.save(path, markdown);
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
      return;
    }
    const target = e.target as HTMLElement | null;
    if (!path || target?.isContentEditable || /^(INPUT|TEXTAREA)$/.test(target?.tagName ?? "")) return;
    if (e.key === "ArrowRight" || e.key === "PageDown") go(index + 1);
    if (e.key === "ArrowLeft" || e.key === "PageUp") go(index - 1);
  }

  // The deck is named by its first slide's heading, the way a person would name it; the file name is the fallback.
  const title = $derived.by(() => {
    const heading = slides[0]?.html.match(/<h1[^>]*>(.*?)<\/h1>/)?.[1]?.replace(/<[^>]+>/g, "");
    return heading || (path ? path.split("/").pop()!.replace(/\.md$/, "").replace(/[-_]/g, " ") : "");
  });
  function plain(html: string): string {
    return html.replace(/<[^>]+>/g, " ").replace(/\s+/g, " ").trim().slice(0, 60);
  }
</script>

<svelte:window onkeydown={onKey} />

<section class="deck">
  {#if path}
    <header class="head">
      <div>
        <h1 class="title">{title}</h1>
        <p class="meta">Slide {index + 1} of {slides.length}</p>
      </div>
      <div class="tools">
        <span class="status" class:ok={status === "Saved"} aria-live="polite">{status}</span>
        <button type="button" class="plain" onclick={() => go(index - 1)} disabled={index === 0}>Previous</button>
        <button type="button" class="plain" onclick={() => go(index + 1)} disabled={index >= slides.length - 1}>Next</button>
        <button type="button" class="save" onclick={save} disabled={!dirty && status !== ""}>Save</button>
      </div>
    </header>
    <div class="body">
      <div class="strip" role="tablist" aria-label="Slides">
        {#each slides as slide, i (i)}
          <button
            type="button"
            role="tab"
            class="thumb"
            class:active={i === index}
            aria-selected={i === index}
            onclick={() => go(i)}
          >
            <span class="thumb-n">{i + 1}</span>
            <span class="thumb-text">{plain(slide.html)}</span>
          </button>
        {/each}
      </div>
      <div class="stage-wrap">
        {#key `${path}:${index}`}
          <article class="stage" contenteditable="true" bind:this={stage} oninput={onInput} spellcheck="false" aria-label="Slide {index + 1}">
            {@html slides[index]?.html ?? ""}
          </article>
        {/key}
      </div>
    </div>
  {:else}
    <div class="empty"><p>Pick a deck from the list.</p></div>
  {/if}
</section>

<style>
  .deck { display: flex; flex-direction: column; min-height: 0; min-width: 0; height: 100%; outline: none; background: var(--background); font-family: "Geist Variable", system-ui, sans-serif; }
  .head { display: flex; justify-content: space-between; align-items: flex-end; gap: 1rem; padding: 1.5rem 2rem 1rem; }
  .title { margin: 0; font-size: 1.5rem; font-weight: 600; letter-spacing: -0.02em; }
  .meta { margin: 0.2rem 0 0; color: var(--muted-foreground); font-size: 0.85rem; font-variant-numeric: tabular-nums; }
  .tools { display: flex; align-items: center; gap: 0.5rem; }
  .status { color: var(--muted-foreground); font-size: 0.8rem; }
  .status.ok { color: var(--success); }
  .plain { padding: 0.4rem 0.7rem; border: var(--line-width) solid var(--border); border-radius: var(--radius); background: transparent; color: var(--foreground); font: inherit; font-size: 0.85rem; cursor: pointer; }
  .plain:disabled { opacity: 0.4; cursor: default; }
  .save { padding: 0.4rem 0.9rem; border: 0; border-radius: var(--radius); background: var(--primary); color: var(--primary-foreground); font: inherit; font-size: 0.85rem; font-weight: 500; cursor: pointer; }
  .save:disabled { opacity: 0.5; cursor: default; }
  .body { flex: 1; min-height: 0; display: grid; grid-template-columns: 150px minmax(0, 1fr); gap: 1.25rem; padding: 0 2rem 2rem; }
  .strip { display: flex; flex-direction: column; gap: 0.5rem; min-height: 0; overflow: auto; }
  .thumb {
    display: flex;
    gap: 0.5rem;
    align-items: flex-start;
    padding: 0.5rem 0.6rem;
    border: var(--line-width) solid var(--border);
    border-radius: var(--radius);
    background: var(--raised);
    color: var(--muted-foreground);
    font: inherit;
    font-size: 0.72rem;
    line-height: 1.35;
    text-align: left;
    aspect-ratio: 16 / 7;
    cursor: pointer;
  }
  .thumb.active { border-color: var(--primary); color: var(--foreground); box-shadow: 0 0 0 1px var(--primary); }
  .thumb-n { flex: none; color: var(--muted-foreground); font-variant-numeric: tabular-nums; }
  .thumb-text { overflow: hidden; display: -webkit-box; -webkit-line-clamp: 3; line-clamp: 3; -webkit-box-orient: vertical; }
  .stage-wrap { display: flex; align-items: flex-start; min-width: 0; container-type: inline-size; }
  .stage {
    width: 100%;
    max-width: 960px;
    aspect-ratio: 16 / 9;
    min-height: max-content;
    padding: clamp(1.5rem, 5cqw, 3rem) clamp(1.75rem, 6cqw, 3.5rem);
    border: var(--line-width) solid var(--border);
    border-radius: var(--radius);
    background: var(--raised);
    color: var(--card-foreground);
    box-shadow: 0 8px 24px var(--elevation-shadow);
    font-family: "IBM Plex Sans Variable", Georgia, serif;
    font-size: clamp(0.95rem, 2.3cqw, 1.25rem);
    line-height: 1.45;
    outline: none;
  }
  .stage:focus-visible { box-shadow: 0 0 0 var(--focus-width) var(--ring), 0 8px 24px var(--elevation-shadow); }
  .stage :global(h1) { font-family: "Geist Variable", system-ui, sans-serif; font-size: clamp(1.6rem, 5cqw, 2.6rem); font-weight: 600; letter-spacing: -0.025em; line-height: 1.1; margin: 0 0 1.5rem; text-wrap: balance; }
  .stage :global(h2) { font-family: "Geist Variable", system-ui, sans-serif; font-size: clamp(1.35rem, 4cqw, 2rem); font-weight: 600; letter-spacing: -0.02em; line-height: 1.15; margin: 0 0 1.25rem; text-wrap: balance; }
  .stage :global(h3) { font-family: "Geist Variable", system-ui, sans-serif; font-size: 1.4rem; font-weight: 600; margin: 1.5rem 0 0.5rem; }
  .stage :global(p) { margin: 0 0 0.8rem; max-width: 48ch; }
  .stage :global(ul), .stage :global(ol) { margin: 0 0 1rem; padding-left: 1.4rem; }
  .stage :global(li) { margin-bottom: 0.4rem; }
  .stage :global(strong) { font-weight: 600; }
  .stage :global(table) { border-collapse: collapse; font-size: 1rem; }
  .stage :global(td), .stage :global(th) { border: var(--line-width) solid var(--border); padding: 0.4rem 0.8rem; font-variant-numeric: tabular-nums; }
  .stage :global(blockquote) { margin: 0 0 1rem; padding-left: 1rem; border-left: 4px solid var(--primary); color: var(--muted-foreground); }
  .plain:focus-visible, .save:focus-visible, .thumb:focus-visible { outline: var(--focus-width) solid var(--ring); outline-offset: var(--focus-offset); }
  .empty { flex: 1; display: grid; place-content: center; color: var(--muted-foreground); }
  @media (max-width: 900px) {
    .body { grid-template-columns: minmax(0, 1fr); padding-inline: 1rem; }
    .strip { flex-direction: row; order: 2; }
    .thumb { min-width: 8rem; }
    .stage { padding: 1.5rem; font-size: 1rem; }
  }
</style>
