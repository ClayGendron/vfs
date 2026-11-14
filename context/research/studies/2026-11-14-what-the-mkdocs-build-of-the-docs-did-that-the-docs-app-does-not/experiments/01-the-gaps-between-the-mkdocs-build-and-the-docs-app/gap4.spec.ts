import { test } from "@playwright/test";
import { writeFileSync } from "node:fs";
const OLD = "http://127.0.0.1:8811", NEW = "http://127.0.0.1:8812";
const OUT = "/private/tmp/claude-501/-Users-claygendron-Git-Repos-vfs/96ca7b12-ae8e-42f1-8e39-f71cf4e99e78/scratchpad/gap-study/browser";
test("batch four", async ({ browser }) => {
  const r: any = {};
  const ctx = await browser.newContext({ viewport: { width: 1280, height: 900 } }); const page = await ctx.newPage();
  const stops = async () => { let n = 0; for (let i = 0; i < 80; i += 1) { await page.keyboard.press("Tab"); n += 1; if (await page.evaluate(() => !!document.activeElement?.closest("article"))) return n; } return -1; };
  for (const [name, url] of [["oldOverview", `${OLD}/overview/`], ["newOverview", `${NEW}/overview`], ["oldApi", `${OLD}/reference/api/AsyncVirtualFileSystem/`], ["newApi", `${NEW}/reference/python-api/async-virtual-file-system`]] as const) {
    await page.goto(url); await page.waitForTimeout(500); r[`${name}TabStopsToArticle`] = await stops();
  }
  await page.goto(`${OLD}/overview/#who-vfs-is-built-for`); await page.waitForTimeout(700);
  r.oldAnchorTop = await page.evaluate(() => ({ headingTop: Math.round(document.getElementById("who-vfs-is-built-for")!.getBoundingClientRect().top), headerBottom: Math.round(document.querySelector(".md-header")!.getBoundingClientRect().bottom) }));
  await page.goto(`${NEW}/overview#who-vfs-is-built-for`); await page.waitForTimeout(700);
  r.newAnchorTop = await page.evaluate(() => ({ headingTop: Math.round(document.getElementById("who-vfs-is-built-for")!.getBoundingClientRect().top), headerBottom: Math.round(document.querySelector("[data-slot=docs-header]")!.getBoundingClientRect().bottom) }));
  await ctx.close();
  const phone = await browser.newContext({ viewport: { width: 390, height: 844 } }); const p = await phone.newPage();
  await p.goto(`${OLD}/overview/`); await p.waitForTimeout(400); await p.mouse.wheel(0, 2500); await p.waitForTimeout(700);
  r.oldPhoneHeaderTitleAfterScroll = (await p.locator(".md-header__title").innerText()).replace(/\s+/g, " ").trim();
  r.oldPhoneHeaderActiveTopic = await p.locator(".md-header__title--active").count();
  await phone.close();
  writeFileSync(`${OUT}/batch-four.json`, JSON.stringify(r, null, 1));
});
