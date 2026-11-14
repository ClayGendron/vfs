<script lang="ts">
  import * as CodeBlock from "#lib/components/ui/code-block";
  import HeadingLink from "./HeadingLink.svelte";
  import Markdown from "./Markdown.svelte";
  import type { ApiMember, ApiObject } from "./types";

  let { object }: { object: ApiObject } = $props();

  // A member is a third-level heading; the fields of a class a module lists sit one level under it.
  const MEMBER_LEVEL = 3;
</script>

{#snippet labels(names: string[])}
  {#each names as label (label)}<span data-api-label>{label}</span>{/each}
{/snippet}

{#snippet entry(member: ApiMember, level: number)}
  <svelte:element this={`h${level}`} id={member.id} data-api-member>
    <span data-api-symbol={member.symbol}>{member.symbol}</span>{member.name}{@render labels(member.labels)}<HeadingLink
      id={member.id}
    />
  </svelte:element>
  {#if member.code}
    <CodeBlock.Root><CodeBlock.Content lines={member.code} /></CodeBlock.Root>
  {/if}
  <Markdown blocks={member.doc} />
  {#each member.members as field (field.id)}
    {@render entry(field, level + 1)}
  {/each}
{/snippet}

<!-- One exported name: a second-level heading, its signature and docstring, then a third-level heading per member. -->
<!-- Each name is led by what it is (class, meth, attr) and followed by how it is declared (async, property). -->
<h2 id={object.id}>
  <span data-api-symbol={object.symbol}>{object.symbol}</span>{object.name}{@render labels(object.labels)}<HeadingLink
    id={object.id}
  />
</h2>
{#if object.code}
  <CodeBlock.Root><CodeBlock.Content lines={object.code} /></CodeBlock.Root>
{/if}
{#if object.bases.length}
  <p>Bases: {#each object.bases as base, index (base)}{index ? ", " : ""}<code>{base}</code>{/each}</p>
{/if}
<Markdown blocks={object.doc} />
{#each object.members as member (member.id)}
  {@render entry(member, MEMBER_LEVEL)}
{/each}
