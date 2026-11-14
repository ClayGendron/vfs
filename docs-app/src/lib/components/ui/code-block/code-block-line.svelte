<script lang="ts" module>
  import { tv, type VariantProps } from "tailwind-variants/lite";

  // Every line carries a transparent marker of the focus width, so an
  // emphasised line's coloured marker shifts no column. The three emphasised
  // variants are the opaque card step with a marker in the state colour:
  // shape and position, not a tint, which would vanish on the muted ground.
  export const codeBlockLineVariants = tv({
    base: "relative block min-h-lh -mx-4 border-l-(length:--focus-width) border-transparent px-4 group-data-[size=sm]/code-block:-mx-3 group-data-[size=sm]/code-block:px-3 in-data-numbered:col-span-2 in-data-numbered:grid in-data-numbered:grid-cols-subgrid in-data-numbered:gap-x-3 in-data-numbered:[counter-increment:line] in-data-numbered:before:min-w-6 in-data-numbered:before:text-end in-data-numbered:before:text-muted-foreground in-data-numbered:before:select-none in-data-numbered:before:content-[counter(line)] in-data-numbered:supports-[content:counter(line)_/_'']:before:content-[counter(line)_/_''] after:absolute after:top-0 after:start-1 after:select-none",
    variants: {
      variant: {
        default: "",
        highlighted: "bg-code-active-line border-primary",
        added:
          "bg-code-active-line border-success after:text-success after:content-['+']",
        removed:
          "bg-code-active-line border-destructive after:text-destructive after:content-['−']",
      },
    },
    defaultVariants: {
      variant: "default",
    },
  });

  export type CodeBlockLineVariant = VariantProps<
    typeof codeBlockLineVariants
  >["variant"];

  /** One highlighted token, such as one returned by `useHighlightedCode` or `highlightCode`. */
  export type CodeBlockLineToken = {
    content: string;
    class?: string;
  };
</script>

<script lang="ts">
  import { cn, type WithElementRef } from "#lib/utils";
  import type { HTMLAttributes } from "svelte/elements";

  let {
    ref = $bindable(null),
    class: className,
    variant = "default",
    code,
    children,
    ...restProps
  }: WithElementRef<HTMLAttributes<HTMLSpanElement>> & {
    variant?: CodeBlockLineVariant;
    /** The line as plain text, or as highlighted tokens. When it is set, `children` is ignored. */
    code?: string | CodeBlockLineToken[];
  } = $props();

  const newline = "\n";
</script>

<!--
  The line number is the `before` pseudo-element's counter, printed with an
  empty alternative text, so it is neither copied nor read. An empty line holds
  a newline so copying a selection keeps blank lines.
-->
<span
  bind:this={ref}
  data-slot="code-block-line"
  data-variant={variant}
  class={cn(codeBlockLineVariants({ variant }), className)}
  {...restProps}
>
  <span data-slot="code-block-line-content" class="min-w-0">
    {#if typeof code === "string"}
      {code || newline}
    {:else if code?.length}
      {#each code as token, index (index)}
        <span class={token.class || undefined}>{token.content}</span>
      {/each}
    {:else if code}
      {newline}
    {:else if children}
      {@render children()}
    {:else}
      {newline}
    {/if}
  </span>
</span>
