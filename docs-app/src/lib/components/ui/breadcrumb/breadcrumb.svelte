<script lang="ts">
  import { cn, type WithElementRef } from "#lib/utils";
  import type { HTMLAttributes } from "svelte/elements";

  let {
    ref = $bindable(null),
    class: className,
    label = "Breadcrumb",
    children,
    ...restProps
  }: WithElementRef<HTMLAttributes<HTMLElement>> & {
    /** The landmark's name. A page with two breadcrumbs names each. */
    label?: string;
  } = $props();
</script>

<!-- A navigation landmark holding the path as a list (APG: a nav with a label, a list, aria-current on the current page). -->
<nav
  bind:this={ref}
  data-slot="breadcrumb"
  aria-label={label}
  class={cn(className)}
  {...restProps}
>
  {@render children?.()}
</nav>
