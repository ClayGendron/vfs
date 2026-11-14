import { test } from "@playwright/test";
import { writeFileSync } from "node:fs";
const OLD = "http://127.0.0.1:8811", NEW = "http://127.0.0.1:8812";
const OUT = "/private/tmp/claude-501/-Users-claygendron-Git-Repos-vfs/96ca7b12-ae8e-42f1-8e39-f71cf4e99e78/scratchpad/gap-study/browser";
test("batch three", async ({ browser }) => {
  const r: any = {};
  let ctx = await browser.newContext({ viewport: { width: 390, height: 844 } }); let page = await ctx.newPage();
  const wide = () => page.evaluate(() => { const vw = document.documentElement.clientWidth; const out: string[] = []; for (const e of document.querySelectorAll("body *")) { const b = e.getBoundingClientRect(); if (b.right > vw + 1 && b.width > 0) { let p = e.parentElement, clipped = false; while (p && p !== document.body) { const o = getComputedStyle(p).overflowX; if (o === "auto" || o === "hidden" || o === "scroll") { clipped = true; break; } p = p.parentElement; } if (!clipped) out.push(`${e.tagName.toLowerCase()}#${e.id}.${String((e as HTMLElement).className).slice(0, 50)} right=${Math.round(b.right)}`); } } return { scrollWidth: document.documentElement.scrollWidth, vw, offenders: out.slice(0, 8), count: out.length }; });
  const pages = ["/reference/python-api/async-virtual-file-system", "/reference/python-api/sessions", "/reference/python-api/results", "/reference/python-api/entry", "/reference/python-api/errors", "/overview", "/reference/glossary", "/tutorials/use-the-cli", "/"];
  r.newPhoneSideways = {}; for (const p of pages) { await page.goto(NEW + p); await page.waitForTimeout(350); r.newPhoneSideways[p] = await wide(); }
  await ctx.close();
  ctx = await browser.newContext({ viewport: { width: 1280, height: 900 } }); page = await ctx.newPage();
  await page.goto(`${OLD}/overview/`); await page.emulateMedia({ media: "print" }); await page.pdf({ path: `${OUT}/old-overview-print.pdf` });
  r.oldPrintLinks = await page.evaluate(() => getComputedStyle(document.querySelector("article a[href^=http]")!, "::after").content);
  await page.goto(`${OLD}/`); await page.emulateMedia({ media: "screen" }); await page.screenshot({ path: `${OUT}/old-home-1280.png` });
  r.oldHome = (await page.locator("article").innerText()).replace(/\s+/g, " ").slice(0, 700);
  await page.goto(`${NEW}/`); await page.waitForTimeout(400); await page.screenshot({ path: `${OUT}/new-home-1280.png` });
  r.newHome = (await page.locator("main").innerText()).replace(/\s+/g, " ").slice(0, 700);
  r.newHomeTitle = await page.title(); r.newHomeMeta = await page.locator('meta[name=description]').count();
  // anchors: same heading ids on both sites for the hand-written pages
  const diffs: any = {};
  for (const p of ["overview", "history", "get-started", "reference/glossary", "reference/access-levels", "tutorials/use-the-cli", "tutorials/build-your-first-file-system", "tutorials/keep-your-files-in-a-database", "tutorials/give-an-ai-agent-the-file-system", "tutorials/control-who-can-access-files", "how-to/load-a-folder-of-files", "explanation/why-vfs-stores-files-in-a-database"]) {
    await page.goto(`${OLD}/${p}/`); const o = await page.locator("article :is(h1,h2,h3,h4)[id]").evaluateAll((els) => els.map((e) => e.id));
    await page.goto(`${NEW}/${p}`); const n = await page.locator("article :is(h1,h2,h3,h4)[id]").evaluateAll((els) => els.map((e) => e.id));
    const onlyOld = o.filter((x) => !n.includes(x)), onlyNew = n.filter((x) => !o.includes(x));
    diffs[p] = { old: o.length, new: n.length, onlyOld, onlyNew };
  }
  r.anchorDiffs = diffs;
  await ctx.close();
  writeFileSync(`${OUT}/batch-three.json`, JSON.stringify(r, null, 1));
});
