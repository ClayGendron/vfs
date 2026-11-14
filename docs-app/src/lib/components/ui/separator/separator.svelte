<script lang="ts">
  import { Separator as SeparatorPrimitive } from "bits-ui";
  import { cn } from "#lib/utils";

  let {
    ref = $bindable(null),
    class: className,
    // Decorative unless the app says it means something: bits-ui's own default is false.
    decorative = true,
    "data-slot": dataSlot = "separator",
    ...restProps
  }: SeparatorPrimitive.RootProps = $props();
</script>

<SeparatorPrimitive.Root
  bind:ref
  data-slot={dataSlot}
  {decorative}
  class={cn(
    "shrink-0 data-horizontal:groove data-horizontal:w-full data-horizontal:pt-(--line-width) data-vertical:self-stretch data-vertical:border-l data-vertical:border-border",
    className,
  )}
  {...restProps}
/>
