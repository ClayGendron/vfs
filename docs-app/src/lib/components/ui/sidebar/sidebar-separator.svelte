<script lang="ts">
  import { Separator } from "#lib/components/ui/separator";
  import { cn } from "#lib/utils";
  import type { ComponentProps } from "svelte";

  let {
    ref = $bindable(null),
    class: className,
    ...restProps
  }: ComponentProps<typeof Separator> = $props();
</script>

<!-- The separator's groove, inset by the sidebar's padding. -->
<Separator
  bind:ref
  data-slot="sidebar-separator"
  data-sidebar="separator"
  class={cn("mx-2 w-auto", className)}
  {...restProps}
/>
