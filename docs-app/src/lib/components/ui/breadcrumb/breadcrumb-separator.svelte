<script lang="ts">
  import CaretRight from "phosphor-svelte/lib/CaretRight";
  import { cn, type WithElementRef } from "#lib/utils";
  import type { HTMLLiAttributes } from "svelte/elements";

  let {
    ref = $bindable(null),
    class: className,
    children,
    ...restProps
  }: WithElementRef<HTMLLiAttributes> = $props();
</script>

<!-- Decoration, out of the tree: a caret that turns under rtl, or the app's own mark. -->
<li
  bind:this={ref}
  data-slot="breadcrumb-separator"
  role="presentation"
  aria-hidden="true"
  class={cn("inline-flex items-center", className)}
  {...restProps}
>
  {#if children}
    {@render children?.()}
  {:else}
    <CaretRight class="size-4 rtl:rotate-180" />
  {/if}
</li>
