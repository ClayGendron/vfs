import TabIcon from "#lib/docs/TabIcon.svelte";
import { render } from "svelte/server";

export const prerender = true;

/** The browser-tab icon as a file, drawn once at build time. The framework's own comments are no part of it. */
export function GET(): Response {
  const drawn = render(TabIcon).body.replace(/<!--.*?-->/g, "").trim();
  return new Response(`${drawn}\n`, { headers: { "content-type": "image/svg+xml" } });
}
