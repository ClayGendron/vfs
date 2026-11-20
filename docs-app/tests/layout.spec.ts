// The layout rules that need a browser: the sidebars stay still, keep their scroll, and fold into a drawer.
import { expect, test, type Page } from "@playwright/test";

// The longest page: one class with every verb, so both sidebars have more than the window can show.
const LONG_PAGE = "/reference/python-api/async-virtual-file-system";
const DESKTOP = { width: 1280, height: 800 };
const PHONE = { width: 390, height: 844 };

const WIDE = { width: 1920, height: 1000 };

const NAVIGATION = '[data-slot="sidebar"]';
const TABLE_OF_CONTENTS = '[data-slot="docs-toc"]';

async function topOf(page: Page, selector: string): Promise<number> {
  return page.locator(selector).evaluate((element) => Math.round(element.getBoundingClientRect().top));
}

// The page's scripts are running. Until then a scroll moves the page and nothing on it follows.
async function started(page: Page): Promise<void> {
  await page.locator('[data-slot="theme-toggle"][data-ready]').first().waitFor();
}

async function scrollTo(page: Page, y: number): Promise<void> {
  await page.evaluate((top) => window.scrollTo(0, top), y);
  await page.waitForFunction((top) => Math.abs(window.scrollY - top) < 2, y);
}

test("the top of each sidebar stays still as the page scrolls", async ({ page }) => {
  await page.setViewportSize(DESKTOP);
  await page.goto(LONG_PAGE);
  const bottom = await page.evaluate(() => document.documentElement.scrollHeight - window.innerHeight);
  expect(bottom).toBeGreaterThan(DESKTOP.height);
  for (const selector of [NAVIGATION, TABLE_OF_CONTENTS]) {
    await scrollTo(page, 0);
    const atTop = await topOf(page, selector);
    await scrollTo(page, 10);
    expect([selector, await topOf(page, selector)]).toEqual([selector, atTop]);
    await scrollTo(page, bottom);
    expect([selector, await topOf(page, selector)]).toEqual([selector, atTop]);
  }
});

test("scrolling a sidebar to its end does not scroll the page", async ({ page }) => {
  await page.setViewportSize(DESKTOP);
  await page.goto(LONG_PAGE);
  const list = page.locator(TABLE_OF_CONTENTS);
  // The list is taller than the window, so it has an end to scroll past.
  expect(await list.evaluate((element) => element.scrollHeight > element.clientHeight)).toBe(true);
  await list.hover();
  for (let turn = 0; turn < 12; turn += 1) await page.mouse.wheel(0, 1200);
  await page.waitForTimeout(300);
  expect(await list.evaluate((element) => element.scrollTop + element.clientHeight >= element.scrollHeight - 1)).toBe(
    true,
  );
  expect(await page.evaluate(() => window.scrollY)).toBe(0);
});

test("the two panels sit inside the page on a wide window", async ({ page }) => {
  await page.setViewportSize(WIDE);
  await page.goto(LONG_PAGE);
  const left = await page.locator(NAVIGATION).evaluate((element) => element.getBoundingClientRect().left);
  const right = await page.locator(TABLE_OF_CONTENTS).evaluate((element) => element.getBoundingClientRect().right);
  // The three columns are one centred block, so each panel is the same distance in from its side.
  expect(left).toBeGreaterThan(200);
  expect(WIDE.width - right).toBeGreaterThan(200);
  expect(Math.abs(left - (WIDE.width - right))).toBeLessThan(20);
  // The wordmark starts where the left panel starts.
  const mark = await page.locator(".vfs-wordmark").first().evaluate((element) => element.getBoundingClientRect().left);
  expect(Math.abs(mark - left)).toBeLessThan(40);
});

test("the current page's row has no coloured edge", async ({ page }) => {
  await page.setViewportSize(DESKTOP);
  await page.goto(LONG_PAGE);
  const row = page.locator(`${NAVIGATION} [aria-current="page"]:visible`);
  await expect(row).toHaveCount(1);
  const edge = await row.evaluate((element) => getComputedStyle(element).borderInlineStartColor);
  expect(edge).toMatch(/^rgba\(0, 0, 0, 0\)$|^transparent$|\/ 0\)$/);
});

// A colour as the browser paints it: drawn onto a canvas, so any colour syntax comes back as red, green and blue.
async function painted(page: Page, selector: string, property: string): Promise<number[]> {
  return page
    .locator(selector)
    .first()
    .evaluate((element, name) => {
      const canvas = document.createElement("canvas");
      canvas.width = canvas.height = 1;
      const context = canvas.getContext("2d")!;
      context.fillStyle = getComputedStyle(element).getPropertyValue(name);
      context.fillRect(0, 0, 1, 1);
      return [...context.getImageData(0, 0, 1, 1).data].slice(0, 3);
    }, property);
}

/** The contrast ratio of two colours, as WCAG defines it: 1 for the same colour, 21 for black on white. */
function contrast(a: number[], b: number[]): number {
  const channel = (value: number) => {
    const share = value / 255;
    return share <= 0.03928 ? share / 12.92 : ((share + 0.055) / 1.055) ** 2.4;
  };
  const light = ([r, g, b]: number[]) => 0.2126 * channel(r) + 0.7152 * channel(g) + 0.0722 * channel(b);
  const [high, low] = [light(a), light(b)].sort((x, y) => y - x);
  return (high + 0.05) / (low + 0.05);
}

const OTHER_ROW = `${NAVIGATION} a[href="/reference/python-api/entry"]:visible`;
const CURRENT_ROW = `${NAVIGATION} [aria-current="page"]:visible`;

test("a hovered row is told by its fill alone, with no edge around it", async ({ page }) => {
  await page.setViewportSize(DESKTOP);
  await page.goto(LONG_PAGE);
  const ground = await painted(page, "body", "background-color");
  await page.hover(OTHER_ROW);
  await page.waitForTimeout(300);
  expect(await page.locator(OTHER_ROW).evaluate((element) => getComputedStyle(element).outlineStyle)).toBe("none");
  const fill = await painted(page, OTHER_ROW, "background-color");
  expect(fill).not.toEqual(ground);
  expect(contrast(await painted(page, OTHER_ROW, "color"), fill)).toBeGreaterThanOrEqual(4.5);
});

const PROSE_LINK = '[data-slot="docs-article"] p a[href]';
const INLINE_CODE = '[data-slot="docs-article"] p code';

for (const scheme of ["light", "dark"] as const) {
  test(`a link in a page is the primary colour and underlined, in ${scheme} mode`, async ({ page }) => {
    await page.emulateMedia({ colorScheme: scheme });
    await page.setViewportSize(DESKTOP);
    await page.goto(LONG_PAGE);
    const ground = await painted(page, "body", "background-color");
    const link = await painted(page, PROSE_LINK, "color");
    // The primary token, read where the design system puts it; the page's own text is a different colour.
    expect(link).toEqual(await painted(page, "body", "--primary"));
    expect(link).not.toEqual(await painted(page, "body", "color"));
    expect(contrast(link, ground)).toBeGreaterThanOrEqual(4.5);
    const line = await page.locator(PROSE_LINK).first().evaluate((el) => getComputedStyle(el).textDecorationLine);
    expect(line).toContain("underline");
  });
}

test("inline code has the code ground behind it, as a code block has", async ({ page }) => {
  await page.setViewportSize(DESKTOP);
  await page.goto(LONG_PAGE);
  const ground = await painted(page, "body", "background-color");
  const chip = await painted(page, INLINE_CODE, "background-color");
  expect(chip).not.toEqual(ground);
  expect(chip).toEqual(await painted(page, '[data-slot="code-block"]', "background-color"));
  const padding = await page.locator(INLINE_CODE).first().evaluate((el) => parseFloat(getComputedStyle(el).paddingLeft));
  expect(padding).toBeGreaterThan(0);
  // The pager is navigation, not prose: its links keep the page's own colour.
  const pager = await painted(page, '[data-slot="docs-pager"] a', "color");
  expect(pager).toEqual(await painted(page, "body", "color"));
});

test("the current page's row differs from every other row by weight, not by colour alone", async ({ page }) => {
  await page.setViewportSize(DESKTOP);
  await page.goto(LONG_PAGE);
  const weight = (selector: string) =>
    page.locator(selector).evaluate((element) => Number(getComputedStyle(element).fontWeight));
  expect(await weight(CURRENT_ROW)).toBeGreaterThanOrEqual(500);
  expect(await weight(OTHER_ROW)).toBe(400);
  // At rest the current row has no edge: the edge is the hovered row's alone.
  expect(await page.locator(CURRENT_ROW).evaluate((element) => getComputedStyle(element).outlineStyle)).toBe("none");
});

test("the list of a page's headings is titled table of contents", async ({ page }) => {
  await page.setViewportSize(DESKTOP);
  await page.goto(LONG_PAGE);
  await expect(page.getByRole("navigation", { name: "Table of contents" })).toBeVisible();
  await expect(page.locator(TABLE_OF_CONTENTS)).toContainText("table of contents");
  await expect(page.locator(TABLE_OF_CONTENTS)).not.toContainText("on this page");
});

const FOLDED_CONTENTS = '[data-slot="docs-toc-folded"]';

for (const size of [PHONE, { width: 1100, height: 800 }]) {
  test(`a window ${size.width} pixels wide has a table of contents folded under the title`, async ({ page }) => {
    await page.setViewportSize(size);
    await page.goto(LONG_PAGE);
    // The column beside the page needs 1280 pixels; below that the same list is under the title, closed.
    await expect(page.locator(TABLE_OF_CONTENTS)).toBeHidden();
    const folded = page.locator(FOLDED_CONTENTS);
    await expect(folded).toBeVisible();
    await expect(folded.locator("summary")).toContainText("table of contents");
    const entry = folded.locator('a[href="#vfs.AsyncVirtualFileSystem.glob"]');
    await expect(entry).toBeHidden();
    await folded.locator("summary").click();
    await expect(entry).toBeVisible();
    await entry.click();
    await expect(page).toHaveURL(/#vfs\.AsyncVirtualFileSystem\.glob$/);
  });
}

test("the folded table of contents is not shown beside the column", async ({ page }) => {
  await page.setViewportSize(DESKTOP);
  await page.goto(LONG_PAGE);
  await expect(page.locator(TABLE_OF_CONTENTS)).toBeVisible();
  await expect(page.locator(FOLDED_CONTENTS)).toBeHidden();
});

test("the first Tab stop is a link that skips to the page's content", async ({ page }) => {
  await page.setViewportSize(DESKTOP);
  await page.goto(LONG_PAGE);
  const skip = page.getByRole("link", { name: "Skip to content" });
  // Out of sight until the keyboard reaches it, so it costs a reader with a mouse nothing.
  await expect(skip).not.toBeInViewport();
  await page.keyboard.press("Tab");
  await expect(skip).toBeFocused();
  await expect(skip).toBeInViewport();
  await page.keyboard.press("Enter");
  await expect(page).toHaveURL(/#content$/);
  // The next stop is inside the page's content, past the header and the whole left navigation.
  await page.keyboard.press("Tab");
  expect(await page.evaluate(() => document.querySelector("main")!.contains(document.activeElement))).toBe(true);
});

const BACK_TO_TOP = '[data-slot="docs-back-to-top"]';

test("a button that returns to the top shows once the reader scrolls back up", async ({ page }) => {
  await page.setViewportSize(DESKTOP);
  await page.goto(LONG_PAGE);
  await started(page);
  const button = page.locator(BACK_TO_TOP);
  await expect(button).toBeHidden();
  // Reading down, it stays out of the way; it is for the reader who has turned back.
  await scrollTo(page, 3000);
  await expect(button).toBeHidden();
  await scrollTo(page, 2600);
  await expect(button).toBeVisible();
  await expect(button).toHaveAccessibleName("Back to top");
  await button.click();
  await page.waitForFunction(() => window.scrollY === 0);
  await expect(button).toBeHidden();
});

test("printed, a page is its article alone at the paper's width", async ({ page }) => {
  await page.setViewportSize(DESKTOP);
  await page.goto(LONG_PAGE);
  await page.emulateMedia({ media: "print" });
  const furniture = ['[data-slot="docs-header"]', NAVIGATION, TABLE_OF_CONTENTS, '[data-slot="docs-pager"]', "footer"];
  for (const selector of furniture) await expect(page.locator(selector).first()).toBeHidden();
  await expect(page.locator(".docs-anchor").first()).toBeHidden();
  const article = await page.locator('[data-slot="docs-article"]').evaluate((el) => el.getBoundingClientRect().width);
  expect(article).toBeGreaterThan(DESKTOP.width * 0.9);
  // Paper cannot scroll: a line of code wider than the page wraps.
  const code = page.locator('[data-slot="code-block-content"]').first();
  expect(await code.evaluate((el) => getComputedStyle(el).whiteSpace)).toBe("pre-wrap");
});

// The tutorial whose printed output is wider than a phone: a table of grants and five error messages.
const WIDE_OUTPUT_PAGE = "/tutorials/control-who-can-access-files";

test("a block of printed output scrolls sideways, and never up and down", async ({ page }) => {
  await page.setViewportSize(PHONE);
  await page.goto(WIDE_OUTPUT_PAGE);
  const blocks = await page.locator('[data-slot="code-block-content"]').evaluateAll((elements) =>
    elements.map((element) => ({
      sideways: element.scrollWidth > element.clientWidth,
      upAndDown: element.scrollHeight > element.clientHeight,
      vertical: getComputedStyle(element).overflowY,
    })),
  );
  expect(blocks.filter((block) => block.sideways).length).toBeGreaterThan(0);
  expect(blocks.filter((block) => block.upAndDown)).toEqual([]);
  expect(new Set(blocks.map((block) => block.vertical))).toEqual(new Set(["hidden"]));
  // The block scrolls inside itself: the page is never wider than the window.
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);
});

test("with scripts off, a phone reaches every section and page from a menu under the header", async ({ browser }) => {
  const context = await browser.newContext({ javaScriptEnabled: false, viewport: PHONE });
  const page = await context.newPage();
  await page.goto(LONG_PAGE);
  // The drawer's button needs a script, so it is gone; the menu beside it is plain HTML and opens without one.
  await expect(page.getByRole("button", { name: "Toggle sidebar" })).toBeHidden();
  const menu = page.locator('[data-slot="docs-menu-noscript"]');
  const entry = menu.getByRole("link", { name: "Entry", exact: true });
  await expect(entry).toBeHidden();
  await menu.locator("summary").click();
  await expect(menu.getByRole("link", { name: "Tutorials", exact: true })).toBeVisible();
  await entry.click();
  await expect(page).toHaveURL(/\/reference\/python-api\/entry$/);
  await context.close();
});

test("with scripts on, the menu for scripts off is not on the page", async ({ page }) => {
  await page.setViewportSize(PHONE);
  await page.goto(LONG_PAGE);
  await expect(page.locator('[data-slot="docs-menu-noscript"]')).toBeHidden();
});

test("the navigation is a drawer on a phone", async ({ page }) => {
  await page.setViewportSize(PHONE);
  await page.goto(LONG_PAGE);
  await expect(page.locator(NAVIGATION)).toHaveCount(0);
  await page.getByRole("button", { name: "Toggle sidebar" }).click();
  const drawer = page.locator(NAVIGATION);
  await expect(drawer).toBeVisible();
  await drawer.getByRole("link", { name: "Entry", exact: true }).click();
  await expect(page).toHaveURL(/\/reference\/python-api\/entry$/);
  await expect(page.getByRole("heading", { level: 1, name: "Entry" })).toBeVisible();
});
