<script lang="ts">
  import { cn, type WithElementRef } from "#lib/utils";
  import { useHighlightedCode } from "#lib/hooks/use-highlighted-code.svelte.js";
  import type { HighlightedLine } from "#lib/highlighter";
  import CodeBlockLine from "./code-block-line.svelte";
  import type { HTMLAttributes } from "svelte/elements";

  let {
    ref = $bindable(null),
    class: className,
    code,
    lines,
    language,
    wrap = false,
    lineNumbers = false,
    tabindex = 0,
    children,
    ...restProps
  }: WithElementRef<HTMLAttributes<HTMLPreElement>> & {
    /** The code as text. Highlighted by the hook when `language` is given; split into lines when `lineNumbers` is set; else one text node. */
    code?: string;
    /** Pre-highlighted lines from `highlightCode`, for code rendered at prerender. Exactly one of `lines`, or `code` with `language`, drives the highlight. */
    lines?: HighlightedLine[];
    /** The language `code` is highlighted in. Without it, `code` renders plain. */
    language?: string;
    wrap?: boolean;
    lineNumbers?: boolean;
    /** 0 by default: the pre is a stop that scrolls by keyboard. Pass -1 to remove the stop. */
    tabindex?: number;
  } = $props();

  // The hook loads nothing for an empty language, so a plain block costs no Shiki.
  const highlighted = useHighlightedCode(
    () => code ?? "",
    () => language ?? "",
  );

  const rendered = $derived.by((): HighlightedLine[] | null => {
    if (lines) return lines;
    if (code === undefined) return null;
    if (language) return highlighted.current;
    if (lineNumbers) return code.replace(/\n$/, "").split("\n");
    return null;
  });
</script>

{#snippet content()}
  <code
    data-slot="code-block-code"
    class="grid min-h-lh min-w-max content-start [counter-reset:line] in-data-numbered:grid-cols-[auto_1fr] in-data-wrap:min-w-0"
  >
    {#if rendered}
      {#each rendered as line, index (index)}
        <CodeBlockLine code={line} />
      {/each}
    {:else if code !== undefined}
      {code}
    {:else}
      {@render children?.()}
    {/if}
  </code>
{/snippet}

<!--
  The one scroll container, with the scrollbar from tokens. Its focus
  indicator is drawn by the root, so it drops its own. It draws the groove
  under a header. Whitespace inside a <pre> is rendered, so its content is a
  snippet defined outside it, where Svelte trims whitespace.
-->
<!-- svelte-ignore a11y_no_noninteractive_tabindex -->
<pre
  bind:this={ref}
  data-slot="code-block-content"
  data-wrap={wrap || undefined}
  data-numbered={lineNumbers || undefined}
  dir="ltr"
  {tabindex}
  class={cn(
    "scrollbar min-h-0 min-w-0 overflow-auto px-4 py-3 text-start font-mono focus-visible:focus-ring-none group-data-[size=sm]/code-block:px-3 group-data-[size=sm]/code-block:py-2 group-has-data-[slot=code-block-header]/code-block:groove data-wrap:wrap-break-word data-wrap:whitespace-pre-wrap",
    className,
  )}
  {...restProps}>{@render content()}</pre>
