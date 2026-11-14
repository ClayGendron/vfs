<script lang="ts">
  import List from "phosphor-svelte/lib/List";
  import { Button } from "#lib/components/ui/button";
  import { Kbd } from "#lib/components/ui/kbd";
  import * as Tooltip from "#lib/components/ui/tooltip";
  import { cn } from "#lib/utils";
  import { useSidebar } from "./context.svelte.js";
  import type { ComponentProps } from "svelte";

  let {
    ref = $bindable(null),
    class: className,
    onclick,
    ...restProps
  }: Omit<ComponentProps<typeof Button>, "href"> & {
    onclick?: (e: MouseEvent) => void;
  } = $props();

  const sidebar = useSidebar();

  // The tooltip closes when the sidebar toggles. Left open, the sheet's
  // scroll lock would close it, the tooltip item would reopen it a frame
  // later while the trigger still had focus, and its layer would then be the
  // newest focus scope, so the sheet would not take focus.
  let tooltipOpen = $state(false);
</script>

<!--
  A disclosure (aria-expanded, aria-controls naming the nav), 32 px, placed
  by the shell before the sidebar. On a phone it opens a dialog, and its
  aria-controls then names the sheet's nav, which is in the DOM only while
  the sheet is open: axe tolerates the dangling reference while aria-expanded
  is false, as it does for bits-ui's own dialog trigger. Its tooltip shows the
  shortcut. Focus stays on it after a press; the sheet returns focus to it.
-->
<Tooltip.Root bind:open={tooltipOpen}>
  <Tooltip.Trigger>
    {#snippet child({ props })}
      <Button
        {...props}
        bind:ref
        data-slot="sidebar-trigger"
        data-sidebar="trigger"
        variant="ghost"
        size="icon-sm"
        type="button"
        aria-label="Toggle sidebar"
        aria-expanded={sidebar.isMobile ? sidebar.openMobile : sidebar.open}
        aria-controls={sidebar.navId}
        aria-haspopup={sidebar.isMobile ? "dialog" : undefined}
        class={cn(className)}
        onclick={(e: MouseEvent) => {
          onclick?.(e);
          tooltipOpen = false;
          sidebar.toggle();
        }}
        {...restProps}
      >
        <List aria-hidden="true" class="size-4" />
      </Button>
    {/snippet}
  </Tooltip.Trigger>
  <Tooltip.Content side="bottom">
    Toggle sidebar <Kbd>Ctrl B</Kbd>
  </Tooltip.Content>
</Tooltip.Root>
