import { test } from "@playwright/test";
import { writeFileSync, mkdirSync } from "node:fs";
const OLD = "http://127.0.0.1:8811", NEW = "http://127.0.0.1:8812";
const OUT = "/private/tmp/claude-501/-Users-claygendron-Git-Repos-vfs/96ca7b12-ae8e-42f1-8e39-f71cf4e99e78/scratchpad/gap-study/browser";
mkdirSync(OUT, { recursive: true });
const save = (name: string, data: unknown) => writeFileSync(`${OUT}/${name}.json`, JSON.stringify(data, null, 1));
const vis = (page: any, sel: string) => page.evaluate((s: string) => { const e = document.querySelector(s) as HTMLElement | null; if (!e) return "absent"; const r = e.getBoundingClientRect(); const c = getComputedStyle(e); return c.display === "none" || c.visibility === "hidden" || r.width === 0 || r.height === 0 ? "hidden" : `visible ${Math.round(r.width)}x${Math.round(r.height)}`; }, sel);

test("old desktop", async ({ browser }) => {
  const ctx = await browser.newContext({ viewport: { width: 1280, height: 900 } });
  const page = await ctx.newPage(); const r: any = {};
  await page.goto(`${OLD}/overview/`); await page.waitForTimeout(800);
  await page.screenshot({ path: `${OUT}/old-overview-1280.png` });
  r.copyButtons = await page.locator("button.md-clipboard, .md-code__button").count();
  r.codeBlocks = await page.locator("pre > code").count();
  r.codeTabindex = await page.locator("pre > code[tabindex], .highlight[tabindex], pre[tabindex]").count();
  r.toc = await vis(page, ".md-sidebar--secondary"); r.leftNav = await vis(page, ".md-sidebar--primary");
  await page.keyboard.press("/"); await page.waitForTimeout(300);
  r.slashFocusesSearch = await page.evaluate(() => document.activeElement?.getAttribute("name") ?? document.activeElement?.tagName);
  await page.keyboard.type("permission"); await page.waitForTimeout(1500);
  r.searchResults = await page.locator(".md-search-result__item").count();
  r.searchMeta = await page.locator(".md-search-result__meta").innerText().catch(() => null);
  await page.screenshot({ path: `${OUT}/old-search-1280.png` });
  await page.keyboard.press("Enter"); await page.waitForTimeout(1200);
  r.afterEnterUrl = page.url(); r.highlightMarks = await page.locator("mark[data-md-highlight]").count();
  await page.goto(`${OLD}/overview/`); await page.waitForTimeout(500);
  await page.keyboard.press("n"); await page.waitForTimeout(1000); r.afterN = page.url();
  await page.keyboard.press("p"); await page.waitForTimeout(1000); r.afterP = page.url();
  await page.goto(`${OLD}/overview/`); await page.waitForTimeout(400);
  await page.mouse.wheel(0, 3000); await page.waitForTimeout(400); await page.mouse.wheel(0, -300); await page.waitForTimeout(600);
  r.backToTop = await vis(page, "button.md-top"); r.backToTopText = await page.locator("button.md-top").innerText().catch(() => null);
  r.tocActive = await page.locator(".md-nav--secondary .md-nav__link--active").first().innerText().catch(() => null);
  await page.screenshot({ path: `${OUT}/old-scrolled-1280.png` });
  await page.goto(`${OLD}/overview/`); await page.keyboard.press("Tab");
  r.firstTab = await page.evaluate(() => `${document.activeElement?.className} | ${document.activeElement?.textContent?.trim()}`);
  const h2 = page.locator("article h2").first(); await h2.hover(); await page.waitForTimeout(300);
  r.permalinkOpacity = await h2.locator("a.headerlink").evaluate((e) => getComputedStyle(e).opacity);
  r.h2ScrollMargin = await h2.evaluate((e) => getComputedStyle(e).scrollMarginTop);
  await page.emulateMedia({ media: "print" });
  r.print = { header: await vis(page, ".md-header"), leftNav: await vis(page, ".md-sidebar--primary"), toc: await vis(page, ".md-sidebar--secondary"), footer: await vis(page, ".md-footer") };
  await page.emulateMedia({ media: "screen" });
  await page.goto(`${OLD}/reference/api/Entry/`); await page.waitForTimeout(500);
  await page.screenshot({ path: `${OUT}/old-api-entry-1280.png` });
  r.apiToc = (await page.locator(".md-sidebar--secondary .md-nav__link").allInnerTexts()).slice(0, 12);
  r.apiH = await page.locator("article h1, article h2").evaluateAll((els) => els.slice(0, 6).map((e) => (e as HTMLElement).innerText.replace(/\s+/g, " ")));
  r.symbolText = await page.locator("article h2 code.doc-symbol").first().evaluate((e) => getComputedStyle(e, "::after").content);
  await page.goto(`${OLD}/reference/api/AsyncVirtualFileSystem/`); await page.waitForTimeout(500);
  r.asyncLabels = await page.locator("article .doc-label").evaluateAll((els) => { const c: Record<string, number> = {}; for (const e of els) { const t = (e as HTMLElement).innerText.trim(); c[t] = (c[t] ?? 0) + 1; } return c; });
  r.asyncMembers = await page.locator("article h2.doc-heading, article h3.doc-heading").count();
  r.asyncSig = await page.locator("article .doc-signature").nth(1).innerText();
  await page.screenshot({ path: `${OUT}/old-api-avfs-1280.png` });
  await page.goto(`${OLD}/nope/`); r.notFound = await page.locator("article").innerText().catch(() => null);
  save("old-desktop", r); await ctx.close();
});

test("new desktop", async ({ browser }) => {
  const ctx = await browser.newContext({ viewport: { width: 1280, height: 900 } });
  const page = await ctx.newPage(); const r: any = {}; const failed: string[] = [];
  page.on("response", (res) => { if (res.status() >= 400) failed.push(`${res.status()} ${res.url()}`); });
  await page.goto(`${NEW}/overview`); await page.waitForTimeout(800);
  await page.screenshot({ path: `${OUT}/new-overview-1280.png` });
  r.copyButtons = await page.locator('button[aria-label^="Copy"]').count();
  r.codeBlocks = await page.locator("pre").count();
  r.codeTabindex = await page.locator("pre[tabindex], [data-slot^=code-block][tabindex]").count();
  r.toc = await vis(page, "[data-slot=docs-toc]"); r.leftNav = await vis(page, "[data-slot=sidebar]");
  await page.keyboard.press("/"); await page.waitForTimeout(300);
  r.slashFocus = await page.evaluate(() => document.activeElement?.tagName);
  r.searchInputs = await page.locator('input[type=search], input[placeholder*="earch" i], [role=search]').count();
  await page.keyboard.press("n"); await page.waitForTimeout(700); r.afterN = page.url();
  await page.mouse.wheel(0, 3000); await page.waitForTimeout(400); await page.mouse.wheel(0, -300); await page.waitForTimeout(600);
  r.backToTop = await page.getByRole("button", { name: /top/i }).count() + await page.getByRole("link", { name: /top/i }).count();
  r.tocActive = await page.locator("[data-slot=docs-toc] a[aria-current=location]").innerText().catch(() => null);
  await page.screenshot({ path: `${OUT}/new-scrolled-1280.png` });
  await page.goto(`${NEW}/overview`); await page.waitForTimeout(400); await page.keyboard.press("Tab");
  r.firstTab = await page.evaluate(() => `${document.activeElement?.tagName} | ${document.activeElement?.getAttribute("aria-label") ?? document.activeElement?.textContent?.trim()}`);
  const h2 = page.locator("article h2").first(); await h2.hover();
  r.h2Links = await h2.locator("a").count(); r.h2ScrollMargin = await h2.evaluate((e) => getComputedStyle(e).scrollMarginTop);
  r.extLinkTarget = await page.locator('article a[href^="https://www.gartner"]').first().evaluate((e) => `${e.getAttribute("target")} ${e.getAttribute("rel")}`);
  r.headerGithub = await page.locator('header a[href*="github.com"]').evaluate((e) => `${e.getAttribute("target")} ${e.getAttribute("rel")}`);
  await page.emulateMedia({ media: "print" });
  r.print = { header: await vis(page, "[data-slot=docs-header]"), leftNav: await vis(page, "[data-slot=sidebar]"), toc: await vis(page, "[data-slot=docs-toc]"), footer: await vis(page, "footer"), headerPosition: await page.locator("[data-slot=docs-header]").evaluate((e) => getComputedStyle(e).position) };
  await page.pdf({ path: `${OUT}/new-overview-print.pdf` }).catch((e) => (r.pdfError = String(e)));
  await page.emulateMedia({ media: "screen" });
  await page.goto(`${NEW}/reference/python-api/entry`); await page.waitForTimeout(500);
  await page.screenshot({ path: `${OUT}/new-api-entry-1280.png` });
  r.apiToc = (await page.locator("[data-slot=docs-toc] a").allInnerTexts()).slice(0, 12);
  r.apiH = await page.locator("article h1, article h2, article h3").evaluateAll((els) => els.slice(0, 6).map((e) => (e as HTMLElement).innerText.replace(/\s+/g, " ")));
  r.entryMembers = await page.locator("article h3[data-api-member]").count();
  r.entryText = (await page.locator("article").innerText()).slice(0, 1500);
  await page.goto(`${NEW}/reference/python-api/async-virtual-file-system`); await page.waitForTimeout(500);
  r.asyncMembers = await page.locator("article h3[data-api-member]").count();
  r.asyncFirstSig = await page.locator("article pre").nth(2).innerText();
  r.asyncWordCounts = await page.locator("article").evaluate((e) => { const t = (e as HTMLElement).innerText; return { property: (t.match(/\bproperty\b/g) ?? []).length, async: (t.match(/\basync\b/g) ?? []).length, classmethod: (t.match(/\bclassmethod\b/g) ?? []).length }; });
  await page.screenshot({ path: `${OUT}/new-api-avfs-1280.png` });
  await page.goto(`${NEW}/nope`); await page.waitForTimeout(600); r.notFound = await page.locator("main").innerText().catch(() => null); r.notFoundTitle = await page.title();
  r.failed = failed; r.htmlClass = await page.evaluate(() => document.documentElement.className);
  save("new-desktop", r); await ctx.close();
});

for (const [name, base, path] of [["old", OLD, "/overview/"], ["new", NEW, "/overview"]] as const) {
  test(`${name} widths`, async ({ browser }) => {
    const r: any = {};
    for (const width of [390, 800, 1100]) {
      const ctx = await browser.newContext({ viewport: { width, height: 844 } });
      const page = await ctx.newPage(); await page.goto(base + path); await page.waitForTimeout(700);
      const o: any = {};
      if (name === "old") {
        o.toc = await vis(page, ".md-sidebar--secondary"); o.leftNav = await vis(page, ".md-sidebar--primary"); o.tabs = await vis(page, ".md-tabs");
        o.menuButton = await vis(page, "label.md-header__button[for=__drawer]"); o.searchButton = await vis(page, "label.md-header__button[for=__search]");
        if (width === 390) { await page.locator("label.md-header__button[for=__drawer]").click(); await page.waitForTimeout(500); o.drawerLinks = (await page.locator(".md-sidebar--primary .md-nav__link:visible").allInnerTexts()).map((t) => t.trim()).slice(0, 20); await page.screenshot({ path: `${OUT}/old-drawer-390.png` }); }
      } else {
        o.toc = await vis(page, "[data-slot=docs-toc]"); o.leftNav = await vis(page, "[data-slot=sidebar]"); o.tabs = await vis(page, "header nav");
        o.menuButton = await vis(page, "[data-slot=sidebar-trigger]"); o.github = await vis(page, 'header a[href*="github.com"]');
        if (width === 390) { await page.locator("[data-slot=sidebar-trigger]").click(); await page.waitForTimeout(600); o.drawerLinks = (await page.locator("[role=dialog] a:visible").allInnerTexts()).map((t) => t.trim()).slice(0, 20); await page.screenshot({ path: `${OUT}/new-drawer-390.png` }); }
      }
      o.pageScrollsSideways = await page.evaluate(() => document.documentElement.scrollWidth > document.documentElement.clientWidth);
      r[width] = o; await ctx.close();
    }
    save(`${name}-widths`, r);
  });
  test(`${name} no scripts`, async ({ browser }) => {
    const r: any = {};
    for (const scheme of ["light", "dark"] as const) {
      const ctx = await browser.newContext({ viewport: { width: 1280, height: 900 }, javaScriptEnabled: false, colorScheme: scheme });
      const page = await ctx.newPage(); await page.goto(base + path);
      r[scheme] = { bodyBackground: await page.locator("body").evaluate((e) => getComputedStyle(e).backgroundColor), h2: await page.locator("article h2").count(), svg: await page.locator("article svg").count(), highlightedSpans: await page.locator("article pre span[class], article pre span[style]").count(), navLinks: await page.locator("nav a").count() };
      if (scheme === "dark") await page.screenshot({ path: `${OUT}/${name}-noscript-dark-1280.png` });
      await ctx.close();
    }
    const ctx = await browser.newContext({ viewport: { width: 390, height: 844 }, javaScriptEnabled: false });
    const page = await ctx.newPage(); await page.goto(base + path);
    const trigger = name === "old" ? "label.md-header__button[for=__drawer]" : "[data-slot=sidebar-trigger]";
    await page.locator(trigger).click({ timeout: 3000 }).catch((e) => (r.phoneClickError = String(e).slice(0, 120))); await page.waitForTimeout(500);
    r.phoneDrawerLinksVisible = name === "old" ? await page.locator(".md-sidebar--primary .md-nav__link:visible").count() : await page.locator("[role=dialog] a:visible").count();
    r.phoneNavLinksVisible = await page.locator("a:visible").count();
    await ctx.close(); save(`${name}-noscript`, r);
  });
}
