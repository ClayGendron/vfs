<script lang="ts">
  import { cn, type WithElementRef, type WithoutChildren } from "#lib/utils";
  import type { HTMLAttributes } from "svelte/elements";

  let {
    ref = $bindable(null),
    class: className,
    ...restProps
  }: WithoutChildren<WithElementRef<HTMLAttributes<HTMLDivElement>>> = $props();
</script>

<!-- Static and hidden: the region being filled carries aria-busy. -->
<div
  bind:this={ref}
  data-slot="skeleton"
  aria-hidden="true"
  class={cn("rounded bg-muted", className)}
  {...restProps}
></div>
