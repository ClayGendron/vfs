import { routes } from "#lib/docs/content.server";
import { SITE_URL } from "#lib/docs/site";

export const prerender = true;

/** Every page's address, for a search engine: the landing page, then the navigation's pages in its order. */
export function GET(): Response {
  const addresses = ["/", ...routes()].map((route) => `  <url><loc>${SITE_URL}${route}</loc></url>`);
  const body = [
    '<?xml version="1.0" encoding="UTF-8"?>',
    '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">',
    ...addresses,
    "</urlset>",
    "",
  ].join("\n");
  return new Response(body, { headers: { "content-type": "application/xml" } });
}
