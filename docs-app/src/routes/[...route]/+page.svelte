<script lang="ts">
  import Markdown from "#lib/docs/Markdown.svelte";
  import Pager from "#lib/docs/Pager.svelte";
  import { SITE_URL } from "#lib/docs/site";
  import type { Page, PageLink } from "#lib/docs/types";

  let { data }: { data: { page: Page; previous: PageLink | null; next: PageLink | null } } = $props();

  // The title, then everything under it: the folded table of contents goes between the two.
  const title = $derived(data.page.blocks.slice(0, 1));
  const body = $derived(data.page.blocks.slice(1));
</script>

<!-- What a search engine and a pasted link read: the page's own summary, its one address, and its neighbours. -->
<svelte:head>
  <title>{data.page.title} · VFS Docs</title>
  <meta name="description" content={data.page.description} />
  <link rel="canonical" href={`${SITE_URL}${data.page.route}`} />
  {#if data.previous}<link rel="prev" href={data.previous.route} />{/if}
  {#if data.next}<link rel="next" href={data.next.route} />{/if}
</svelte:head>

<!-- The page's own column. The gap under the header is inside it, not above the row of columns. -->
<!-- The pager sits under the article and outside its prose styles: it is navigation, not text. -->
<div class="mx-auto w-full max-w-3xl px-(--gutter-stage) pt-10">
  <article class="docs-prose" data-slot="docs-article">
    <Markdown blocks={title} />
    <!-- Below the width the side column needs, the same list is here, closed, and opens without a script. -->
    {#if data.page.toc.length}
      <details data-slot="docs-toc-folded" class="mb-6 rounded bg-card px-4 py-3 text-sm xl:hidden">
        <summary class="cursor-pointer font-mono text-xs tracking-eyebrow text-muted-foreground lowercase">
          table of contents
        </summary>
        <ul class="mt-3 list-none ps-0">
          {#each data.page.toc as entry (entry.id)}
            <li class={entry.depth === 3 ? "ps-4" : ""}>
              <a href={`#${entry.id}`} class="block py-1">
                {#if entry.symbol}<span data-api-symbol={entry.symbol}>{entry.symbol}</span>{/if}{entry.text}
              </a>
            </li>
          {/each}
        </ul>
      </details>
    {/if}
    <Markdown blocks={body} />
  </article>
  <Pager previous={data.previous} next={data.next} />
</div>
