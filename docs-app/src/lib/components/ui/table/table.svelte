<script lang="ts">
  import { cn, type WithElementRef } from "#lib/utils";
  import type { HTMLTableAttributes } from "svelte/elements";

  let {
    ref = $bindable(null),
    class: className,
    label,
    children,
    ...restProps
  }: WithElementRef<HTMLTableAttributes> & {
    /**
     * With a label, the scrolling container is a named region that keyboard
     * users can focus and scroll; without one it adds no stop.
     */
    label?: string;
  } = $props();
</script>

<!-- A labelled region is focusable so keyboard users can scroll it. -->
<!-- svelte-ignore a11y_no_noninteractive_tabindex -->
<div
  data-slot="table-container"
  class="relative w-full overflow-x-auto"
  role={label ? "region" : undefined}
  aria-label={label}
  tabindex={label ? 0 : undefined}
>
  <table
    bind:this={ref}
    data-slot="table"
    class={cn("w-full caption-bottom text-sm", className)}
    {...restProps}
  >
    {@render children?.()}
  </table>
</div>
