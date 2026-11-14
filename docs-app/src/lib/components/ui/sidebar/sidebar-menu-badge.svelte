<script lang="ts">
  import { cn, type WithElementRef } from "#lib/utils";
  import type { HTMLAttributes } from "svelte/elements";

  let {
    ref = $bindable(null),
    class: className,
    children,
    ...restProps
  }: WithElementRef<HTMLAttributes<HTMLElement>> = $props();
</script>

<!-- A count at the row's end, 24 px tall (not a target), centred on either row height. -->
<div
  bind:this={ref}
  data-slot="sidebar-menu-badge"
  data-sidebar="menu-badge"
  class={cn(
    "pointer-events-none absolute end-2 top-3 flex h-6 min-w-6 items-center justify-center rounded px-1 text-xs font-medium text-sidebar-foreground tabular-nums select-none peer-hover/menu-button:text-sidebar-accent-foreground peer-data-[size=sm]/menu-button:top-1 group-data-[collapsible=icon]:hidden",
    className,
  )}
  {...restProps}
>
  {@render children?.()}
</div>
