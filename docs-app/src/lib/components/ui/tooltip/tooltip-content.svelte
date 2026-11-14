<script lang="ts">
  import { Tooltip as TooltipPrimitive } from "bits-ui";
  import { cn } from "#lib/utils";
  import type { WithoutChildrenOrChild } from "#lib/utils";
  import TooltipPortal from "./tooltip-portal.svelte";
  import type { ComponentProps } from "svelte";

  let {
    ref = $bindable(null),
    class: className,
    // bits-ui takes a number, not a CSS value: the 4 px ladder step.
    sideOffset = 4,
    side = "top",
    children,
    portalProps,
    ...restProps
  }: TooltipPrimitive.ContentProps & {
    portalProps?: WithoutChildrenOrChild<ComponentProps<typeof TooltipPortal>>;
  } = $props();
</script>

<!--
  An inverted chip, so it stands out without elevation. It fades in and out
  over the micro budget. It is never an icon button's only name. bits-ui
  gives the content no role, so it is set here.
-->
<TooltipPortal {...portalProps}>
  <TooltipPrimitive.Content
    bind:ref
    data-slot="tooltip-content"
    role="tooltip"
    {sideOffset}
    {side}
    class={cn(
      "z-50 inline-flex w-fit max-w-xs origin-(--bits-tooltip-content-transform-origin) items-center gap-2 rounded bg-foreground px-3 py-2 text-xs text-background data-open:animate-enter data-[state=delayed-open]:animate-enter data-[state=instant-open]:animate-enter data-closed:animate-exit",
      className,
    )}
    {...restProps}
  >
    {@render children?.()}
  </TooltipPrimitive.Content>
</TooltipPortal>
