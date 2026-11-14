<script lang="ts">
  import { cn, type WithElementRef } from "#lib/utils";
  import type { Snippet } from "svelte";
  import type { HTMLButtonAttributes } from "svelte/elements";

  let {
    ref = $bindable(null),
    class: className,
    showOnHover = false,
    children,
    child,
    ...restProps
  }: WithElementRef<HTMLButtonAttributes> & {
    child?: Snippet<[{ props: Record<string, unknown> }]>;
    /** Shown on the row's hover or focus from md; always on a phone. */
    showOnHover?: boolean;
  } = $props();

  // A 32 px target at the row's end, centred on a 48 px row (top-2) or a 32 px one (top-0).
  const mergedProps = $derived({
    class: cn(
      "absolute end-1 top-2 flex size-8 items-center justify-center rounded text-sidebar-foreground hover:bg-sidebar-accent hover:text-sidebar-accent-foreground peer-hover/menu-button:text-sidebar-accent-foreground peer-data-[size=sm]/menu-button:top-0 group-data-[collapsible=icon]:hidden [&>svg]:size-4 [&>svg]:shrink-0",
      showOnHover &&
        "group-focus-within/menu-item:opacity-100 group-hover/menu-item:opacity-100 peer-data-active/menu-button:text-sidebar-accent-foreground aria-expanded:opacity-100 md:opacity-0",
      className,
    ),
    "data-slot": "sidebar-menu-action",
    "data-sidebar": "menu-action",
    type: "button" as const,
    ...restProps,
  });
</script>

{#if child}
  {@render child({ props: mergedProps })}
{:else}
  <button bind:this={ref} {...mergedProps}>
    {@render children?.()}
  </button>
{/if}
