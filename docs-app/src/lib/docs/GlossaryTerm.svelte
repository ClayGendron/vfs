<script lang="ts">
  import Inline from "./Inline.svelte";
  import type { GlossaryTerm, TermRow } from "./types";

  let { term }: { term: GlossaryTerm } = $props();
</script>

{#snippet rows(found: TermRow[])}
  <ul>
    {#each found as row (row.name)}
      <li>
        {#if row.href}
          <a href={row.href}>{#if row.code}<code>{row.name}</code>{:else}{row.name}{/if}</a>
        {:else if row.code}
          <code>{row.name}</code>
        {:else}
          {row.name}
        {/if}
        {#if row.where}<span data-term-where>{row.where}</span>{/if}
      </li>
    {/each}
  </ul>
{/snippet}

<!-- What stands under a term's definition: the types the page names, then what the build found for the term. -->
<dl data-term>
  <dt>Types</dt>
  <dd>
    {#if term.types.length}{@render rows(term.types)}{:else}<span data-term-none><Inline nodes={term.note} /></span>{/if}
  </dd>
  <dt>Code</dt>
  <dd>{#if term.code.length}{@render rows(term.code)}{:else}<span data-term-none>None yet.</span>{/if}</dd>
  <dt>Documentation</dt>
  <dd>
    {#if term.documentation.length}{@render rows(term.documentation)}{:else}<span data-term-none>None yet.</span>{/if}
  </dd>
  <dt>Related terms</dt>
  <dd>{#if term.related.length}{@render rows(term.related)}{:else}<span data-term-none>None.</span>{/if}</dd>
</dl>
