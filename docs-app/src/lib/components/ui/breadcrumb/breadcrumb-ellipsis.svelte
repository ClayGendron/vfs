<script lang="ts">
  import DotsThree from "phosphor-svelte/lib/DotsThree";
  import { cn, type WithElementRef, type WithoutChildren } from "#lib/utils";
  import type { HTMLAttributes } from "svelte/elements";

  let {
    ref = $bindable(null),
    class: className,
    ...restProps
  }: WithoutChildren<
    WithElementRef<HTMLAttributes<HTMLSpanElement>>
  > = $props();
</script>

<!--
  Decoration for pages left out of the path. When hidden pages exist, the app
  wraps it in a DropdownMenu.Trigger named "Show hidden pages", 32 px, with a
  menu of those pages; alone it says nothing.
-->
<span
  bind:this={ref}
  data-slot="breadcrumb-ellipsis"
  class={cn("inline-flex size-6 items-center justify-center", className)}
  {...restProps}
>
  <DotsThree aria-hidden="true" class="size-4" />
</span>
