<script lang="ts">
  import * as CodeBlock from "#lib/components/ui/code-block";
  import Markdown from "#lib/Markdown.svelte";
  let { data } = $props();
</script>

<article class="prose">
  <h1 id={`vfs.${data.name}`}>vfs.{data.name}</h1>
  <p>{data.kind}</p>
  {#if data.signature}<CodeBlock.Root><CodeBlock.Content code={`${data.name}${data.signature}`} /></CodeBlock.Root>{/if}
  <Markdown tokens={data.doc} />
  {#each data.members as member}
    <h2 id={`vfs.${data.name}.${member.name}`}>{member.name}</h2>
    {#if member.signature}<CodeBlock.Root><CodeBlock.Content code={`${member.name}${member.signature}`} /></CodeBlock.Root>{/if}
    {#if member.annotation}<p><code>{member.annotation}</code>{#if member.value} = <code>{member.value}</code>{/if}</p>{/if}
    <Markdown tokens={member.doc} />
  {/each}
</article>
