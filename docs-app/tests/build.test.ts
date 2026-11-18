// The static build: what it writes for the real pages, and what it refuses.
// Each case runs `vite build` once, into a folder of its own, so the cases run one after another.
import { afterAll, beforeAll, describe, expect, setDefaultTimeout, test } from "bun:test";
import { existsSync, mkdirSync, mkdtempSync, readdirSync, readFileSync, rmSync, statSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { dirname, join, relative, resolve } from "node:path";

const APP = resolve(import.meta.dir, "..");
const REAL_PAGES = resolve(APP, "../documentation");
const REAL_EXPORT = join(APP, "src/lib/generated/api.json");
const scratch = mkdtempSync(join(tmpdir(), "vfs-docs-"));

// A case is one whole build, which takes seconds: the runner's own limit would cut a slow one short.
setDefaultTimeout(180_000);

type Built = { code: number; output: string; out: string };

/** One build of the app over a folder of pages and an export. */
function build(pages: string, exported: string): Built {
  const out = mkdtempSync(join(scratch, "out-"));
  const run = Bun.spawnSync(["bun", "--bun", "vite", "build"], {
    cwd: APP,
    env: { ...process.env, DOCS_DIR: pages, DOCS_API: exported, DOCS_OUT: out },
    stdout: "pipe",
    stderr: "pipe",
  });
  return { code: run.exitCode, output: run.stdout.toString() + run.stderr.toString(), out };
}

/** A folder of pages written from a map of path to text, with a navigation that lists every page once. */
function pages(files: Record<string, string>, navigation?: object): string {
  const root = mkdtempSync(join(scratch, "pages-"));
  for (const [path, text] of Object.entries(files)) {
    mkdirSync(dirname(join(root, path)), { recursive: true });
    writeFileSync(join(root, path), text);
  }
  const routes = Object.keys(files)
    .filter((path) => path.endsWith(".md"))
    .map((path) => `/${path.slice(0, -3)}`);
  const listed = navigation ?? { tabs: [{ title: "Pages", groups: [{ title: null, pages: routes }] }] };
  writeFileSync(join(root, "navigation.json"), JSON.stringify(listed));
  return root;
}

/** An export written from a map of name to object. */
function exported(objects: Record<string, object> = {}): string {
  const path = join(mkdtempSync(join(scratch, "export-")), "api.json");
  writeFileSync(path, JSON.stringify({ names: Object.keys(objects), objects }));
  return path;
}

function htmlFiles(dir: string, prefix = ""): string[] {
  return readdirSync(dir).flatMap((name) => {
    const full = join(dir, name);
    if (statSync(full).isDirectory()) return htmlFiles(full, `${prefix}${name}/`);
    return name.endsWith(".html") ? [`${prefix}${name}`] : [];
  });
}

function allFiles(dir: string): string[] {
  return readdirSync(dir).flatMap((name) => {
    const full = join(dir, name);
    return statSync(full).isDirectory() ? allFiles(full) : [full];
  });
}

const page = (built: Built, route: string) => readFileSync(join(built.out, `${route}.html`), "utf8");

afterAll(() => rmSync(scratch, { recursive: true, force: true }));

describe("the real pages", () => {
  let real: Built;

  beforeAll(() => {
    if (!existsSync(REAL_EXPORT)) throw new Error(`${REAL_EXPORT} does not exist: run scripts/docs.sh export`);
    real = build(REAL_PAGES, REAL_EXPORT);
    if (real.code !== 0) throw new Error(real.output);
  });

  test("the build writes one page per navigation entry", () => {
    const navigation = JSON.parse(readFileSync(join(REAL_PAGES, "navigation.json"), "utf8"));
    const routes: string[] = navigation.tabs.flatMap((tab: any) =>
      tab.groups.flatMap((group: any) => group.pages.map((entry: any) => entry.route ?? entry)),
    );
    const expected = [...routes.map((route) => `${route.slice(1)}.html`), "index.html", "404.html"].sort();
    expect(htmlFiles(real.out).sort()).toEqual(expected);
  });

  test("code is highlighted in the built page and no grammar is loaded", () => {
    const html = page(real, "tutorials/build-your-first-file-system");
    expect(html).toMatch(/class="[^"]*text-code-(keyword|string|function)/);
    const named = [...html.matchAll(/(?:href|src)="([^"]+\.js)"|import\("([^"]+\.js)"\)/g)].map((m) => m[1] ?? m[2]);
    expect(named.length).toBeGreaterThan(0);
    for (const script of named) {
      const file = resolve(join(real.out, "tutorials"), script);
      // A TextMate grammar, the kind the highlighter loads, carries the key scopeName.
      expect(readFileSync(file, "utf8")).not.toContain("scopeName");
    }
  });

  test("a built page asks no other host for anything", () => {
    const resource = /<(?:script|img|source)\b[^>]*\bsrc="(https?:)?\/\/|<link\b[^>]*\bhref="(https?:)?\/\//;
    const inStyle = /url\(\s*["']?(https?:)?\/\/|@import\s+["'](https?:)?\/\//;
    for (const file of allFiles(real.out)) {
      const name = relative(real.out, file);
      // A page's canonical link names its own address at the site: it says where the page is and fetches nothing.
      const read = () => readFileSync(file, "utf8").replace(/<link\b[^>]*\brel="canonical"[^>]*>/g, "");
      if (file.endsWith(".html")) expect([name, resource.test(read())]).toEqual([name, false]);
      if (file.endsWith(".css")) expect([name, inStyle.test(read())]).toEqual([name, false]);
    }
  });

  /** The routes the navigation lists, in its order. */
  const listed = (): string[] =>
    JSON.parse(readFileSync(join(REAL_PAGES, "navigation.json"), "utf8")).tabs.flatMap((tab: any) =>
      tab.groups.flatMap((group: any) => group.pages.map((entry: any) => entry.route ?? entry)),
    );

  test("a page's head holds its description, its one address, and the pages before and after it", () => {
    const routes = listed();
    const head = (route: string) => {
      const html = page(real, route.slice(1));
      return html.slice(0, html.indexOf("</head>"));
    };
    const descriptions = routes.map((route) => head(route).match(/<meta name="description" content="([^"]*)"/)?.[1]);
    // Each page describes itself, in a length a search result shows whole: not one sentence on every page.
    for (const description of descriptions) expect(description?.length).toBeGreaterThan(20);
    for (const description of descriptions) expect(description?.length).toBeLessThanOrEqual(160);
    expect(new Set(descriptions).size).toBeGreaterThan(routes.length / 2);
    for (const route of routes) expect(head(route)).toContain(`<link rel="canonical" href="https://docs.vfs.dev${route}"`);
    expect(page(real, "index")).toContain('<link rel="canonical" href="https://docs.vfs.dev/"');
    // The first page has a next and no previous; the one after it has both.
    expect(head(routes[0])).not.toContain('rel="prev"');
    expect(head(routes[0])).toContain(`<link rel="next" href="${routes[1]}"`);
    expect(head(routes[1])).toContain(`<link rel="prev" href="${routes[0]}"`);
    expect(head(routes[1])).toContain(`<link rel="next" href="${routes[2]}"`);
  });

  test("the build writes a sitemap of every page, and a robots file that names it", () => {
    const sitemap = readFileSync(join(real.out, "sitemap.xml"), "utf8");
    const addresses = [...sitemap.matchAll(/<loc>([^<]+)<\/loc>/g)].map((m) => m[1]);
    const expected = ["/", ...listed()].map((route) => `https://docs.vfs.dev${route}`);
    expect(addresses.sort()).toEqual(expected.sort());
    expect(readFileSync(join(real.out, "robots.txt"), "utf8")).toContain("Sitemap: https://docs.vfs.dev/sitemap.xml");
  });

  test("every page links the icon the build writes", () => {
    for (const file of htmlFiles(real.out)) {
      expect([file, readFileSync(join(real.out, file), "utf8").includes('<link rel="icon" href="/favicon.svg"')]).toEqual([
        file,
        true,
      ]);
    }
    const icon = readFileSync(join(real.out, "favicon.svg"), "utf8");
    expect(icon.startsWith("<svg")).toBe(true);
    expect(icon).toContain('xmlns="http://www.w3.org/2000/svg"');
    expect(icon).toMatch(/<path\b/);
    // A tab's own ground may be dark: the icon turns light there by itself.
    expect(icon).toContain("prefers-color-scheme: dark");
    expect(icon).not.toContain("<!--");
  });

  test("a module's page shows its attributes, and the fields of a class no page pulls in by name", () => {
    const html = page(real, "reference/python-api/permissions").replace(/<!--.*?-->/g, "");
    expect(html).toContain('id="vfs.permissions.Permission"');
    // The module lists what it offers. A helper of the gate is not on its page.
    expect(html).not.toContain("PermissionLayer");
    const ranking = page(real, "reference/python-api/ranking").replace(/<!--.*?-->/g, "");
    for (const field of ["source", "mount", "rank"]) {
      expect(ranking).toContain(`<h4 id="vfs.rerank.Candidate.${field}"`);
    }
  });

  test("a glossary term shows its types, its code, its pages and its related terms", () => {
    const html = page(real, "reference/glossary").replace(/<!--.*?-->/g, "");
    const terms = html.split("<dl data-term").slice(1).map((rest) => rest.slice(0, rest.indexOf("</dl>")));
    // One block per term, at the end of the term: the next thing after it is the next term's heading, or the page's end.
    expect(terms.length).toBe((html.match(/<h2 id="/g) ?? []).length);
    const article = html.slice(html.indexOf("<article"), html.indexOf("</article>"));
    const after = article.split("</dl>").slice(1).map((rest) => rest.trimStart());
    expect(after.slice(0, -1).every((rest) => rest.startsWith("<h2 "))).toBe(true);
    expect(after[after.length - 1]).not.toContain("<h2 ");
    // The summary is what a link to the term shows, and the page does not print it under the heading.
    expect(html).not.toContain("<p>One file or directory in the file tree.</p>");
    for (const term of terms) {
      expect([...term.matchAll(/<dt[^>]*>([^<]+)<\/dt>/g)].map((label) => label[1])).toEqual([
        "Types",
        "Code",
        "Documentation",
        "Related terms",
      ]);
    }
    const entry = terms.find((term) => term.includes('href="/reference/python-api/entry#vfs.Entry"'));
    // A type links to its place on its API page, and a related term to its own heading on this page.
    expect(entry).toContain('href="#mount"');
    // A type or a row of code is its name alone, with no line under it saying where its page is.
    for (const term of terms) {
      expect(term.slice(0, term.indexOf(">Documentation</dt>"))).not.toContain("data-term-where");
    }
    // A term with no class of its own says so in its Types row.
    const arm = terms[0];
    expect(arm.slice(arm.indexOf(">Types</dt>"), arm.indexOf(">Code</dt>"))).toContain("None.");
  });

  test("a link that leaves the site opens in a new tab and says so", () => {
    const html = page(real, "overview").replace(/<!--.*?-->/g, "");
    const article = html.slice(html.indexOf("<article"), html.indexOf("</article>"));
    const links = [...article.matchAll(/<a\b[^>]*\bhref="([^"]+)"[^>]*>/g)].filter((m) => !m[0].includes("docs-anchor"));
    const outside = links.filter((m) => /^https?:\/\//.test(m[1]));
    const inside = links.filter((m) => !/^https?:\/\//.test(m[1]));
    expect(outside.length).toBeGreaterThan(0);
    expect(inside.length).toBeGreaterThan(0);
    for (const [tag] of outside) {
      expect(tag).toContain('target="_blank"');
      expect(tag).toContain('rel="noopener"');
      expect(tag).toContain('aria-describedby="vfs-new-tab"');
    }
    for (const [tag] of inside) expect(tag).not.toContain("target=");
    // The sentence a screen reader says for each of them is in the page once, and the header's link carries it too.
    expect(html.match(/id="vfs-new-tab"/g)).toHaveLength(1);
    expect(html).toMatch(/<span id="vfs-new-tab"[^>]*>Opens in a new tab<\/span>/);
    const header = html.slice(html.indexOf('data-slot="docs-header"'), html.indexOf("</header>"));
    expect(header).toMatch(/<a\b[^>]*href="https:\/\/github\.com[^"]*"[^>]*target="_blank"/);
  });

  test("every heading of a page links to itself", () => {
    const html = page(real, "overview").replace(/<!--.*?-->/g, "");
    const article = html.slice(html.indexOf("<article"), html.indexOf("</article>"));
    const ids = [...article.matchAll(/<h[1-4] id="([^"]+)"/g)].map((m) => m[1]);
    expect(ids.length).toBeGreaterThan(10);
    for (const id of ids) expect(article).toContain(`class="docs-anchor" href="#${id}"`);
    // An API name and each of its members link to themselves too.
    const api = page(real, "reference/python-api/mounts").replace(/<!--.*?-->/g, "");
    expect(api).toContain('class="docs-anchor" href="#vfs.Mount"');
    expect(api).toContain('class="docs-anchor" href="#vfs.Mount.path"');
  });

  test("a local diagram is inline", () => {
    const html = page(real, "overview");
    expect(html).toContain('id="vfs-optimal-disclosure"');
    expect(html).toContain('id="vfs-architecture"');
    expect(html).not.toMatch(/<img\b/);
  });
});

describe("links", () => {
  test("a dead link fails the build", () => {
    const built = build(pages({ "a.md": "# A\n\nSee [the other page](no-such-page.md).\n" }), exported());
    expect(built.code).not.toBe(0);
    expect(built.output).toContain("/no-such-page");
  });

  test("a dead anchor fails the build", () => {
    const files = { "a.md": "# A\n\nSee [a heading](b.md#no-such-heading).\n", "b.md": "# B\n\n## A Heading\n" };
    const built = build(pages(files), exported());
    expect(built.code).not.toBe(0);
    expect(built.output).toContain("no-such-heading");
  });
});

describe("the navigation and the folder agree", () => {
  const tab = (routes: string[]) => ({ tabs: [{ title: "Pages", groups: [{ title: null, pages: routes }] }] });
  const cases: [string, Record<string, string>, object | undefined, string][] = [
    ["a page on no list", { "a.md": "# A\n", "b.md": "# B\n" }, tab(["/a"]), "documentation/b.md is on no list"],
    ["a listed route with no file", { "a.md": "# A\n" }, tab(["/a", "/gone"]), "/gone is listed and has no file"],
    ["a route listed twice", { "a.md": "# A\n" }, tab(["/a", "/a"]), "/a is listed twice"],
    ["a page with no first-level heading", { "a.md": "No title here.\n" }, undefined, "documentation/a.md"],
    ["a page with two first-level headings", { "a.md": "# A\n\n# Again\n" }, undefined, "documentation/a.md"],
  ];
  for (const [name, files, navigation, named] of cases) {
    test(name, () => {
      const built = build(pages(files, navigation), exported());
      expect(built.code).not.toBe(0);
      expect(built.output).toContain(named);
    });
  }
});

test("a navigation entry may carry its own name", () => {
  // A page's title can be a sentence; the navigation may list it under a shorter name.
  const files = { "a.md": "# A Long Title: How It Came to Be\n", "b.md": "# B\n" };
  const listed = [{ route: "/a", title: "Short" }, "/b"];
  const navigation = { tabs: [{ title: "Pages", groups: [{ title: null, pages: listed }] }] };
  const built = build(pages(files, navigation), exported());
  expect(built.code).toBe(0);
  const html = page(built, "b").replace(/<!--.*?-->/g, "");
  const sidebar = html.slice(html.indexOf('data-slot="sidebar"'), html.indexOf("<main"));
  // A row's classes hold ">" themselves, so the row is found by its link and its text, not by one pattern.
  expect(sidebar).toContain('href="/a"');
  expect(sidebar).toContain(">Short</span>");
  expect(sidebar).not.toContain("A Long Title");
  // The page itself keeps its own title.
  expect(page(built, "a")).toContain("A Long Title: How It Came to Be");
});

describe("a token the renderer does not draw fails the build", () => {
  test("a raw HTML block in a page", () => {
    const built = build(pages({ "a.md": "# A\n\n<div>raw</div>\n" }), exported());
    expect(built.code).not.toBe(0);
    expect(built.output).toContain("documentation/a.md");
    expect(built.output).toContain('"html"');
  });

  test("a raw HTML block in a docstring", () => {
    const doc = "Text.\n\n<div>raw</div>";
    const thing = { kind: "function", labels: [], signature: "() -> None", bases: [], doc, members: [] };
    const built = build(pages({ "a.md": "# A\n\n::: vfs.thing\n" }), exported({ thing }));
    expect(built.code).not.toBe(0);
    expect(built.output).toContain("vfs.thing");
    expect(built.output).toContain('"html"');
  });
});

test("an API block renders the name and its members", () => {
  const member = (name: string, labels: string[] = []) => ({
    name,
    kind: "function",
    labels,
    signature: "() -> None",
    annotation: null,
    value: null,
    doc: `Does ${name}.`,
    members: [],
  });
  const size = {
    name: "size",
    kind: "attribute",
    labels: ["property"],
    signature: null,
    annotation: "int",
    value: null,
    doc: "",
    members: [],
  };
  const Thing = {
    kind: "class",
    labels: ["dataclass"],
    signature: "(name: str) -> None",
    bases: [],
    doc: "A thing.\n\n## Inside the Docstring\n\nMore.",
    members: [member("zeta", ["async"]), member("alpha"), size],
  };
  const built = build(pages({ "a.md": "# A\n\nIntro.\n\n::: vfs.Thing\n" }), exported({ Thing }));
  expect(built.output).toContain("done");
  expect(built.code).toBe(0);
  // The framework leaves comments between elements for the browser; they are no part of what is drawn.
  const html = page(built, "a").replace(/<!--.*?-->/g, "");
  const article = html.slice(html.indexOf("<article"), html.indexOf("</article>"));
  expect(article).not.toContain("text-code-invalid");
  expect([...article.matchAll(/<h2 id="([^"]+)"/g)].map((m) => m[1])).toEqual(["vfs.Thing"]);
  const members = ["vfs.Thing.zeta", "vfs.Thing.alpha", "vfs.Thing.size"];
  expect([...article.matchAll(/<h3 id="([^"]+)"/g)].map((m) => m[1])).toEqual(members);
  // Each name is led by what it is, in the page and in the table of contents, and followed by how it is declared.
  const symbols = (text: string) => [...text.matchAll(/data-api-symbol="(\w+)"/g)].map((m) => m[1]);
  const headings = [...article.matchAll(/<h[23] [^>]*>\s*<span data-api-symbol="(\w+)"/g)].map((m) => m[1]);
  expect(headings).toEqual(["class", "meth", "meth", "attr"]);
  // The list folded under the title on a narrow window carries the same words.
  const folded = article.slice(article.indexOf('data-slot="docs-toc-folded"'), article.indexOf("</details>"));
  expect(symbols(folded)).toEqual(["class", "meth", "meth", "attr"]);
  expect([...article.matchAll(/<span data-api-label="">(\w+)<\/span>/g)].map((m) => m[1])).toEqual([
    "dataclass",
    "async",
    "property",
  ]);
  const contents = html.slice(html.indexOf('data-slot="docs-toc"'));
  expect(symbols(contents)).toEqual(["class", "meth", "meth", "attr"]);
  // A heading inside a docstring is a bold line: it is no heading and has no id.
  expect(article).toMatch(/<strong>\s*Inside the Docstring\s*<\/strong>/);
  expect(article).not.toContain('id="inside-the-docstring"');
});

test("an exported type alias shows the type it stands for", () => {
  const Size = {
    kind: "attribute",
    labels: [],
    signature: null,
    annotation: null,
    value: "Literal['small', 'large']",
    bases: [],
    doc: "How big a thing is.",
    members: [],
  };
  const built = build(pages({ "a.md": "# A\n\n::: vfs.Size\n" }), exported({ Size }));
  expect(built.output).toContain("done");
  expect(built.code).toBe(0);
  const html = page(built, "a").replace(/<!--.*?-->/g, "");
  const article = html.slice(html.indexOf("<article"), html.indexOf("</article>"));
  expect(article).toMatch(/<h2 [^>]*>\s*<span data-api-symbol="attr"/);
  // The declaration is drawn as code: the name, then the type it is assigned.
  const text = article.replace(/<[^>]+>/g, "").replace(/&#39;|&apos;/g, "'");
  expect(text).toContain("Size = Literal['small', 'large']");
  expect(text).toContain("How big a thing is.");
});
