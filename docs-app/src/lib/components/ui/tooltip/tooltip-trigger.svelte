<script lang="ts" generics="T = never">
  import { Tooltip as TooltipPrimitive } from "bits-ui";
  import { getContext } from "svelte";

  let {
    ref = $bindable(null),
    onfocus,
    onkeydown,
    onpointerdown,
    onpointerleave,
    ...restProps
  }: TooltipPrimitive.TriggerProps<T> = $props();

  const keyboard = getContext<
    { trigger: HTMLElement | null; dismissed: boolean } | undefined
  >("pluto:tooltip");

  $effect(() => {
    if (keyboard) keyboard.trigger = ref;
  });

  type Handler<E extends Event> =
    | ((event: E & { currentTarget: EventTarget & HTMLButtonElement }) => void)
    | null
    | undefined;

  function call<E extends Event>(handler: unknown, event: E) {
    (handler as Handler<E>)?.(
      event as E & { currentTarget: EventTarget & HTMLButtonElement },
    );
  }
</script>

<!-- Escape and the pointer dismiss the tooltip for as long as focus stays. -->
<TooltipPrimitive.Trigger
  bind:ref
  data-slot="tooltip-trigger"
  onfocus={(event) => {
    if (keyboard) keyboard.dismissed = false;
    call(onfocus, event);
  }}
  onkeydown={(event) => {
    if (keyboard && event.key === "Escape") keyboard.dismissed = true;
    call(onkeydown, event);
  }}
  onpointerdown={(event) => {
    if (keyboard) keyboard.dismissed = true;
    call(onpointerdown, event);
  }}
  onpointerleave={(event) => {
    if (keyboard) keyboard.dismissed = true;
    call(onpointerleave, event);
  }}
  {...restProps}
/>
