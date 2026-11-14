<script lang="ts" module>
  /** The edge the panel is fixed to, in writing direction: `start` and `end`, or `top` and `bottom`. */
  export type SheetSide = "start" | "end" | "top" | "bottom";
</script>

<script lang="ts">
  import { Dialog as SheetPrimitive } from "bits-ui";
  import X from "phosphor-svelte/lib/X";
  import { Button } from "#lib/components/ui/button";
  import { cn, type WithoutChildrenOrChild } from "#lib/utils";
  import SheetOverlay from "./sheet-overlay.svelte";
  import SheetPortal from "./sheet-portal.svelte";
  import type { ComponentProps, Snippet } from "svelte";

  let {
    ref = $bindable(null),
    class: className,
    side = "end",
    label,
    showCloseButton = true,
    portalProps,
    children,
    ...restProps
  }: WithoutChildrenOrChild<SheetPrimitive.ContentProps> & {
    portalProps?: WithoutChildrenOrChild<ComponentProps<typeof SheetPortal>>;
    side?: SheetSide;
    /** The sheet's name when it holds no `SheetTitle`. One of the two is required. */
    label?: string;
    showCloseButton?: boolean;
    children: Snippet;
  } = $props();
</script>

<!--
  A modal dialog fixed to one edge: role="dialog" aria-modal="true", named by
  its title (bits-ui wires aria-labelledby) or by `label`, focus to the first
  tabbable inside, trapped and looped, returned to the trigger on close. 288
  px wide on a side and at most the viewport tall on a top or bottom edge;
  the elevation draws the edge, so no border. It fades, as every overlay
  does; no slide. A long body scrolls inside. The close button is 32 px and
  the last stop.
-->
<SheetPortal {...portalProps}>
  <SheetOverlay />
  <SheetPrimitive.Content
    bind:ref
    data-slot="sheet-content"
    data-side={side}
    aria-label={label}
    class={cn(
      "fixed z-50 flex flex-col gap-6 overflow-y-auto bg-popover p-6 text-popover-foreground shadow-elevation scrollbar data-open:animate-enter data-closed:animate-exit data-[side=bottom]:inset-x-0 data-[side=bottom]:bottom-0 data-[side=bottom]:h-auto data-[side=bottom]:max-h-full data-[side=end]:inset-y-0 data-[side=end]:end-0 data-[side=end]:h-full data-[side=end]:w-2xs data-[side=end]:max-w-full data-[side=start]:inset-y-0 data-[side=start]:start-0 data-[side=start]:h-full data-[side=start]:w-2xs data-[side=start]:max-w-full data-[side=top]:inset-x-0 data-[side=top]:top-0 data-[side=top]:h-auto data-[side=top]:max-h-full",
      className,
    )}
    {...restProps}
  >
    {@render children?.()}
    {#if showCloseButton}
      <SheetPrimitive.Close data-slot="sheet-close">
        {#snippet child({ props })}
          <Button
            variant="ghost"
            size="icon-sm"
            aria-label="Close"
            class="absolute top-4 end-4"
            {...props}
          >
            <X aria-hidden="true" class="size-4" />
          </Button>
        {/snippet}
      </SheetPrimitive.Close>
    {/if}
  </SheetPrimitive.Content>
</SheetPortal>
