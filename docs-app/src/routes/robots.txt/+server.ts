import { SITE_URL } from "#lib/docs/site";

export const prerender = true;

/** Every page may be read, and the sitemap is named, which is how a search engine finds it. */
export function GET(): Response {
  const body = `User-agent: *\nAllow: /\n\nSitemap: ${SITE_URL}/sitemap.xml\n`;
  return new Response(body, { headers: { "content-type": "text/plain" } });
}
