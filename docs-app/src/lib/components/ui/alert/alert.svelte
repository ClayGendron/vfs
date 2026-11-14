<script lang="ts" module>
  import { type VariantProps, tv } from "tailwind-variants/lite";

  export const alertVariants = tv({
    base: "group/alert relative grid w-full gap-1 rounded border px-4 py-3 text-left text-sm has-data-[slot=alert-action]:pr-24 has-[>svg]:grid-cols-[auto_1fr] has-[>svg]:gap-x-3 *:[svg]:row-span-2 *:[svg]:mt-1 *:[svg]:text-current *:[svg:not([class*='size-'])]:size-4",
    variants: {
      variant: {
        default: "border-border bg-card text-card-foreground",
        destructive:
          "border-destructive bg-destructive/10 text-destructive dark:bg-destructive/20 *:data-[slot=alert-description]:text-destructive",
        success:
          "border-success bg-success/10 text-success dark:bg-success/20 *:data-[slot=alert-description]:text-success",
        caution:
          "border-border border-l-(length:--focus-width) border-l-caution bg-card text-card-foreground",
      },
    },
    defaultVariants: {
      variant: "default",
    },
  });

  export type AlertVariant = VariantProps<typeof alertVariants>["variant"];
</script>

<script lang="ts">
  import { cn, type WithElementRef } from "#lib/utils";
  import type { HTMLAttributes } from "svelte/elements";

  /**
   * The role each variant takes unless the app passes one: an error is
   * announced when inserted; success and caution are status messages; a
   * default alert is neither.
   */
  const ROLE: Record<
    NonNullable<AlertVariant>,
    "alert" | "status" | undefined
  > = {
    default: undefined,
    destructive: "alert",
    success: "status",
    caution: "status",
  };

  let {
    ref = $bindable(null),
    class: className,
    variant = "default",
    children,
    ...restProps
  }: WithElementRef<HTMLAttributes<HTMLDivElement>> & {
    variant?: AlertVariant;
  } = $props();

  // "The prop if it was given, else the variant's", so role={null} renders none.
  const role = $derived(
    "role" in restProps ? restProps.role : ROLE[variant ?? "default"],
  );
</script>

<div
  bind:this={ref}
  data-slot="alert"
  data-variant={variant}
  class={cn(alertVariants({ variant }), className)}
  {...restProps}
  {role}
>
  {@render children?.()}
</div>
