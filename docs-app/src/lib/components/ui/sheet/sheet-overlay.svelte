<script lang="ts">
  import { Dialog as SheetPrimitive } from "bits-ui";
  import { cn } from "#lib/utils";

  let {
    ref = $bindable(null),
    class: className,
    ...restProps
  }: SheetPrimitive.OverlayProps = $props();
</script>

<!-- The scrim, unblurred, fading with the content. -->
<SheetPrimitive.Overlay
  bind:ref
  data-slot="sheet-overlay"
  class={cn(
    "fixed inset-0 z-50 bg-scrim data-open:animate-enter data-closed:animate-exit",
    className,
  )}
  {...restProps}
/>
