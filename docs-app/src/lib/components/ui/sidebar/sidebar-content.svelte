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

<!--
  The scroll box between header and footer, with the token scrollbar and no
  stop of its own: its rows are stops that scroll it into view, and the nav
  names it. It scrolls as icons too, so no row is out of the pointer's reach.
-->
<div
  bind:this={ref}
  data-slot="sidebar-content"
  data-sidebar="content"
  class={cn(
    "flex min-h-0 flex-1 flex-col gap-2 overflow-auto scrollbar",
    className,
  )}
  {...restProps}
>
  {@render children?.()}
</div>
