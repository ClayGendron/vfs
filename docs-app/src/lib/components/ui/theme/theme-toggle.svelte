<script lang="ts">
  import { onMount } from "svelte";
  import Moon from "phosphor-svelte/lib/Moon";
  import Sun from "phosphor-svelte/lib/Sun";
  import { Button, type ButtonProps } from "#lib/components/ui/button";
  import { theme } from "./theme.svelte.js";

  let {
    size = "icon",
    ...restProps
  }: Omit<ButtonProps, "size" | "children" | "href"> & {
    /** 48 px (`icon`, the default) or 32 px (`icon-sm`). */
    size?: "icon" | "icon-sm";
  } = $props();

  // Until hydration the server markup cannot know the theme the head script
  // chose, so the button states no pressed value rather than a wrong one, and
  // shows the light icon. `data-ready` marks the moment for tests.
  let ready = $state(false);
  onMount(() => {
    ready = true;
  });
  const dark = $derived(ready && theme.resolved === "dark");
</script>

<!--
  One control, one state: a pressed button named "Dark theme", pressed when
  dark is in force. A tri-state choice (light, dark, system) is an app's to
  compose from dropdown-menu and theme.set.
-->
<Button
  variant="ghost"
  {size}
  data-slot="theme-toggle"
  aria-label="Dark theme"
  aria-pressed={ready ? dark : undefined}
  data-ready={ready ? "" : undefined}
  onclick={() => theme.toggle()}
  {...restProps}
>
  {#if dark}
    <Moon aria-hidden="true" />
  {:else}
    <Sun aria-hidden="true" />
  {/if}
</Button>
