import { test } from "@playwright/test";
import { writeFileSync } from "node:fs";
const OLD = "http://127.0.0.1:8811", NEW = "http://127.0.0.1:8812";
const OUT = "/private/tmp/claude-501/-Users-claygendron-Git-Repos-vfs/96ca7b12-ae8e-42f1-8e39-f71cf4e99e78/scratchpad/gap-study/browser";
test("batch two", async ({ browser }) => {
  const r: any = { old: {}, new: {} };
  let ctx = await browser.newContext({ viewport: { width: 1280, height: 900 } }); let page = await ctx.newPage();
  await page.goto(`${OLD}/reference/api/AsyncVirtualFileSystem/`); await page.waitForTimeout(600);
  r.old.apiCopyButtons = await page.locator("button.md-clipboard, .md-code__button").count(); r.old.apiSignatures = await page.locator(".doc-signature").count();
  r.old.apiTocLinks = await page.locator(".md-sidebar--secondary .md-nav__link").count();
  r.old.apiTocFirst = await page.locator(".md-sidebar--secondary .md-nav__link").nth(4).evaluate((e) => { const c = e.querySelector("code"); return { text: (e as HTMLElement).innerText, symbol: c ? getComputedStyle(c, "::after").content : null }; });
  await page.locator('h2[id="vfs.AsyncVirtualFileSystem.bind"]').scrollIntoViewIfNeeded(); await page.screenshot({ path: `${OUT}/old-api-bind-1280.png` });
  await page.goto(`${OLD}/reference/python-api/permissions/#vfs.permissions.Permission`); await page.waitForTimeout(500);
  r.old.permissionAlias = await page.locator('h2[id="vfs.permissions.Permission"]').evaluate((e) => (e.parentElement as HTMLElement).innerText.slice(0, 400));
  r.old.focusablesBeforeArticle = await page.evaluate(() => { const a = document.querySelector("article")!; return [...document.querySelectorAll("a[href], button, input, [tabindex]")].filter((e) => (e as HTMLElement).offsetParent !== null && (a.compareDocumentPosition(e) & Node.DOCUMENT_POSITION_PRECEDING)).length; });
  await page.goto(`${NEW}/reference/python-api/async-virtual-file-system`); await page.waitForTimeout(600);
  r.new.apiCopyButtons = await page.locator('button[aria-label^="Copy"]').count(); r.new.apiCodeBlocks = await page.locator("article pre").count();
  r.new.apiTocLinks = await page.locator("[data-slot=docs-toc] a").count();
  r.new.focusablesBeforeArticle = await page.evaluate(() => { const a = document.querySelector("article")!; return [...document.querySelectorAll("a[href], button, input, [tabindex]")].filter((e) => (e as HTMLElement).offsetParent !== null && (a.compareDocumentPosition(e) & Node.DOCUMENT_POSITION_PRECEDING)).length; });
  await page.locator('h3[id="vfs.AsyncVirtualFileSystem.bind"]').scrollIntoViewIfNeeded(); await page.screenshot({ path: `${OUT}/new-api-bind-1280.png` });
  await page.goto(`${NEW}/overview`); await page.waitForTimeout(400);
  await page.locator('[data-slot=docs-pager] a').last().click(); await page.waitForTimeout(700);
  r.new.clientNavigation = await page.evaluate(() => ({ url: location.pathname, navType: (performance.getEntriesByType("navigation")[0] as any).name }));
  r.new.themeToggle = await page.locator("header button").evaluateAll((els) => els.map((e) => e.getAttribute("aria-label") ?? (e as HTMLElement).innerText));
  await ctx.close();
  for (const [name, base, path] of [["old", OLD, "/reference/access-levels/"], ["new", NEW, "/reference/access-levels"]] as const) {
    ctx = await browser.newContext({ viewport: { width: 390, height: 844 } }); page = await ctx.newPage(); await page.goto(base + path); await page.waitForTimeout(600);
    r[name].phoneTable = await page.evaluate(() => { const t = document.querySelector("article table") as HTMLElement; const w = t.parentElement as HTMLElement; return { pageScrollsSideways: document.documentElement.scrollWidth > document.documentElement.clientWidth, tableWidth: t.scrollWidth, wrapWidth: w.clientWidth, wrapOverflowX: getComputedStyle(w).overflowX, grandOverflowX: getComputedStyle(w.parentElement!).overflowX }; });
    await page.screenshot({ path: `${OUT}/${name}-table-390.png` });
    await page.goto(base + (name === "old" ? "/reference/api/AsyncVirtualFileSystem/" : "/reference/python-api/async-virtual-file-system")); await page.waitForTimeout(600);
    r[name].phoneApiSideways = await page.evaluate(() => document.documentElement.scrollWidth > document.documentElement.clientWidth);
    await page.screenshot({ path: `${OUT}/${name}-api-390.png` });
    await ctx.close();
  }
  writeFileSync(`${OUT}/batch-two.json`, JSON.stringify(r, null, 1));
});
