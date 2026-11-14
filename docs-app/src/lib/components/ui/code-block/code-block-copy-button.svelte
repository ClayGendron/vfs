<script lang="ts">
  import { onDestroy } from "svelte";
  import Check from "phosphor-svelte/lib/Check";
  import Copy from "phosphor-svelte/lib/Copy";
  import { Button, type ButtonProps } from "#lib/components/ui/button";
  import { Status } from "#lib/components/ui/status";
  import { cn } from "#lib/utils";

  let {
    ref = $bindable(null),
    class: className,
    code,
    variant = "ghost",
    size = "icon-sm",
    onclick,
    ...restProps
  }: Omit<ButtonProps, "onclick"> & {
    /** The text copied: the block's code. */
    code: string;
    onclick?: (e: MouseEvent) => void;
  } = $props();

  let copied = $state(false);
  let failed = $state(false);
  let timeout: ReturnType<typeof setTimeout> | undefined;

  function copy() {
    // Absent in an insecure context (http:// other than localhost): nothing to do.
    if (!navigator.clipboard) return;
    failed = false;
    navigator.clipboard
      .writeText(code)
      .then(() => {
        copied = true;
        clearTimeout(timeout);
        timeout = setTimeout(() => (copied = false), 2000);
      })
      .catch(() => {
        // The write was refused: the outcome is said, and the name stays
        // "Copy code" so the button can be tried again.
        copied = false;
        failed = true;
      });
  }

  onDestroy(() => clearTimeout(timeout));
</script>

<!--
  A 32 px ghost button whose name says what it does, then "Copied" for two
  seconds. The status region beside it is in the page from the first render,
  so the announcement is heard; a refused write says "Could not copy" there.
-->
<Button
  bind:ref
  data-slot="code-block-copy-button"
  data-copied={copied || undefined}
  {variant}
  {size}
  aria-label={copied ? "Copied" : "Copy code"}
  class={cn(className)}
  onclick={(e) => {
    onclick?.(e);
    copy();
  }}
  {...restProps}
>
  {#if copied}
    <Check aria-hidden="true" />
  {:else}
    <Copy aria-hidden="true" />
  {/if}
</Button>
<Status text={copied ? "Copied" : failed ? "Could not copy" : ""} />
