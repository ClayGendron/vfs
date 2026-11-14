<script lang="ts">
  import type { TocEntry } from "./types";

  let { entries }: { entries: TocEntry[] } = $props();

  let list = $state<HTMLElement | null>(null);
  let active = $state<string | null>(null);
  let hovered = false;

  // The heading a reader is at: the last one whose top has passed under the header.
  function follow() {
    const line = 120;
    let current: string | null = entries[0]?.id ?? null;
    for (const entry of entries) {
      const heading = document.getElementById(entry.id);
      if (heading && heading.getBoundingClientRect().top <= line) current = entry.id;
    }
    active = current;
  }

  $effect(() => {
    if (!entries.length) return;
    follow();
    window.addEventListener("scroll", follow, { passive: true });
    return () => window.removeEventListener("scroll", follow);
  });

  // Keep the current entry in view by moving this list alone, and never while the reader is using it.
  $effect(() => {
    if (!active || !list || hovered) return;
    const link = list.querySelector<HTMLElement>(`[data-id="${CSS.escape(active)}"]`);
    if (!link) return;
    const top = link.offsetTop;
    const bottom = top + link.offsetHeight;
    if (top < list.scrollTop) list.scrollTop = top - 16;
    else if (bottom > list.scrollTop + list.clientHeight) list.scrollTop = bottom - list.clientHeight + 16;
  });
</script>

<!-- Starts directly under the header and sticks there. It is its own scroll container and keeps its scroll to itself. -->
{#if entries.length}
  <nav
    bind:this={list}
    aria-label="Table of contents"
    data-slot="docs-toc"
    onpointerenter={() => (hovered = true)}
    onpointerleave={() => (hovered = false)}
    class="sticky top-(--size-bar) hidden h-[calc(100svh-var(--size-bar))] w-3xs shrink-0 self-start overflow-y-auto overscroll-contain pt-10 pe-5 pb-10 text-sm scrollbar xl:block"
  >
    <p class="mb-2 font-mono text-xs tracking-eyebrow text-muted-foreground lowercase">table of contents</p>
    <ul class="groove-s">
      {#each entries as entry (entry.id)}
        <li>
          <a
            href={`#${entry.id}`}
            data-id={entry.id}
            aria-current={active === entry.id ? "location" : undefined}
            class={[
              "block truncate py-1 text-muted-foreground no-underline hover:text-foreground aria-[current=location]:font-medium aria-[current=location]:text-foreground",
              entry.depth === 3 ? "ps-6" : "ps-3",
            ]}
          >
            {#if entry.symbol}<span data-api-symbol={entry.symbol}>{entry.symbol}</span>{/if}{entry.text}
          </a>
        </li>
      {/each}
    </ul>
  </nav>
{/if}
