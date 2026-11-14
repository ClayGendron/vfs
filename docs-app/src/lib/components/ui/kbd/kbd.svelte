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

<kbd
  bind:this={ref}
  data-slot="kbd"
  class={cn(
    "pointer-events-none inline-flex w-fit min-w-6 items-center justify-center gap-1 rounded border border-border bg-muted px-1 font-mono text-xs font-medium text-muted-foreground select-none [&_svg:not([class*='size-'])]:size-3",
    className,
  )}
  {...restProps}
>
  {@render children?.()}
</kbd>
