<script lang="ts">
  import SpinnerIcon from "phosphor-svelte/lib/Spinner";
  import { cn } from "#lib/utils";
  import type { ComponentProps } from "svelte";

  type SpinnerProps = Omit<ComponentProps<typeof SpinnerIcon>, "role"> & {
    /**
     * Without a label the spinner is decorative: it sits inside a busy
     * control that has its own name. With one, it stands alone and its
     * label is announced from a status region.
     */
    label?: string;
  };

  let { class: className, label, ...restProps }: SpinnerProps = $props();
</script>

{#if label}
  <span data-slot="spinner" role="status" class="inline-flex items-center">
    <SpinnerIcon
      aria-hidden="true"
      class={cn("size-4 animate-spin", className)}
      {...restProps}
    />
    <span class="sr-only">{label}</span>
  </span>
{:else}
  <SpinnerIcon
    data-slot="spinner"
    aria-hidden="true"
    class={cn("size-4 animate-spin", className)}
    {...restProps}
  />
{/if}
