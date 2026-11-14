<script lang="ts">
  import { cn, type WithElementRef } from "#lib/utils";
  import type { HTMLAttributes } from "svelte/elements";

  let {
    ref = $bindable(null),
    class: className,
    children,
    ...restProps
  }: WithElementRef<HTMLAttributes<HTMLDivElement>> = $props();
</script>

<!-- As the header, divided from the code above it by the groove. -->
<div
  bind:this={ref}
  data-slot="code-block-footer"
  class={cn(
    "groove flex min-w-0 shrink-0 items-center justify-between gap-2 px-4 py-2 text-muted-foreground group-data-[size=sm]/code-block:px-3 group-data-[size=sm]/code-block:py-1",
    className,
  )}
  {...restProps}
>
  {@render children?.()}
</div>
