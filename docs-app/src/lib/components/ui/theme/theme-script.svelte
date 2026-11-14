<script lang="ts" module>
  /**
   * The head script, as a constant. It reads the key
   * `theme.svelte.ts` writes, else the system's preference, and sets the
   * `dark` class before first paint. Storage may be unavailable. The key is
   * written here and in `theme.svelte.ts`; the two must agree.
   */
  export const THEME_SCRIPT = [
    "(function () {",
    '  var query = "(prefers-color-scheme: dark)";',
    "  var dark;",
    "  try {",
    '    var stored = localStorage.getItem("pluto-theme");',
    '    dark = stored ? stored === "dark" : matchMedia(query).matches;',
    "  } catch (e) {",
    "    dark = matchMedia(query).matches;",
    "  }",
    '  document.documentElement.classList.toggle("dark", dark);',
    "})();",
  ].join("\n");
</script>

<script lang="ts">
  let {
    nonce,
  }: {
    /** For an app with a Content Security Policy: SvelteKit's own nonces never reach a script written through `{@html}`. */
    nonce?: string;
  } = $props();

  // A nonce is base64; anything else is dropped rather than written into markup.
  const attribute = $derived(
    nonce ? ` nonce="${nonce.replace(/[^A-Za-z0-9+/=_-]/g, "")}"` : "",
  );
  const tag = $derived(`<script${attribute}>${THEME_SCRIPT}</${"script"}>`);
</script>

<!--
  Rendered once, in the app's root layout, so the script is in the
  server-rendered head, which prerendering keeps. An item cannot edit an app's
  app.html; this is the same route mode-watcher takes. The string is a
  constant, not input.
-->
<svelte:head>
  {@html tag}
</svelte:head>
