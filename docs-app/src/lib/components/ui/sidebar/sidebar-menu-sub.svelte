<script lang="ts">
  import { cn, type WithElementRef } from "#lib/utils";
  import type { HTMLAttributes } from "svelte/elements";

  let {
    ref = $bindable(null),
    class: className,
    children,
    ...restProps
  }: WithElementRef<HTMLAttributes<HTMLUListElement>> = $props();
</script>

<!-- Sub-rows under a row, along a hairline in the groove's colour; gone as icons. -->
<ul
  bind:this={ref}
  data-slot="sidebar-menu-sub"
  data-sidebar="menu-sub"
  class={cn(
    "mx-4 flex min-w-0 flex-col gap-1 border-s border-groove-line px-2 py-0 group-data-[collapsible=icon]:hidden",
    className,
  )}
  {...restProps}
>
  {@render children?.()}
</ul>
