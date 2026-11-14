<script lang="ts">
  import { Skeleton } from "#lib/components/ui/skeleton";
  import { cn, type WithElementRef } from "#lib/utils";
  import type { HTMLAttributes } from "svelte/elements";

  let {
    ref = $bindable(null),
    class: className,
    showIcon = false,
    index = 0,
    children,
    ...restProps
  }: WithElementRef<HTMLAttributes<HTMLElement>> & {
    showIcon?: boolean;
    /** The row's place in its list: it picks one of four widths, the same on the server and the client. */
    index?: number;
  } = $props();

  // Four widths by index, in place of shadcn-svelte's random style attribute,
  // which
  // differed between the server's render and the client's.
  const WIDTHS = ["max-w-1/2", "max-w-2/3", "max-w-3/4", "max-w-full"];
  const width = $derived(WIDTHS[Math.abs(index) % WIDTHS.length]);
</script>

<div
  bind:this={ref}
  data-slot="sidebar-menu-skeleton"
  data-sidebar="menu-skeleton"
  class={cn("flex h-12 items-center gap-2 rounded px-3", className)}
  {...restProps}
>
  {#if showIcon}
    <Skeleton class="size-4" data-sidebar="menu-skeleton-icon" />
  {/if}
  <Skeleton class={cn("h-4 flex-1", width)} data-sidebar="menu-skeleton-text" />
  {@render children?.()}
</div>
