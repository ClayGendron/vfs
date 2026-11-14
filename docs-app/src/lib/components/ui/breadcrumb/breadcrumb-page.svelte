<script lang="ts">
  import { cn, type WithElementRef } from "#lib/utils";
  import type { HTMLAttributes } from "svelte/elements";

  let {
    ref = $bindable(null),
    class: className,
    children,
    ...restProps
  }: WithElementRef<HTMLAttributes<HTMLSpanElement>> = $props();
</script>

<!--
  The current page: a span with aria-current and nothing else.
  shadcn-svelte's role="link" aria-disabled announced "link, disabled", a false promise.
-->
<span
  bind:this={ref}
  data-slot="breadcrumb-page"
  aria-current="page"
  class={cn("text-foreground", className)}
  {...restProps}
>
  {@render children?.()}
</span>
