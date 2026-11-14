<script lang="ts">
  import { cn, type WithElementRef } from "#lib/utils";
  import type { Snippet } from "svelte";
  import type { HTMLButtonAttributes } from "svelte/elements";

  let {
    ref = $bindable(null),
    class: className,
    children,
    child,
    ...restProps
  }: WithElementRef<HTMLButtonAttributes> & {
    child?: Snippet<[{ props: Record<string, unknown> }]>;
  } = $props();

  // A 32 px target on the group label's row; it names itself with aria-label.
  const mergedProps = $derived({
    class: cn(
      "absolute end-2 top-2 flex size-8 items-center justify-center rounded text-sidebar-foreground hover:bg-sidebar-accent hover:text-sidebar-accent-foreground group-data-[collapsible=icon]:hidden [&>svg]:size-4 [&>svg]:shrink-0",
      className,
    ),
    "data-slot": "sidebar-group-action",
    "data-sidebar": "group-action",
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
