import { existsSync, readdirSync, readFileSync, statSync } from "node:fs";
import { join, relative, resolve } from "node:path";
import type { ApiExport, NavTab, PageLink } from "./types";

/** A page, the navigation or the export is wrong; the message names the place, and the build stops on it. */
export class DocsError extends Error {}

// The pages live outside the app, in the repository's documentation folder; a test names another.
export const DOCS_DIR = resolve(process.env.DOCS_DIR ?? "../documentation");

// The export the Python script writes. It is never stored: `scripts/docs.sh export` remakes it.
export const API_FILE = resolve(process.env.DOCS_API ?? "src/lib/generated/api.json");

const NAVIGATION = "navigation.json";

/** A page as the navigation file lists it: its route, or its route with the name the navigation shows for it. */
type NavEntry = string | { route: string; title: string };
const FENCE = /^\s*(```|~~~)/;

/** A page's path inside the documentation folder, as an error names it. */
export function nameOf(file: string): string {
  return `documentation/${relative(DOCS_DIR, file).split("\\").join("/")}`;
}

/** Every Markdown page under the documentation folder: its route, then its file. */
export function pageFiles(dir = DOCS_DIR, prefix = ""): Map<string, string> {
  const found = new Map<string, string>();
  for (const name of readdirSync(dir).sort()) {
    const full = join(dir, name);
    if (statSync(full).isDirectory()) {
      for (const [route, file] of pageFiles(full, `${prefix}/${name}`)) found.set(route, file);
    } else if (name.endsWith(".md")) {
      // A file named index.md is served at its folder's own route.
      const route = name === "index.md" ? prefix : `${prefix}/${name.slice(0, -3)}`;
      if (route === "") {
        throw new DocsError(`${nameOf(full)}: the landing page is a Svelte page, so the folder holds no index.md`);
      }
      found.set(route, full);
    }
  }
  return found;
}

/** A page's title: its one first-level heading. */
export function titleOf(file: string): string {
  const titles: string[] = [];
  let fenced = false;
  for (const line of readFileSync(file, "utf8").split("\n")) {
    if (FENCE.test(line)) fenced = !fenced;
    else if (!fenced && line.startsWith("# ")) titles.push(line.slice(2).trim());
  }
  if (titles.length !== 1) {
    throw new DocsError(`${nameOf(file)}: a page has one first-level heading, and this one has ${titles.length}`);
  }
  return titles[0];
}

/** The navigation, checked against the folder: every page on exactly one list, every listed page a file. */
export function navigation(): NavTab[] {
  const path = join(DOCS_DIR, NAVIGATION);
  if (!existsSync(path)) throw new DocsError(`documentation/${NAVIGATION} does not exist`);
  const raw = JSON.parse(readFileSync(path, "utf8")) as {
    tabs: { title: string; groups: { title: string | null; pages: NavEntry[] }[] }[];
  };
  const files = pageFiles();
  const listed = new Set<string>();
  const problems: string[] = [];
  const link = (entry: NavEntry): PageLink => {
    const route = typeof entry === "string" ? entry : entry.route;
    const file = files.get(route);
    if (listed.has(route)) problems.push(`${route} is listed twice`);
    listed.add(route);
    if (!file) {
      problems.push(`${route} is listed and has no file`);
      return { route, title: route };
    }
    // The page's own title is checked either way; the navigation shows the entry's name when it gives one.
    const title = titleOf(file);
    return { route, title: typeof entry === "string" ? title : entry.title };
  };
  const tabs = raw.tabs.map((tab) => {
    const groups = tab.groups.map((group) => ({ title: group.title, pages: group.pages.map(link) }));
    // A tab links to its first page.
    return { title: tab.title, href: groups[0]?.pages[0]?.route ?? "/", groups };
  });
  for (const [route, file] of files) {
    if (!listed.has(route)) problems.push(`${nameOf(file)} is on no list`);
  }
  if (problems.length) throw new DocsError(`documentation/${NAVIGATION}: ${problems.join("; ")}`);
  return tabs;
}

/** Every route the navigation lists, in its order. */
export function routes(tabs: NavTab[] = navigation()): string[] {
  return tabs.flatMap((tab) => tab.groups.flatMap((group) => group.pages.map((page) => page.route)));
}

/** The export of the public API, read fresh so a new export shows without a restart. */
export function api(): ApiExport {
  if (!existsSync(API_FILE)) {
    throw new DocsError(`${API_FILE} does not exist: run scripts/docs.sh export`);
  }
  return JSON.parse(readFileSync(API_FILE, "utf8")) as ApiExport;
}
