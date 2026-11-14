<script lang="ts" generics="T = never">
  import { Tooltip as TooltipPrimitive } from "bits-ui";
  import { setContext } from "svelte";

  let {
    open = $bindable(false),
    onOpenChange,
    ...restProps
  }: TooltipPrimitive.RootProps<T> = $props();

  /**
   * Shared with `TooltipTrigger`: its element, and whether the person
   * dismissed the tooltip (Escape, or the pointer) since focus arrived.
   */
  const keyboard: { trigger: HTMLElement | null; dismissed: boolean } = {
    trigger: null,
    dismissed: false,
  };
  setContext("pluto:tooltip", keyboard);

  /**
   * bits-ui closes an open tooltip on any scroll around its trigger, and Tab
   * to a trigger below the fold scrolls the page, so the tooltip would vanish
   * while focus stays. If it closes while the trigger still has keyboard focus
   * and no one dismissed it, open it again on the next frame (SC 1.4.13).
   */
  function handleOpenChange(next: boolean) {
    onOpenChange?.(next);
    if (next) return;
    requestAnimationFrame(() => {
      const trigger = keyboard.trigger;
      if (
        !open &&
        !keyboard.dismissed &&
        trigger &&
        trigger === document.activeElement &&
        trigger.matches(":focus-visible")
      )
        open = true;
    });
  }
</script>

<TooltipPrimitive.Root
  bind:open
  onOpenChange={handleOpenChange}
  {...restProps}
/>
