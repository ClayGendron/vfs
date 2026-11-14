<script lang="ts">
  import { Dialog as SheetPrimitive } from "bits-ui";
  import { cn } from "#lib/utils";

  let {
    ref = $bindable(null),
    class: className,
    level = 2,
    ...restProps
  }: SheetPrimitive.TitleProps = $props();
</script>

<!-- A heading in the heading face; bits-ui renders role="heading" aria-level and names the dialog by it. -->
<SheetPrimitive.Title
  bind:ref
  data-slot="sheet-title"
  {level}
  class={cn("font-heading text-base font-bold", className)}
  {...restProps}
/>
