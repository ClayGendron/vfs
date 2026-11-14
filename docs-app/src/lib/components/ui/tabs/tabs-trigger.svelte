<script lang="ts">
  import { Tabs as TabsPrimitive } from "bits-ui";
  import { cn } from "#lib/utils";

  let {
    ref = $bindable(null),
    class: className,
    ...restProps
  }: TabsPrimitive.TriggerProps = $props();
</script>

<!--
  In the pill strip the active tab is a raised pill with an input border, so
  the state is a 3:1 boundary and a text change, not the fill alone. In the
  line variant it is a 2 px underline in the foreground colour.
-->
<TabsPrimitive.Trigger
  bind:ref
  data-slot="tabs-trigger"
  class={cn(
    "relative inline-flex flex-1 items-center justify-center gap-2 rounded border border-transparent px-3 text-sm font-medium whitespace-nowrap text-muted-foreground transition-[color,background-color,border-color] group-data-vertical/tabs:w-full group-data-vertical/tabs:justify-start hover:text-foreground disabled:pointer-events-none disabled:opacity-50 data-active:text-foreground [&_svg]:pointer-events-none [&_svg]:shrink-0 [&_svg:not([class*='size-'])]:size-4",
    "group-data-[variant=default]/tabs-list:h-8 group-data-[variant=default]/tabs-list:data-active:border-input group-data-[variant=default]/tabs-list:data-active:bg-card",
    "group-data-[variant=line]/tabs-list:h-12 group-data-[variant=line]/tabs-list:rounded-none group-data-[variant=line]/tabs-list:border-x-0 group-data-[variant=line]/tabs-list:border-t-0 group-data-[variant=line]/tabs-list:border-b-(length:--focus-width) group-data-[variant=line]/tabs-list:data-active:border-b-foreground",
    className,
  )}
  {...restProps}
/>
