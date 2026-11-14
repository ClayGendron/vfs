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

<!-- The header sits above the code, divided from it by the groove the content draws. -->
<div
  bind:this={ref}
  data-slot="code-block-header"
  class={cn(
    "flex min-w-0 shrink-0 items-center justify-between gap-2 px-4 py-2 text-muted-foreground group-data-[size=sm]/code-block:px-3 group-data-[size=sm]/code-block:py-1 *:has-[>[data-slot=code-block-title]]:min-w-0",
    className,
  )}
  {...restProps}
>
  {@render children?.()}
</div>
