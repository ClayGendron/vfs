<script lang="ts" module>
  import { tv, type VariantProps } from "tailwind-variants/lite";

  /**
   * A row: 48 px (default) or 32 px (sm). Hover is the sidebar's accent
   * inset; the current row keeps the inset and adds a primary start edge, so
   * the two states differ by shape. Every row carries the edge transparent,
   * so the text never shifts. As icons, a 32 px square.
   */
  export const sidebarMenuButtonVariants = tv({
    base: "peer/menu-button group/menu-button flex w-full items-center gap-2 overflow-hidden rounded border-s-(length:--focus-width) border-transparent px-3 text-start text-sm transition-[width,height,padding] duration-(--motion-micro) hover:bg-sidebar-accent hover:text-sidebar-accent-foreground active:bg-sidebar-accent active:text-sidebar-accent-foreground aria-[current=page]:border-sidebar-primary aria-[current=page]:bg-sidebar-accent aria-[current=page]:text-sidebar-accent-foreground data-[state=open]:hover:bg-sidebar-accent data-[state=open]:hover:text-sidebar-accent-foreground group-has-data-[sidebar=menu-action]/menu-item:pe-8 group-data-[collapsible=icon]:size-8! group-data-[collapsible=icon]:p-2! disabled:pointer-events-none disabled:opacity-50 aria-disabled:pointer-events-none aria-disabled:opacity-50 [&_svg]:size-4 [&_svg]:shrink-0 [&>span:last-child]:truncate",
    variants: {
      variant: {
        default: "",
        // The start width is written again after the shorthand, which would
        // otherwise drop it in the merge.
        outline:
          "border border-input border-s-(length:--focus-width) bg-background hover:border-foreground aria-[current=page]:border-s-sidebar-primary",
      },
      size: {
        default: "h-12",
        sm: "h-8",
      },
    },
    defaultVariants: {
      variant: "default",
      size: "default",
    },
  });

  export type SidebarMenuButtonVariant = VariantProps<
    typeof sidebarMenuButtonVariants
  >["variant"];
  export type SidebarMenuButtonSize = VariantProps<
    typeof sidebarMenuButtonVariants
  >["size"];
</script>

<script lang="ts">
  import { mergeProps } from "bits-ui";
  import * as Tooltip from "#lib/components/ui/tooltip";
  import {
    cn,
    type WithElementRef,
    type WithoutChildrenOrChild,
  } from "#lib/utils";
  import { useSidebar } from "./context.svelte.js";
  import type { ComponentProps, Snippet } from "svelte";
  import type { HTMLAttributes } from "svelte/elements";

  let {
    ref = $bindable(null),
    class: className,
    children,
    child,
    variant = "default",
    size = "default",
    isActive = false,
    tooltipContent,
    tooltipContentProps,
    ...restProps
  }: WithElementRef<HTMLAttributes<HTMLButtonElement>, HTMLButtonElement> & {
    /** The current page: sets aria-current="page", the inset and the primary edge. */
    isActive?: boolean;
    variant?: SidebarMenuButtonVariant;
    size?: SidebarMenuButtonSize;
    /** The row's name as icons, shown by a tooltip on the right. */
    tooltipContent?: Snippet | string;
    tooltipContentProps?: WithoutChildrenOrChild<
      ComponentProps<typeof Tooltip.Content>
    >;
    child?: Snippet<[{ props: Record<string, unknown> }]>;
  } = $props();

  const sidebar = useSidebar();

  const buttonProps = $derived({
    class: cn(sidebarMenuButtonVariants({ variant, size }), className),
    "data-slot": "sidebar-menu-button",
    "data-sidebar": "menu-button",
    "data-size": size,
    "data-active": isActive ? "" : undefined,
    "aria-current": isActive ? ("page" as const) : undefined,
    ...restProps,
  });

  // The tooltip names an icon: it exists only as icons on desktop. Never in
  // the sheet, where an invisible tooltip would take the first Escape.
  const tooltip = $derived(
    !!tooltipContent && sidebar.state === "collapsed" && !sidebar.isMobile,
  );
</script>

{#snippet Button({ props }: { props?: Record<string, unknown> })}
  <!-- The row's own slot and data win over the tooltip trigger's; handlers chain. -->
  {@const mergedProps = mergeProps(props ?? {}, buttonProps)}
  {#if child}
    {@render child({ props: mergedProps })}
  {:else}
    <button bind:this={ref} {...mergedProps}>
      {@render children?.()}
    </button>
  {/if}
{/snippet}

{#if !tooltip}
  {@render Button({})}
{:else}
  <Tooltip.Root>
    <Tooltip.Trigger>
      {#snippet child({ props })}
        {@render Button({ props })}
      {/snippet}
    </Tooltip.Trigger>
    <Tooltip.Content side="right" align="center" {...tooltipContentProps}>
      {#if typeof tooltipContent === "string"}
        {tooltipContent}
      {:else if tooltipContent}
        {@render tooltipContent()}
      {/if}
    </Tooltip.Content>
  </Tooltip.Root>
{/if}
