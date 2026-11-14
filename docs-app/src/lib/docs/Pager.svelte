<script lang="ts">
  import type { PageLink } from "./types";

  let { previous, next }: { previous: PageLink | null; next: PageLink | null } = $props();
</script>

<!-- The page before and the page after, in the navigation's order. -->
{#if previous || next}
  <nav aria-label="Previous and next page" data-slot="docs-pager" class="mt-16 flex justify-between gap-6 pt-6 text-sm groove">
    {#if previous}
      <a href={previous.route} class="no-underline">
        <span class="block font-mono text-xs text-muted-foreground lowercase">previous</span>
        {previous.title}
      </a>
    {:else}
      <span></span>
    {/if}
    {#if next}
      <a href={next.route} class="text-end no-underline">
        <span class="block font-mono text-xs text-muted-foreground lowercase">next</span>
        {next.title}
      </a>
    {/if}
  </nav>
{/if}
