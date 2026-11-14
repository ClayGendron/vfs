<script lang="ts">
  import * as CodeBlock from "#lib/components/ui/code-block";
  import * as Table from "#lib/components/ui/table";
  import Markdown from "./Markdown.svelte";

  let { tokens }: { tokens: any[] } = $props();
</script>

{#each tokens as token, index (index)}
  {#if token.type === "heading"}
    <svelte:element this={`h${token.depth}`} id={token.id}><Markdown tokens={token.tokens} /></svelte:element>
  {:else if token.type === "paragraph"}
    <p><Markdown tokens={token.tokens} /></p>
  {:else if token.type === "code"}
    <CodeBlock.Root><CodeBlock.Content code={token.text} lines={token.lines ?? undefined} /></CodeBlock.Root>
  {:else if token.type === "table"}
    <Table.Root>
      <Table.Header><Table.Row>{#each token.header as cell}<Table.Head><Markdown tokens={cell.tokens} /></Table.Head>{/each}</Table.Row></Table.Header>
      <Table.Body>{#each token.rows as row}<Table.Row>{#each row as cell}<Table.Cell><Markdown tokens={cell.tokens} /></Table.Cell>{/each}</Table.Row>{/each}</Table.Body>
    </Table.Root>
  {:else if token.type === "list"}
    <svelte:element this={token.ordered ? "ol" : "ul"}>{#each token.items as item}<li><Markdown tokens={item.tokens} /></li>{/each}</svelte:element>
  {:else if token.type === "blockquote"}
    <blockquote><Markdown tokens={token.tokens} /></blockquote>
  {:else if token.type === "strong"}
    <strong><Markdown tokens={token.tokens} /></strong>
  {:else if token.type === "em"}
    <em><Markdown tokens={token.tokens} /></em>
  {:else if token.type === "codespan"}
    <code>{token.text}</code>
  {:else if token.type === "link"}
    <a href={token.href}><Markdown tokens={token.tokens} /></a>
  {:else if token.type === "image"}
    <img src={token.href} alt={token.text} />
  {:else if token.type === "html"}
    {@html token.text}
  {:else if token.type === "hr"}
    <hr />
  {:else if token.type === "br"}
    <br />
  {:else if token.type === "text" || token.type === "escape"}
    {#if token.tokens}<Markdown tokens={token.tokens} />{:else}{token.text}{/if}
  {/if}
{/each}
