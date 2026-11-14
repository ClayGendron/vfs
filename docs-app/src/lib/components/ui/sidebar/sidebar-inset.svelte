<script lang="ts">
  import { cn, type WithElementRef } from "#lib/utils";
  import type { HTMLAttributes } from "svelte/elements";
  import { useSidebar } from "./context.svelte.js";

  let {
    ref = $bindable(null),
    element = "main",
    label,
    class: className,
    children,
    ...restProps
  }: WithElementRef<HTMLAttributes<HTMLElement>> & {
    /** `main` for a shell (the skip link's target); `div` renders a labelled region for a page that already has a main. */
    element?: "main" | "div";
    /** The region's name, when `element` is `div`. */
    label?: string;
  } = $props();

  // The groove is drawn only while a sidebar is beside the page: not when it
  // is collapsed off-canvas to 0 px, and not on a phone, where the sidebar is
  // a sheet. Outside a provider there is nothing to read, and the groove stays.
  const sidebar = useSidebar();
  const groove = $derived(sidebar ? sidebar.beside : true);
</script>

<!--
  The page beside the sidebar. It owns the vertical groove on its start edge
  (the hairline, then the light inside it) while the sidebar is beside it.
  As a main it is id="main" with tabindex="-1", so the shell's skip link
  lands focus in every browser.
-->
<svelte:element
  this={element}
  bind:this={ref}
  id={element === "main" ? "main" : undefined}
  tabindex={element === "main" ? -1 : undefined}
  role={element === "div" ? "region" : undefined}
  aria-label={element === "div" ? label : undefined}
  data-slot="sidebar-inset"
  class={cn(
    "relative flex min-w-0 flex-1 flex-col bg-background",
    groove && "groove-s",
    className,
  )}
  {...restProps}
>
  {@render children?.()}
</svelte:element>
