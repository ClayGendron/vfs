<script lang="ts">
  import { getContext } from "svelte";
  import { cn, type WithElementRef } from "#lib/utils";
  import type {
    HTMLInputAttributes,
    HTMLInputTypeAttribute,
  } from "svelte/elements";

  type InputType = Exclude<HTMLInputTypeAttribute, "file">;

  type Props = WithElementRef<
    Omit<HTMLInputAttributes, "type"> &
      (
        | { type: "file"; files?: FileList }
        | { type?: InputType; files?: undefined }
      )
  >;

  /** The contract a `Field` sets under the key "pluto:field". */
  type FieldContext = {
    readonly id: string;
    readonly invalid: boolean;
    readonly describedBy: string | undefined;
  };

  let {
    ref = $bindable(null),
    value = $bindable(),
    type,
    files = $bindable(),
    class: className,
    id,
    "aria-describedby": describedBy,
    "aria-invalid": invalid,
    "data-slot": dataSlot = "input",
    ...restProps
  }: Props = $props();

  const field = getContext<FieldContext | undefined>("pluto:field");

  const wiring = $derived({
    id: id ?? field?.id,
    "aria-describedby": describedBy ?? field?.describedBy,
    "aria-invalid": invalid ?? (field?.invalid ? true : undefined),
  });

  const recipe =
    "h-12 w-full min-w-0 rounded border border-input bg-card px-3 text-base text-foreground transition-[color,background-color,border-color] placeholder:text-muted-foreground aria-invalid:border-destructive disabled:pointer-events-none disabled:cursor-not-allowed disabled:opacity-50";
</script>

{#if type === "file"}
  <input
    bind:this={ref}
    data-slot={dataSlot}
    class={cn(
      recipe,
      "file:mr-3 file:inline-flex file:h-full file:items-center file:border-0 file:bg-transparent file:text-sm file:font-medium file:text-foreground",
      className,
    )}
    type="file"
    bind:files
    bind:value
    {...wiring}
    {...restProps}
  />
{:else}
  <input
    bind:this={ref}
    data-slot={dataSlot}
    class={cn(recipe, className)}
    {type}
    bind:value
    {...wiring}
    {...restProps}
  />
{/if}
