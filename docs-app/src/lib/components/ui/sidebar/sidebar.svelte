<script lang="ts">
  import * as Sheet from "#lib/components/ui/sheet";
  import { cn, type WithElementRef } from "#lib/utils";
  import { useSidebar } from "./context.svelte.js";
  import type { HTMLAttributes } from "svelte/elements";

  let {
    ref = $bindable(null),
    label = "Main",
    collapsible = "offcanvas",
    class: className,
    children,
    ...restProps
  }: WithElementRef<HTMLAttributes<HTMLElement>> & {
    /** The landmark's name. A shell with a second nav names each. */
    label?: string;
    /** `offcanvas` leaves the page and goes inert; `icon` shrinks to a 48 px column; `none` never collapses. */
    collapsible?: "offcanvas" | "icon" | "none";
  } = $props();

  const sidebar = useSidebar();
  const collapsed = $derived(sidebar.state === "collapsed");
  $effect(() => {
    sidebar.collapsible = collapsible;
  });
</script>

<!--
  A navigation landmark on the paper ground, set apart by the groove its
  inset owns: no tint, no border, no shadow. On desktop it is a sticky,
  full-height flex child of the consumer's row, never fixed, whose width is
  its state: 256 px open, 48 px as icons, 0 off-canvas, over the micro
  budget. Off-canvas it is inert, so its rows leave the tab order and the
  accessibility tree while the state persists. Below 768 px it is a sheet
  named "Sidebar", 288 px wide, with no tooltip on a row. The inner column
  keeps its width while the landmark clips, so nothing reflows mid-motion.
-->
{#if collapsible === "none"}
  <nav
    bind:this={ref}
    id={sidebar.navId}
    aria-label={label}
    data-slot="sidebar"
    data-sidebar="sidebar"
    data-state="expanded"
    class={cn(
      "sticky top-0 flex h-svh w-3xs shrink-0 flex-col self-start overflow-hidden bg-sidebar text-sidebar-foreground",
      className,
    )}
    {...restProps}
  >
    {@render children?.()}
  </nav>
{:else if sidebar.isMobile}
  <Sheet.Root
    bind:open={() => sidebar.openMobile, (v) => sidebar.setOpenMobile(v)}
  >
    <Sheet.Content
      side="start"
      data-mobile="true"
      class="w-2xs gap-0 bg-sidebar p-0 pt-12 text-sidebar-foreground"
    >
      <Sheet.Header class="sr-only">
        <Sheet.Title>Sidebar</Sheet.Title>
        <Sheet.Description>The site's navigation.</Sheet.Description>
      </Sheet.Header>
      <nav
        bind:this={ref}
        id={sidebar.navId}
        aria-label={label}
        data-slot="sidebar"
        data-sidebar="sidebar"
        data-state="expanded"
        class={cn("flex h-full min-h-0 flex-col", className)}
        {...restProps}
      >
        {@render children?.()}
      </nav>
    </Sheet.Content>
  </Sheet.Root>
{:else}
  <nav
    bind:this={ref}
    id={sidebar.navId}
    aria-label={label}
    data-slot="sidebar"
    data-sidebar="sidebar"
    data-state={sidebar.state}
    data-collapsible={collapsed ? collapsible : ""}
    inert={collapsed && collapsible === "offcanvas" ? true : undefined}
    class={cn(
      "group sticky top-0 hidden h-svh w-3xs shrink-0 flex-col self-start overflow-hidden bg-sidebar text-sidebar-foreground transition-[width] duration-(--motion-micro) ease-linear data-[collapsible=icon]:w-12 data-[collapsible=offcanvas]:w-0 md:flex",
      className,
    )}
    {...restProps}
  >
    <div
      data-slot="sidebar-inner"
      class="flex h-full w-3xs shrink-0 flex-col group-data-[collapsible=icon]:w-12"
    >
      {@render children?.()}
    </div>
  </nav>
{/if}
