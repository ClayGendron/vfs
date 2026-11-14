<script lang="ts">
  import { cn, type WithElementRef } from "#lib/utils";
  import type { HTMLAttributes } from "svelte/elements";

  let {
    ref = $bindable(null),
    class: className,
    text = "",
    visible = false,
    ...restProps
  }: WithElementRef<HTMLAttributes<HTMLDivElement>> & {
    /** What the region says. Empty by default. Set it to announce; set "" to clear. */
    text?: string;
    /** Shown on screen as well as announced. Default false: visually hidden. */
    visible?: boolean;
  } = $props();
</script>

<!--
  A polite live region, rendered empty from the first render, so it is in the
  page before its text changes. A region announces only if it was there before
  its text changed: mount it first, then set the text. Setting the same text
  twice is not announced again; put a working message between results.
-->
<div
  bind:this={ref}
  data-slot="status"
  role="status"
  aria-live="polite"
  aria-atomic="true"
  class={cn(!visible && "sr-only", className)}
  {...restProps}
>
  {text}
</div>
