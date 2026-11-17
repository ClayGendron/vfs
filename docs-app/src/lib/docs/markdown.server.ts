import { marked, type Token } from "marked";
import { existsSync, readFileSync } from "node:fs";
import { dirname, posix, resolve } from "node:path";
import { highlightCode, type HighlightedLine } from "#lib/highlighter";
import { api, DocsError, nameOf, navigation, pageFiles } from "./content.server";
import type {
  ApiExport,
  ApiMember,
  ApiObject,
  ApiSymbol,
  Block,
  ExportedMember,
  ExportedName,
  ExportedTerm,
  GlossaryTerm,
  Inline,
  Page,
  TermRow,
  TocEntry,
} from "./types";

// The package the API pages document, and the line that pulls one of its names into a page.
const PACKAGE = "vfs";
const API_BLOCK = new RegExp(`^::: ${PACKAGE}\\.(\\S+)$`);

// A signature longer than this is drawn one parameter to a line.
const SIGNATURE_WIDTH = 80;

const XML_PROLOG = /^\s*<\?xml[^>]*\?>\s*/;

/** What one render is of, and what it has seen so far. */
type Context = {
  /** The place an error names: a page's path, or an object's id. */
  where: string;
  /** The page's route, for resolving its links; null inside a docstring. */
  route: string | null;
  /** The page's file, for resolving its images; null inside a docstring. */
  file: string | null;
  anchors: Set<string>;
  toc: TocEntry[];
  export: ApiExport | null;
};

/** A heading's anchor: lower case, each run of other characters one hyphen, none at either end. */
export function anchorOf(text: string): string {
  return text
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/^-|-$/g, "");
}

/** A Markdown page, ready to draw. */
export async function renderPage(route: string): Promise<Page> {
  const file = pageFiles().get(route);
  if (!file) throw new DocsError(`${route} has no file under documentation/`);
  const context: Context = { where: nameOf(file), route, file, anchors: new Set(), toc: [], export: null };
  const drawn = await blocksOf(marked.lexer(readFileSync(file, "utf8")), context);
  const blocks = route === GLOSSARY_ROUTE ? withTerms(drawn, context) : drawn;
  const titles = blocks.filter((block) => block.type === "heading" && block.depth === 1);
  if (titles.length !== 1) {
    throw new DocsError(`${context.where}: a page has one first-level heading, and this one has ${titles.length}`);
  }
  const title = titles[0].type === "heading" ? plainText(titles[0].children) : "";
  return { route, title, description: descriptionOf(blocks, title), blocks, toc: context.toc };
}

// The longest description a search result shows in full.
const DESCRIPTION_LENGTH = 160;

/** A page's first paragraph as plain text, cut at a word; the title when the page has no paragraph. */
function descriptionOf(blocks: Block[], title: string): string {
  const first = blocks.find((block) => block.type === "paragraph");
  const text = (first?.type === "paragraph" ? plainText(first.children) : title).replace(/\s+/g, " ").trim();
  if (text.length <= DESCRIPTION_LENGTH) return text;
  const cut = text.slice(0, DESCRIPTION_LENGTH - 1);
  // Cut at the last whole word, and drop a comma or a colon the cut leaves hanging before the ellipsis.
  return `${cut.slice(0, cut.lastIndexOf(" ")).replace(/[\s,;:.]+$/, "")}…`;
}

// ---------------------------------------------------------------------------
// Blocks
// ---------------------------------------------------------------------------

async function blocksOf(tokens: Token[], context: Context): Promise<Block[]> {
  const blocks: Block[] = [];
  for (const token of tokens as any[]) {
    switch (token.type) {
      case "space":
        break;
      case "heading":
        blocks.push(headingOf(token, context));
        break;
      case "paragraph": {
        const pulled = context.route ? API_BLOCK.exec(token.text.trim()) : null;
        if (pulled) blocks.push({ type: "api", object: await apiObject(pulled[1], context) });
        else blocks.push({ type: "paragraph", children: inlinesOf(token.tokens, context) });
        break;
      }
      case "text":
        // A tight list item's own words: inline text with no paragraph around it.
        blocks.push({ type: "plain", children: inlinesOf(token.tokens ?? [token], context) });
        break;
      case "code":
        if (token.codeBlockStyle === "indented") throw refused("code with no fence", context);
        blocks.push({ type: "code", text: token.text, lines: await highlighted(token.text, token.lang ?? "") });
        break;
      case "table":
        blocks.push({
          type: "table",
          header: token.header.map((cell: any) => inlinesOf(cell.tokens, context)),
          rows: token.rows.map((row: any[]) => row.map((cell) => inlinesOf(cell.tokens, context))),
        });
        break;
      case "list": {
        const items: Block[][] = [];
        for (const item of token.items) {
          if (item.task) throw refused("task list item", context);
          items.push(await blocksOf(item.tokens, context));
        }
        blocks.push({ type: "list", ordered: token.ordered, items });
        break;
      }
      case "blockquote":
        blocks.push({ type: "quote", children: await blocksOf(token.tokens, context) });
        break;
      case "hr":
        blocks.push({ type: "rule" });
        break;
      default:
        throw refused(token.type, context);
    }
  }
  return blocks;
}

function headingOf(token: any, context: Context): Block {
  const children = inlinesOf(token.tokens, context);
  // A heading inside a docstring is a bold line: the page's outline belongs to the page.
  if (context.route === null) return { type: "paragraph", children: [{ type: "strong", children }] };
  const id = anchorOf(token.text);
  claim(id, context);
  if (token.depth === 2 || token.depth === 3) {
    context.toc.push({ id, text: plainText(children), depth: token.depth });
  }
  return { type: "heading", depth: token.depth, id, children };
}

function claim(id: string, context: Context): void {
  if (context.anchors.has(id)) throw new DocsError(`${context.where}: two headings share the anchor "${id}"`);
  context.anchors.add(id);
}

function refused(kind: string, context: Context): DocsError {
  return new DocsError(`${context.where}: the renderer does not draw "${kind}"`);
}

async function highlighted(text: string, language: string) {
  return language ? await highlightCode(text, language) : null;
}

// ---------------------------------------------------------------------------
// Inline text
// ---------------------------------------------------------------------------

function inlinesOf(tokens: Token[], context: Context): Inline[] {
  const inlines: Inline[] = [];
  for (const token of tokens as any[]) {
    switch (token.type) {
      case "text":
      case "escape":
        if (token.tokens) inlines.push(...inlinesOf(token.tokens, context));
        else inlines.push({ type: "text", text: token.text });
        break;
      case "strong":
        inlines.push({ type: "strong", children: inlinesOf(token.tokens, context) });
        break;
      case "em":
        inlines.push({ type: "em", children: inlinesOf(token.tokens, context) });
        break;
      case "codespan":
        inlines.push({ type: "code", text: token.text });
        break;
      case "link":
        inlines.push({
          type: "link",
          href: routeOf(token.href, context),
          // A link to another site: the renderer opens it in a new tab and says so.
          external: /^https?:\/\//i.test(token.href),
          children: inlinesOf(token.tokens, context),
        });
        break;
      case "image":
        inlines.push({ type: "svg", markup: diagram(token.href, context) });
        break;
      case "br":
        inlines.push({ type: "break" });
        break;
      default:
        throw refused(token.type, context);
    }
  }
  return inlines;
}

/** A link written for the Markdown file tree, as the route the site serves. */
function routeOf(href: string, context: Context): string {
  if (context.route === null || /^[a-z][a-z0-9+.-]*:/i.test(href) || href.startsWith("#") || href.startsWith("/")) {
    return href;
  }
  const [path, anchor] = href.split("#");
  // A link is relative to the page's folder, and an index.md is served at its folder's own route.
  const folder = context.file?.endsWith("index.md") ? context.route : posix.dirname(context.route);
  let route = posix.normalize(posix.join(folder, path)).replace(/\.md$/, "");
  if (route.endsWith("/index")) route = route.slice(0, -"/index".length);
  return anchor ? `${route}#${anchor}` : route;
}

/** A local SVG file's own markup, so the diagram takes the page's colours and typefaces. */
function diagram(href: string, context: Context): string {
  if (context.file === null || !href.endsWith(".svg") || /^[a-z][a-z0-9+.-]*:/i.test(href)) {
    throw new DocsError(`${context.where}: the only image a page may hold is a local SVG file, not ${href}`);
  }
  const file = resolve(dirname(context.file), href);
  if (!existsSync(file)) throw new DocsError(`${context.where}: the image ${href} does not exist`);
  return readFileSync(file, "utf8").replace(XML_PROLOG, "").trim();
}

function plainText(inlines: Inline[]): string {
  return inlines
    .map((inline) => ("text" in inline ? inline.text : "children" in inline ? plainText(inline.children) : ""))
    .join("");
}

// ---------------------------------------------------------------------------
// Glossary terms
// ---------------------------------------------------------------------------

// The glossary page, and the label that opens the one part a term writes by hand.
const GLOSSARY_ROUTE = "/reference/glossary";
const TYPES_LABEL = "Types:";

/** The glossary's blocks with each term's Types list replaced by the term's rows: what it names, then what the build found. */
function withTerms(blocks: Block[], context: Context): Block[] {
  context.export ??= api();
  const exported = context.export.glossary ?? {};
  const places = placesByRoute();
  const drawn = new Set<string>();
  let term: string | null = null;
  const result = blocks.map((block): Block => {
    if (block.type === "heading" && block.depth === 2) term = plainText(block.children);
    const note = block.type === "list" ? typesNote(block.items) : null;
    if (term === null || note === null) return block;
    const found = exported[term];
    if (!found) throw new DocsError(`${context.where}: the term "${term}" is not in the export; run scripts/docs.sh export`);
    drawn.add(term);
    return { type: "term", term: termOf(found, note, places) };
  });
  const missing = Object.keys(exported).filter((name) => !drawn.has(name));
  if (missing.length) {
    throw new DocsError(`${context.where}: the export holds terms the page does not draw: ${missing.join(", ")}`);
  }
  return result;
}

/** What a list writes after its Types label, when the list is a term's Types part; null for any other list. */
function typesNote(items: Block[][]): Inline[] | null {
  const first = items.length === 1 ? items[0][0] : undefined;
  if (first?.type !== "plain") return null;
  const [label, ...rest] = first.children;
  if (label?.type !== "strong" || plainText(label.children) !== TYPES_LABEL) return null;
  const [lead, ...tail] = rest;
  // The words begin after the label's own space, with their first letter raised: "none." reads "None." in a row.
  if (lead?.type !== "text") return rest;
  const text = lead.text.trimStart();
  return [{ type: "text", text: text.charAt(0).toUpperCase() + text.slice(1) }, ...tail];
}

function termOf(found: ExportedTerm, note: Inline[], places: Map<string, Place>): GlossaryTerm {
  const named = (cited: ExportedName): TermRow => {
    const route = cited.page === null ? null : routeOfPage(cited.page);
    const place = route === null ? undefined : places.get(route);
    return {
      name: cited.name,
      href: route === null ? null : `${route}#${cited.id}`,
      where: place ? `${place.tab} › ${place.title}` : null,
      code: true,
    };
  };
  const related = [...new Set([...found.mentions, ...found.mentioned_by])];
  return {
    note: found.types.length ? [] : note,
    types: found.types.map(named),
    // A row of code is its name alone: the name already says which class it is on.
    code: found.code.map((cited) => ({ ...named(cited), where: null })),
    documentation: found.documentation.map((page) => {
      const route = routeOfPage(page.page);
      return { name: page.title, href: route, where: places.get(route)?.tab ?? null, code: false };
    }),
    related: related.map((name) => ({ name, href: `#${anchorOf(name)}`, where: null, code: false })),
  };
}

/** Where a page sits in the navigation: its tab, and the name the navigation shows for it. */
type Place = { tab: string; title: string };

function placesByRoute(): Map<string, Place> {
  const places = new Map<string, Place>();
  for (const tab of navigation()) {
    for (const group of tab.groups) {
      for (const page of group.pages) places.set(page.route, { tab: tab.title, title: page.title });
    }
  }
  return places;
}

/** A page's path inside the documentation folder, as the route the site serves it at. */
function routeOfPage(page: string): string {
  const route = `/${page.replace(/\.md$/, "")}`;
  return route.endsWith("/index") ? route.slice(0, -"/index".length) : route;
}

// ---------------------------------------------------------------------------
// API blocks
// ---------------------------------------------------------------------------

async function apiObject(name: string, context: Context): Promise<ApiObject> {
  context.export ??= api();
  const object = context.export.objects[name];
  if (!object) {
    throw new DocsError(`${context.where}: ${PACKAGE}.${name} is not in the export; run scripts/docs.sh export`);
  }
  const id = `${PACKAGE}.${name}`;
  const symbol = symbolOf(object.kind, false);
  claim(id, context);
  context.toc.push({ id, text: name, depth: 2, symbol });
  const members: ApiMember[] = [];
  for (const member of object.members) {
    const drawn = await apiMember(member, id, object.kind === "class", context);
    context.toc.push({ id: drawn.id, text: drawn.name, depth: 3, symbol: drawn.symbol });
    members.push(drawn);
  }
  return {
    name,
    id,
    symbol,
    labels: object.labels,
    bases: object.bases,
    code: object.signature === null ? null : await declaration(name, object),
    doc: await docstring(object.doc, id),
    members,
  };
}

/** One member, and under it the fields of a class that a module lists and no page pulls in by name. */
async function apiMember(member: ExportedMember, parent: string, inClass: boolean, context: Context): Promise<ApiMember> {
  const id = `${parent}.${member.name}`;
  claim(id, context);
  const members: ApiMember[] = [];
  for (const field of member.members) members.push(await apiMember(field, id, true, context));
  return {
    name: member.name,
    id,
    symbol: symbolOf(member.kind, inClass),
    labels: member.labels,
    code: await declaration(member.name, member),
    doc: await docstring(member.doc, id),
    members,
  };
}

/** The short word shown before a name: a function inside a class is a method. */
function symbolOf(kind: string, inClass: boolean): ApiSymbol {
  if (kind === "function") return inClass ? "meth" : "func";
  if (kind === "attribute") return "attr";
  if (kind === "module") return "mod";
  return "class";
}

/** A docstring's Markdown as blocks. The same token check as a page's, named by the object. */
async function docstring(markdown: string, id: string): Promise<Block[]> {
  const context: Context = { where: id, route: null, file: null, anchors: new Set(), toc: [], export: null };
  return blocksOf(marked.lexer(markdown), context);
}

/** A name's signature, or an attribute's type and value, as highlighted Python. */
async function declaration(
  name: string,
  member: { signature: string | null; annotation?: string | null; value?: string | null },
) {
  if (member.signature !== null) {
    // A signature is highlighted as the definition it is part of, and the two ends added for that are cut off.
    const code = `${name}${broken(member.signature)}`;
    const lines = await highlightCode(`${DEFINITION}${code}${BODY}`, "python");
    return lines ? cut(lines, DEFINITION.length, BODY.length) : code.split("\n");
  }
  if (!member.annotation && !member.value) return null;
  const code = `${name}${member.annotation ? `: ${member.annotation}` : ""}${member.value ? ` = ${member.value}` : ""}`;
  return (await highlightCode(code, "python")) ?? code.split("\n");
}

const DEFINITION = "def ";
const BODY = ": ...";

/** Highlighted lines without their first *start* characters and their last *end* characters. */
function cut(lines: HighlightedLine[], start: number, end: number): HighlightedLine[] {
  const trimmed = lines.map((line) => (typeof line === "string" ? line : line.map((token) => ({ ...token }))));
  const first = trimmed[0];
  if (typeof first === "string") trimmed[0] = first.slice(start);
  else {
    while (start > 0 && first.length) {
      const taken = Math.min(start, first[0].content.length);
      first[0].content = first[0].content.slice(taken);
      start -= taken;
      if (!first[0].content) first.shift();
    }
  }
  const last = trimmed[trimmed.length - 1];
  if (typeof last === "string") trimmed[trimmed.length - 1] = last.slice(0, last.length - end);
  else {
    while (end > 0 && last.length) {
      const token = last[last.length - 1];
      const taken = Math.min(end, token.content.length);
      token.content = token.content.slice(0, token.content.length - taken);
      end -= taken;
      if (!token.content) last.pop();
    }
  }
  return trimmed;
}

/** A long signature with one parameter to a line; a short one as it is. */
function broken(signature: string): string {
  if (signature.length <= SIGNATURE_WIDTH) return signature;
  const close = closing(signature);
  const parameters = splitTopLevel(signature.slice(1, close));
  if (parameters.length < 2) return signature;
  return `(\n${parameters.map((parameter) => `    ${parameter},`).join("\n")}\n${signature.slice(close)}`;
}

/** The index of the bracket that closes a signature's parameter list. */
function closing(signature: string): number {
  let depth = 0;
  for (let index = 0; index < signature.length; index += 1) {
    if ("([{".includes(signature[index])) depth += 1;
    else if (")]}".includes(signature[index]) && (depth -= 1) === 0) return index;
  }
  return signature.length - 1;
}

/** A parameter list cut at the commas that sit outside every bracket and every string. */
function splitTopLevel(text: string): string[] {
  const parts: string[] = [];
  let depth = 0;
  let quote: string | null = null;
  let start = 0;
  for (let index = 0; index < text.length; index += 1) {
    const char = text[index];
    if (quote) {
      if (char === quote && text[index - 1] !== "\\") quote = null;
    } else if (char === '"' || char === "'") quote = char;
    else if ("([{".includes(char)) depth += 1;
    else if (")]}".includes(char)) depth -= 1;
    else if (char === "," && depth === 0) {
      parts.push(text.slice(start, index).trim());
      start = index + 1;
    }
  }
  const last = text.slice(start).trim();
  return last ? [...parts, last] : parts;
}
