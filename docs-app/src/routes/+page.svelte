<script lang="ts">
  import { Button } from "#lib/components/ui/button";
  import { SITE_DESCRIPTION, SITE_URL } from "#lib/docs/site";
  import type { NavTab } from "#lib/docs/types";

  let { data }: { data: { tabs: NavTab[] } } = $props();

  // What each tab is for, in a sentence; a tab with no sentence here shows its name alone.
  const purpose: Record<string, string> = {
    Tutorials: "Learn VFS step by step. Start here if you are new.",
    "How-to Guides": "Get a specific job done, such as loading a folder of files.",
    Reference: "Look up the facts, such as what each access level allows.",
    Explanation: "Understand why VFS is built the way it is.",
  };

  // The first tab is the front door: its first page is where a reader starts, and its second is the overview.
  const start = $derived(data.tabs[0]?.groups[0]?.pages ?? []);
  const sections = $derived(data.tabs.slice(1));
</script>

<svelte:head>
  <title>VFS Docs</title>
  <meta name="description" content={SITE_DESCRIPTION} />
  <link rel="canonical" href={`${SITE_URL}/`} />
</svelte:head>

<!-- The same centred width as the header, so the headline starts under the wordmark. -->
<div class="mx-auto max-w-7xl px-5 pt-16">
  <section>
    <h1 class="max-w-3xl text-5xl font-bold tracking-display">Governed Data Access for AI Agents</h1>
    <p class="mt-6 max-w-2xl text-muted-foreground">
      VFS is a virtual file system that gives AI agents one governed namespace for data and tools. AI agents navigate
      it with commands they already know, and every command is checked against permissions before it runs.
    </p>
    <div class="mt-8 flex flex-wrap gap-3">
      {#if start[0]}
        <Button href={start[0].route}>{start[0].title}</Button>
      {/if}
      {#if start[1]}
        <Button href={start[1].route} variant="secondary">Read the Overview</Button>
      {/if}
    </div>
  </section>

  {#if sections.length}
    <section class="mt-20">
      <h2 class="text-2xl font-bold tracking-section">Explore the Docs</h2>
      <ul class="mt-6 grid max-w-5xl gap-4 sm:grid-cols-2">
        {#each sections as tab (tab.title)}
          <li class="rounded bg-card p-6">
            <a href={tab.href} class="font-heading font-bold underline underline-offset-4">{tab.title}</a>
            {#if purpose[tab.title]}
              <p class="mt-2 text-sm text-muted-foreground">{purpose[tab.title]}</p>
            {/if}
          </li>
        {/each}
      </ul>
    </section>
  {/if}
</div>
