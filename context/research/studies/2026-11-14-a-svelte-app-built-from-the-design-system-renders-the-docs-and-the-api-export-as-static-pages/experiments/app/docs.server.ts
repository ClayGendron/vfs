import { marked, type Token } from "marked";
import { readFileSync, readdirSync, statSync } from "node:fs";
import { join, posix } from "node:path";
import { highlightCode } from "#lib/highlighter";

export const DOCS_DIR = process.env.DOCS_DIR ?? "/Users/claygendron/Git/Repos/vfs/documentation";

export const slugOf = (text: string) => text.toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/^-|-$/g, "");

/** Every page as its route: "tutorials/use-the-cli". The landing page is a Svelte page, so index.md is left out. */
export function pages(dir = DOCS_DIR, prefix = ""): string[] {
  return readdirSync(dir).flatMap((name) => {
    const full = join(dir, name);
    if (statSync(full).isDirectory()) return pages(full, `${prefix}${name}/`);
    return name.endsWith(".md") && `${prefix}${name}` !== "index.md" ? [`${prefix}${name.slice(0, -3)}`] : [];
  });
}

/** A link written for the Markdown file tree, as the route the site serves. */
function route(href: string, page: string): string {
  if (/^[a-z]+:/i.test(href) || href.startsWith("#") || href.startsWith("/")) return href;
  const [path, anchor] = href.split("#");
  const resolved = posix.normalize(posix.join(posix.dirname(page), path)).replace(/\.md$/, "");
  return `/${resolved}${anchor ? `#${anchor}` : ""}`;
}

async function prepare(tokens: Token[], page: string): Promise<void> {
  for (const token of tokens as any[]) {
    if (token.type === "heading") token.id = slugOf(token.text);
    if (token.type === "code") token.lines = (token.lang && (await highlightCode(token.text, token.lang))) || null;
    if (token.type === "link") token.href = route(token.href, page);
    if (token.type === "image") token.href = `/images/${posix.basename(token.href)}`;
    if (token.type === "table") for (const cell of [...token.header, ...token.rows.flat()]) await prepare(cell.tokens, page);
    if (token.type === "list") for (const item of token.items) await prepare(item.tokens, page);
    if (token.tokens) await prepare(token.tokens, page);
  }
}

export async function render(markdown: string, page: string) {
  const tokens = marked.lexer(markdown);
  await prepare(tokens, page);
  return tokens;
}

export async function loadPage(page: string) {
  const tokens = await render(readFileSync(join(DOCS_DIR, `${page}.md`), "utf8"), page);
  const headings = (tokens as any[]).filter((t) => t.type === "heading" && t.depth === 2).map((t) => ({ id: t.id, text: t.text }));
  return { tokens, headings };
}
