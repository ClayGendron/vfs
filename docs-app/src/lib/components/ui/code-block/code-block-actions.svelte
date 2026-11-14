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

<!--
  A row of controls, always visible. A control that appears on hover is
  unreachable on touch and invisible until a keyboard user lands on it.
-->
<div
  bind:this={ref}
  data-slot="code-block-actions"
  class={cn("ms-auto flex shrink-0 items-center gap-1", className)}
  {...restProps}
>
  {@render children?.()}
</div>
