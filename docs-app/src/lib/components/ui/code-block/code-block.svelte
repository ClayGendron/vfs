<script lang="ts" module>
  import { tv, type VariantProps } from "tailwind-variants/lite";

  export const codeBlockVariants = tv({
    // The root draws the focus indicator for its pre, so overflow-hidden
    // cannot clip it. The ground is the code
    // ground, with no border: an inset is told by its ground. The code ground
    // is the muted inset everywhere but inside an ink surface, where it goes
    // flush with the surface as the editor does; a block that
    // should stay an inset there passes `class="bg-muted"`.
    base: "group/code-block relative flex w-full min-w-0 flex-col overflow-hidden rounded bg-code-background text-sm has-[[data-slot=code-block-content]:focus-visible]:focus-ring data-[size=sm]:text-xs",
    variants: {
      variant: {
        default: "text-foreground",
        // State told by colour: the app gives a destructive block a visible
        // label, such as "Error output", in its header or beside it.
        destructive: "text-destructive",
      },
    },
    defaultVariants: {
      variant: "default",
    },
  });

  export type CodeBlockVariant = VariantProps<
    typeof codeBlockVariants
  >["variant"];
  export type CodeBlockSize = "default" | "sm";
</script>

<script lang="ts">
  import { cn, type WithElementRef } from "#lib/utils";
  import type { HTMLAttributes } from "svelte/elements";

  let {
    ref = $bindable(null),
    class: className,
    variant = "default",
    size = "default",
    children,
    ...restProps
  }: WithElementRef<HTMLAttributes<HTMLDivElement>> & {
    variant?: CodeBlockVariant;
    size?: CodeBlockSize;
  } = $props();
</script>

<div
  bind:this={ref}
  data-slot="code-block"
  data-variant={variant}
  data-size={size}
  class={cn(codeBlockVariants({ variant }), className)}
  {...restProps}
>
  {@render children?.()}
</div>
