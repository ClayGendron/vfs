<script lang="ts">
  import { cn, type WithElementRef } from "#lib/utils";
  import type { Snippet } from "svelte";
  import type { HTMLAnchorAttributes } from "svelte/elements";

  let {
    ref = $bindable(null),
    class: className,
    href = undefined,
    child,
    children,
    ...restProps
  }: WithElementRef<HTMLAnchorAttributes> & {
    /** Renders a framework link in place of the anchor, with these props. */
    child?: Snippet<[{ props: HTMLAnchorAttributes }]>;
  } = $props();

  // At least 24 px tall, a target. The colour alone transitions: a
  // transition on every colour would fade the focus mark in too, and it must
  // be there at once.
  const attrs = $derived({
    "data-slot": "breadcrumb-link",
    class: cn(
      "inline-flex min-h-6 items-center transition-[color] hover:text-foreground",
      className,
    ),
    href,
    ...restProps,
  });
</script>

{#if child}
  {@render child({ props: attrs })}
{:else}
  <a bind:this={ref} {...attrs}>
    {@render children?.()}
  </a>
{/if}
