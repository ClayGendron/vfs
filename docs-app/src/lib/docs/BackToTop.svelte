<script lang="ts">
  import { Button } from "#lib/components/ui/button";
  import ArrowUp from "phosphor-svelte/lib/ArrowUp";

  // Shown once the first screen has scrolled away and the reader turns back up: never over text being read down.
  let shown = $state(false);
  let last = 0;

  function follow() {
    const at = window.scrollY;
    shown = at > window.innerHeight && at < last;
    last = at;
  }
</script>

<svelte:window onscroll={follow} />

{#if shown}
  <Button
    data-slot="docs-back-to-top"
    variant="secondary"
    size="sm"
    class="fixed bottom-6 left-1/2 z-30 -translate-x-1/2 shadow-elevation"
    onclick={() => window.scrollTo({ top: 0 })}
  >
    <ArrowUp aria-hidden="true" class="size-4" />Back to top
  </Button>
{/if}
