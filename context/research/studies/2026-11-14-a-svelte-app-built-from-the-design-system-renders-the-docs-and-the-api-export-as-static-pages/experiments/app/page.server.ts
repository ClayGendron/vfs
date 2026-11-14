import { loadPage, pages } from "#lib/docs.server";
import api from "#lib/api.json";

export const entries = () => [{ slug: "" }, ...pages().map((slug) => ({ slug }))];

export async function load({ params }) {
  if (params.slug === "") return { index: [...pages(), ...api.names.map((name: string) => `reference/api/${name}`)] };
  return { page: await loadPage(params.slug) };
}
