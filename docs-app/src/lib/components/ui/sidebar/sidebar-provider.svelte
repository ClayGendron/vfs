<script lang="ts">
  import * as Tooltip from "#lib/components/ui/tooltip";
  import { cn, type WithElementRef } from "#lib/utils";
  import { SIDEBAR_COOKIE_MAX_AGE, SIDEBAR_COOKIE_NAME } from "./constants";
  import { setSidebar } from "./context.svelte.js";
  import type { HTMLAttributes } from "svelte/elements";

  let {
    ref = $bindable(null),
    open = $bindable(true),
    onOpenChange = () => {},
    class: className,
    children,
    ...restProps
  }: WithElementRef<HTMLAttributes<HTMLDivElement>> & {
    /** The desktop state. Pass the cookie's value from a server load so the first paint is right. */
    open?: boolean;
    onOpenChange?: (open: boolean) => void;
  } = $props();

  const uid = $props.id();

  const sidebar = setSidebar({
    open: () => open,
    setOpen: (value: boolean) => {
      open = value;
      onOpenChange(value);
      // Written on every toggle, never read here: an app's +layout.server.ts
      // reads it and passes `open`.
      document.cookie = `${SIDEBAR_COOKIE_NAME}=${open}; path=/; max-age=${SIDEBAR_COOKIE_MAX_AGE}`;
    },
    navId: `${uid}-nav`,
  });
</script>

<svelte:window onkeydown={sidebar.handleShortcutKeydown} />

<!--
  A column that lays out nothing but its children, so a shell can put a header
  above the sidebar's row and a footer below it with the trigger inside the
  context. The row of Sidebar and SidebarInset is the consumer's own
  <div class="flex flex-1">. No style attribute: the widths are classes.
-->
<Tooltip.Provider delayDuration={0}>
  <div
    bind:this={ref}
    data-slot="sidebar-wrapper"
    class={cn(
      "group/sidebar-wrapper flex min-h-svh w-full flex-col",
      className,
    )}
    {...restProps}
  >
    {@render children?.()}
  </div>
</Tooltip.Provider>
