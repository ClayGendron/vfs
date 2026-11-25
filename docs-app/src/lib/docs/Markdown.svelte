<script lang="ts">
  import * as CodeBlock from "#lib/components/ui/code-block";
  import * as Table from "#lib/components/ui/table";
  import ApiBlock from "./ApiBlock.svelte";
  import GlossaryTerm from "./GlossaryTerm.svelte";
  import HeadingLink from "./HeadingLink.svelte";
  import Inline from "./Inline.svelte";
  import Markdown from "./Markdown.svelte";
  import type { Block } from "./types";

  let { blocks }: { blocks: Block[] } = $props();
</script>

<!-- One block, one component: a fenced block is the design system's CodeBlock and a table its Table. -->
{#each blocks as block, index (index)}
  {#if block.type === "heading"}
    <svelte:element this={`h${block.depth}`} id={block.id}>
      <Inline nodes={block.children} />{#if block.id}<HeadingLink id={block.id} />{/if}
    </svelte:element>
  {:else if block.type === "paragraph"}
    <p><Inline nodes={block.children} /></p>
  {:else if block.type === "plain"}
    <Inline nodes={block.children} />
  {:else if block.type === "code"}
    <CodeBlock.Root>
      <CodeBlock.Actions class="absolute end-2 top-2">
        <CodeBlock.CopyButton code={block.text} />
      </CodeBlock.Actions>
      <CodeBlock.Content code={block.text} lines={block.lines ?? undefined} />
    </CodeBlock.Root>
  {:else if block.type === "table"}
    <Table.Root>
      <Table.Header>
        <Table.Row>
          {#each block.header as cell, column (column)}
            <Table.Head><Inline nodes={cell} /></Table.Head>
          {/each}
        </Table.Row>
      </Table.Header>
      <Table.Body>
        {#each block.rows as row, line (line)}
          <Table.Row>
            {#each row as cell, column (column)}
              <Table.Cell class="whitespace-normal"><Inline nodes={cell} /></Table.Cell>
            {/each}
          </Table.Row>
        {/each}
      </Table.Body>
    </Table.Root>
  {:else if block.type === "list"}
    <svelte:element this={block.ordered ? "ol" : "ul"}>
      {#each block.items as item, position (position)}
        <li><Markdown blocks={item} /></li>
      {/each}
    </svelte:element>
  {:else if block.type === "quote"}
    <blockquote><Markdown blocks={block.children} /></blockquote>
  {:else if block.type === "rule"}
    <hr />
  {:else if block.type === "api"}
    <ApiBlock object={block.object} />
  {:else if block.type === "term"}
    <GlossaryTerm term={block.term} />
  {/if}
{/each}
