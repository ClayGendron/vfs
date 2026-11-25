<script lang="ts">
  import "../app.css";
  import "#lib/docs/site.css";
  import { onMount } from "svelte";
  import { page } from "$app/state";
  import * as Sidebar from "#lib/components/ui/sidebar";
  import { ThemeScript, ThemeToggle } from "#lib/components/ui/theme";
  import ArrowUpRight from "phosphor-svelte/lib/ArrowUpRight";
  import BackToTop from "#lib/docs/BackToTop.svelte";
  import { CONTENT_ID, NEW_TAB, NEW_TAB_ID, REPOSITORY, SITE_DESCRIPTION, SITE_NAME } from "#lib/docs/site";
  import TableOfContents from "#lib/docs/TableOfContents.svelte";
  import type { NavTab } from "#lib/docs/types";
  import type { Snippet } from "svelte";

  let { data, children }: { data: { tabs: NavTab[]; commit: string; built: string }; children: Snippet } = $props();

  // A documentation page says which tab it is under; the landing page and the not-found page are under none.
  const current = $derived<NavTab | null>(page.data.tab === undefined ? null : data.tabs[page.data.tab]);

  // The header and the three columns share one centred width, so the panels never reach the window's sides.
  const frame = "mx-auto w-full max-w-7xl";

  // The current page's row has no coloured start edge. Its fill is the hovered row's too, so its name is
  // also set heavier: that weight is what tells the current row from a hovered one.
  const row = "aria-[current=page]:border-transparent aria-[current=page]:font-medium";

  // Runs once the whole page has hydrated with every listener attached. The browser tests wait for `<html data-ready>`.
  onMount(() => {
    document.documentElement.dataset.ready = "";
  });
</script>

<svelte:head>
  <ThemeScript />
</svelte:head>

<!-- The first stop of the Tab key: one press and Enter pass the header and the navigation. Shown only when focused. -->
<a href={`#${CONTENT_ID}`} class="docs-skip">Skip to content</a>

<!-- What every link that leaves the site names, so a screen reader says it once for each. -->
<span id={NEW_TAB_ID} hidden>Opens in a new tab</span>

<Sidebar.Provider>
  <!-- The header stays at the top of the window. Its height includes its own line, so the columns below start exactly where they stick. -->
  <header data-slot="docs-header" class="sticky top-0 z-40 h-(--size-bar) shrink-0 bg-background groove-b">
    <div class={[frame, "flex h-full items-center gap-4 px-5"]}>
      <Sidebar.Trigger class="md:hidden" />
      <!-- The drawer's button needs a script. With scripts off, the same links are a list that opens without one. -->
      <noscript>
        <details data-slot="docs-menu-noscript" class="md:hidden">
          <summary class="cursor-pointer font-mono text-xs tracking-eyebrow text-muted-foreground lowercase">menu</summary>
          <nav aria-label="Pages" class="docs-menu-noscript-list">
            <ul>
              {#each data.tabs as tab (tab.title)}
                <li><a href={tab.href} aria-current={tab === current ? "page" : undefined}>{tab.title}</a></li>
              {/each}
            </ul>
            {#if current}
              {#each current.groups as group, index (index)}
                {#if group.title}<p>{group.title}</p>{/if}
                <ul>
                  {#each group.pages as link (link.route)}
                    <li>
                      <a href={link.route} aria-current={link.route === page.data.page?.route ? "page" : undefined}>
                        {link.title}
                      </a>
                    </li>
                  {/each}
                </ul>
              {/each}
            {/if}
          </nav>
        </details>
      </noscript>
      <a href="/" class="flex items-baseline gap-2 no-underline" aria-label="{SITE_NAME} Docs, home">
        <span class="vfs-wordmark">{SITE_NAME}</span><span class="vfs-wordmark-site">Docs</span>
      </a>
      <nav aria-label="Sections" class="ms-6 hidden items-center gap-6 text-sm md:flex">
        {#each data.tabs as tab (tab.title)}
          <a
            href={tab.href}
            aria-current={tab === current ? "page" : undefined}
            class="text-muted-foreground underline-offset-4 hover:text-foreground aria-[current=page]:text-foreground aria-[current=page]:underline"
          >
            {tab.title}
          </a>
        {/each}
      </nav>
      <div class="ms-auto flex items-center gap-2">
        <!-- The arrow says the link leaves the site, as the new tab and the sentence it names do. -->
        <a
          href={REPOSITORY}
          {...NEW_TAB}
          class="hidden items-center gap-1 text-sm text-muted-foreground hover:text-foreground sm:inline-flex"
        >
          GitHub<ArrowUpRight aria-hidden="true" class="size-3" />
        </a>
        <ThemeToggle size="icon-sm" />
      </div>
    </div>
  </header>

  <div class={[frame, "flex flex-1"]}>
    <!-- The left navigation: the chosen tab's pages. On a phone it is a drawer that also lists the tabs. -->
    <Sidebar.Root
      label="Pages"
      class={[
        "top-(--size-bar) h-[calc(100svh-var(--size-bar))] overscroll-contain",
        current ? "" : "md:hidden",
      ]}
    >
      <Sidebar.Content class="overscroll-contain pt-6">
        <Sidebar.Group class="md:hidden">
          <Sidebar.GroupLabel>sections</Sidebar.GroupLabel>
          <Sidebar.GroupContent>
            <Sidebar.Menu>
              {#each data.tabs as tab (tab.title)}
                <Sidebar.MenuItem>
                  <Sidebar.MenuButton size="sm" isActive={tab === current} class={row}>
                    {#snippet child({ props })}
                      <a href={tab.href} {...props}>{tab.title}</a>
                    {/snippet}
                  </Sidebar.MenuButton>
                </Sidebar.MenuItem>
              {/each}
            </Sidebar.Menu>
          </Sidebar.GroupContent>
        </Sidebar.Group>
        {#if current}
          {#each current.groups as group, index (index)}
            <Sidebar.Group>
              {#if group.title}
                <Sidebar.GroupLabel>{group.title}</Sidebar.GroupLabel>
              {/if}
              <Sidebar.GroupContent>
                <Sidebar.Menu>
                  {#each group.pages as link (link.route)}
                    <Sidebar.MenuItem>
                      <Sidebar.MenuButton size="sm" isActive={link.route === page.data.page?.route} class={row}>
                        {#snippet child({ props })}
                          <a href={link.route} {...props}><span class="truncate">{link.title}</span></a>
                        {/snippet}
                      </Sidebar.MenuButton>
                    </Sidebar.MenuItem>
                  {/each}
                </Sidebar.Menu>
              </Sidebar.GroupContent>
            </Sidebar.Group>
          {/each}
        {/if}
      </Sidebar.Content>
    </Sidebar.Root>

    <div class="flex min-w-0 flex-1 flex-col">
      <!-- Where the skip link lands. It takes focus from a link and is no stop of the Tab key itself. -->
      <main id={CONTENT_ID} tabindex="-1" class="min-w-0 flex-1 outline-none">
        {@render children()}
      </main>
      <footer class="mt-16 flex flex-wrap items-end justify-between gap-6 px-5 py-8 text-sm groove">
        <div>
          <span class="vfs-wordmark">{SITE_NAME}</span>
          <p class="mt-2 text-muted-foreground">{SITE_DESCRIPTION}</p>
        </div>
        <dl class="flex gap-6 font-mono text-xs text-muted-foreground">
          {#if data.commit}
            <div><dt>commit</dt><dd class="text-foreground">{data.commit}</dd></div>
          {/if}
          <div><dt>built</dt><dd class="text-foreground">{data.built}</dd></div>
          <div>
            <dt>source</dt>
            <dd>
              <a href={REPOSITORY} {...NEW_TAB} class="text-foreground underline">
                {REPOSITORY.replace("https://", "")}
              </a>
            </dd>
          </div>
        </dl>
      </footer>
    </div>

    <!-- A sibling of the page's column, so it reaches the bottom of the page and never has to move. -->
    {#if page.data.page}
      <TableOfContents entries={page.data.page.toc} />
    {/if}
  </div>
  <BackToTop />
</Sidebar.Provider>
