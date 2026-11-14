<script lang="ts">
  import Markdown from "#lib/Markdown.svelte";
  let { data } = $props();
</script>

{#if data.index}
  <h1>Every page</h1>
  <ul>{#each data.index as page}<li><a href={`/${page}`}>{page}</a></li>{/each}</ul>
{:else}
  <nav aria-label="On this page"><ul>{#each data.page.headings as h}<li><a href={`#${h.id}`}>{h.text}</a></li>{/each}</ul></nav>
  <article class="prose"><Markdown tokens={data.page.tokens} /></article>
{/if}
