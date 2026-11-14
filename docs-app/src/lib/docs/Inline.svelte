<script lang="ts">
  import Inline from "./Inline.svelte";
  import { NEW_TAB } from "./site";
  import type { Inline as InlineNode } from "./types";

  let { nodes }: { nodes: InlineNode[] } = $props();
</script>

{#each nodes as node, index (index)}
  {#if node.type === "text"}
    {node.text}
  {:else if node.type === "strong"}
    <strong><Inline nodes={node.children} /></strong>
  {:else if node.type === "em"}
    <em><Inline nodes={node.children} /></em>
  {:else if node.type === "code"}
    <code>{node.text}</code>
  {:else if node.type === "link" && node.external}
    <!-- A link that leaves the site opens in a new tab, and names the sentence that tells a screen reader so. -->
    <a href={node.href} {...NEW_TAB}><Inline nodes={node.children} /></a>
  {:else if node.type === "link"}
    <a href={node.href}><Inline nodes={node.children} /></a>
  {:else if node.type === "break"}
    <br />
  {:else if node.type === "svg"}
    <!-- The markup of a diagram file in this repository, placed inline so it takes the page's tokens. -->
    {@html node.markup}
  {/if}
{/each}
