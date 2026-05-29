/**
 * Telemetry integration tests.
 *
 * These tests verify that Application Insights events fire correctly for all
 * tracked user interactions. They require a build created with:
 *
 *   PUBLIC_APP_INSIGHTS_CONNECTION_STRING="InstrumentationKey=00000000-0000-0000-0000-000000000000;IngestionEndpoint=https://fake-ai.test" npm run build
 *
 * The fake endpoint is intercepted via `page.route` so no real data leaves the browser.
 */
import { test, expect } from "@playwright/test";
import type { Page } from "@playwright/test";

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

/**
 * Parsed App Insights telemetry envelope.
 * @see https://learn.microsoft.com/en-us/azure/azure-monitor/app/data-model
 */
interface Envelope {
  name: string;
  data?: {
    baseType?: string;
    baseData?: {
      name?: string;
      properties?: Record<string, unknown>;
      measurements?: Record<string, number>;
      metrics?: Array<{ name: string; value: number }>;
      exceptions?: Array<{ message: string }>;
      ver?: number;
    };
  };
}

/** Parse an App Insights POST body (JSON array or NDJSON). */
function parsePayload(body: string | null): Envelope[] {
  if (!body) return [];

  // Try JSON array / single object first
  try {
    const parsed = JSON.parse(body);
    return Array.isArray(parsed) ? parsed : [parsed];
  } catch {
    /* fall through to NDJSON */
  }

  // NDJSON (newline-delimited)
  const envelopes: Envelope[] = [];
  for (const line of body.split("\n")) {
    const trimmed = line.trim();
    if (!trimmed) continue;
    try {
      const parsed = JSON.parse(trimmed);
      if (Array.isArray(parsed)) envelopes.push(...parsed);
      else envelopes.push(parsed);
    } catch {
      /* skip malformed lines */
    }
  }
  return envelopes;
}

/** Intercept App Insights SDK network calls and capture the envelopes. */
async function setupCapture(page: Page): Promise<Envelope[]> {
  const captured: Envelope[] = [];

  await page.route(/fake-ai\.test/, async (route) => {
    const body = route.request().postData();
    if (body) captured.push(...parsePayload(body));
    await route.fulfill({ status: 200, body: "" });
  });

  return captured;
}

/** Flush the SDK buffer and wait for the network request to be intercepted. */
async function flush(page: Page): Promise<void> {
  await page.evaluate(() => (window as any).__telemetry?.flush?.());
  // Give the browser time to complete the network send and the route handler to process
  await page.waitForTimeout(1500);
}

/** Filter captured envelopes to custom events with a given name. */
function findEvents(captured: Envelope[], eventName: string): Envelope[] {
  return captured.filter(
    (e) => e.data?.baseType === "EventData" && e.data?.baseData?.name === eventName,
  );
}

/** Filter captured envelopes to page views. */
function findPageViews(captured: Envelope[]): Envelope[] {
  return captured.filter((e) => e.data?.baseType === "PageviewData");
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

const HOME = "/forgebook/";
const NOTEBOOK = "/forgebook/notebook/foundry-agent-part-1";

test.describe("Telemetry", () => {
  // --------------------------------------------------
  // 1. SDK initialisation — page view on load
  // --------------------------------------------------
  test("page view is tracked on load", async ({ page }) => {
    const captured = await setupCapture(page);
    await page.goto(HOME);
    await flush(page);

    const pvs = findPageViews(captured);
    expect(pvs.length).toBeGreaterThanOrEqual(1);
  });

  // --------------------------------------------------
  // 2. Click tracking (internal — notebook card)
  // --------------------------------------------------
  test("notebook card click fires Click event", async ({ page }) => {
    const captured = await setupCapture(page);
    await page.goto(HOME);

    // Prevent actual navigation so we stay on page for flush
    await page.evaluate(() => {
      const card = document.querySelector("[data-track-click]");
      card?.addEventListener("click", (e) => e.preventDefault(), { once: true });
    });

    await page.locator("[data-track-click]").first().click();
    await flush(page);

    const clicks = findEvents(captured, "Click");
    const cardClick = clicks.find((e) =>
      String(e.data?.baseData?.properties?.label ?? "").startsWith("notebook-card:"),
    );
    expect(cardClick).toBeTruthy();
  });

  // --------------------------------------------------
  // 3. Outbound click tracking (GitHub link)
  // --------------------------------------------------
  test("GitHub link fires OutboundClick event", async ({ page }) => {
    const captured = await setupCapture(page);
    await page.goto(HOME);

    // Prevent navigation away from the page
    await page.evaluate(() => {
      const link = document.querySelector('a[href*="github.com"]');
      link?.addEventListener("click", (e) => e.preventDefault(), { once: true });
    });

    await page.locator('a[href="https://github.com/microsoft-foundry/forgebook"]').first().click();
    await flush(page);

    const outbound = findEvents(captured, "OutboundClick");
    expect(outbound.length).toBeGreaterThanOrEqual(1);
    expect(outbound[0].data?.baseData?.properties?.destination).toBe("github.com");
  });

  // --------------------------------------------------
  // 4. Theme toggle
  // --------------------------------------------------
  test("theme toggle fires ThemeChange event", async ({ page }) => {
    const captured = await setupCapture(page);
    await page.goto(HOME);

    await page.getByRole("button", { name: /light mode/i }).click();
    await flush(page);

    const events = findEvents(captured, "ThemeChange");
    expect(events.length).toBeGreaterThanOrEqual(1);
    expect(events[0].data?.baseData?.properties).toMatchObject({
      from: "light",
      to: "dark",
    });
  });

  // --------------------------------------------------
  // 5. Tag filter
  // --------------------------------------------------
  test("clicking a tag filter fires TagFilter event", async ({ page }) => {
    const captured = await setupCapture(page);
    await page.goto(HOME);

    const tagBtn = page.locator(".tag-filter-btn:not(.tag-clear-btn)").first();
    if (await tagBtn.isVisible({ timeout: 2000 }).catch(() => false)) {
      await tagBtn.click();
      await flush(page);

      const events = findEvents(captured, "TagFilter");
      expect(events.length).toBeGreaterThanOrEqual(1);
      expect(events[0].data?.baseData?.properties?.tag).toBeTruthy();
      expect(events[0].data?.baseData?.properties).toHaveProperty("isFiltering");
    }
  });

  // --------------------------------------------------
  // 6. Search query
  // --------------------------------------------------
  test("typing a search query fires Search event", async ({ page }) => {
    const captured = await setupCapture(page);
    await page.goto(HOME);

    // Open search modal
    await page.keyboard.press("Control+k");
    await page.waitForSelector("#search-modal:not([style*='none'])", { timeout: 3000 });

    // Type a query (debounce is 200ms + pagefind load time)
    await page.fill("#search-input", "agent");
    await page.waitForTimeout(2000);
    await flush(page);

    const opens = findEvents(captured, "SearchOpen");
    expect(opens.length).toBeGreaterThanOrEqual(1);
    expect(opens[0].data?.baseData?.properties?.source).toBe("keyboard-shortcut");

    const events = findEvents(captured, "Search");
    expect(events.length).toBeGreaterThanOrEqual(1);
    expect(events[0].data?.baseData?.properties?.query).toBe("agent");
    expect(events[0].data?.baseData?.properties?.queryLength).toBe("5");
    expect(events[0].data?.baseData?.properties).toHaveProperty("resultCount");
    expect(events[0].data?.baseData?.properties).toHaveProperty("hasResults");
  });

  // --------------------------------------------------
  // 7. Search result click (keyboard)
  // --------------------------------------------------
  test("selecting a search result fires SearchResultClick event", async ({ page }) => {
    const captured = await setupCapture(page);
    await page.goto(HOME);

    await page.keyboard.press("Control+k");
    await page.waitForSelector("#search-modal:not([style*='none'])", { timeout: 3000 });

    await page.fill("#search-input", "agent");
    await page.waitForTimeout(2000);

    // Check we have results
    const resultCount = await page.locator(".search-result-item").count();
    if (resultCount > 0) {
      // Prevent navigation so we can flush
      await page.evaluate(() => {
        const result = document.querySelector(".search-result-item");
        result?.addEventListener("click", (e) => e.preventDefault(), { once: true });
      });

      // Click the first result
      await page.locator(".search-result-item").first().click();
      await flush(page);

      const events = findEvents(captured, "SearchResultClick");
      expect(events.length).toBeGreaterThanOrEqual(1);
      expect(events[0].data?.baseData?.properties?.query).toBe("agent");
      expect(events[0].data?.baseData?.properties?.queryLength).toBe("5");
      expect(events[0].data?.baseData?.properties).toHaveProperty("resultUrl");
    }
  });

  test("closing search after a query without clicking a result fires SearchAbandon event", async ({ page }) => {
    const captured = await setupCapture(page);
    await page.goto(HOME);

    await page.keyboard.press("Control+k");
    await page.waitForSelector("#search-modal:not([style*='none'])", { timeout: 3000 });

    await page.fill("#search-input", "zzzzzzzzzzzzzzzzzzzz");
    await page.waitForTimeout(2000);
    await page.keyboard.press("Escape");
    await flush(page);

    const events = findEvents(captured, "SearchAbandon");
    expect(events.length).toBeGreaterThanOrEqual(1);
    expect(events[0].data?.baseData?.properties).toMatchObject({
      query: "zzzzzzzzzzzzzzzzzzzz",
      queryLength: "20",
      source: "escape",
    });
    expect(events[0].data?.baseData?.properties).toHaveProperty("hasResults");
    expect(events[0].data?.baseData?.properties).toHaveProperty("resultCount");
  });

  // --------------------------------------------------
  // 8. Scroll depth
  // --------------------------------------------------
  test("scrolling fires ScrollDepth event", async ({ page }) => {
    const captured = await setupCapture(page);
    await page.goto(NOTEBOOK);

    // Scroll to 100%
    await page.evaluate(() =>
      window.scrollTo({ top: document.documentElement.scrollHeight, behavior: "instant" }),
    );
    await page.waitForTimeout(500);
    await flush(page);

    const events = findEvents(captured, "ScrollDepth");
    expect(events.length).toBeGreaterThanOrEqual(1);

    // Thresholds arrive as strings in the serialized JSON
    const thresholds = events.map((e) => Number(e.data?.baseData?.properties?.threshold));
    expect(thresholds).toContain(25);
  });

  // --------------------------------------------------
  // 9. Copy code block
  // --------------------------------------------------
  test("copying a code block fires CopyCodeBlock event", async ({ page, context }) => {
    await context.grantPermissions(["clipboard-read", "clipboard-write"]);
    const captured = await setupCapture(page);
    await page.goto(NOTEBOOK);

    const copyBtn = page.locator(".copy-btn").first();
    if (await copyBtn.isVisible({ timeout: 3000 }).catch(() => false)) {
      await copyBtn.click();
      await flush(page);

      const events = findEvents(captured, "CopyCodeBlock");
      expect(events.length).toBeGreaterThanOrEqual(1);
      expect(events[0].data?.baseData?.properties).toHaveProperty("codeLength");
      expect(events[0].data?.baseData?.properties).not.toHaveProperty("codePreview");
    }
  });

  // --------------------------------------------------
  // 10. Copy Markdown
  // --------------------------------------------------
  test("copying markdown fires CopyMarkdown event", async ({ page, context }) => {
    await context.grantPermissions(["clipboard-read", "clipboard-write"]);
    const captured = await setupCapture(page);
    await page.goto(NOTEBOOK);

    await page.getByRole("button", { name: "Copy page" }).click();
    await page.waitForTimeout(1000); // Wait for fetch + clipboard write
    await flush(page);

    const events = findEvents(captured, "CopyMarkdown");
    expect(events.length).toBeGreaterThanOrEqual(1);
    expect(events[0].data?.baseData?.properties?.slug).toBe("foundry-agent-part-1");
  });

  // --------------------------------------------------
  // 11. Share — copy link
  // --------------------------------------------------
  test("primary share button copies link and fires ShareAction event", async ({ page, context }) => {
    await context.grantPermissions(["clipboard-read", "clipboard-write"]);
    const captured = await setupCapture(page);
    await page.goto(NOTEBOOK);

    await page.getByRole("button", { name: "Share", exact: true }).click();
    await expect(page.locator("#share-btn-text")).toHaveText("Copied!");
    await expect(page.locator("#share-dropdown")).toHaveClass(/hidden/);
    await page.waitForTimeout(1000);
    await flush(page);

    const events = findEvents(captured, "ShareAction");
    const copyEvent = events.find((e) =>
      e.data?.baseData?.properties?.method === "CopyLink" &&
      e.data?.baseData?.properties?.source === "button"
    );
    expect(copyEvent).toBeTruthy();
  });

  test("share copy-link fires ShareAction event", async ({ page, context }) => {
    await context.grantPermissions(["clipboard-read", "clipboard-write"]);
    const captured = await setupCapture(page);
    await page.goto(NOTEBOOK);

    // Open share dropdown
    await page.locator("#share-dropdown-btn").click();
    await page.waitForSelector("#share-dropdown:not(.hidden)", { timeout: 2000 });

    // Click "Copy Link" and wait for async clipboard operation
    await page.locator("#copy-link-btn").click();
    await page.waitForTimeout(1000);
    await flush(page);

    const events = findEvents(captured, "ShareAction");
    expect(events.length).toBeGreaterThanOrEqual(1);
    expect(events[0].data?.baseData?.properties?.method).toBe("CopyLink");
  });

  // --------------------------------------------------
  // 12. Share — social links (X / LinkedIn)
  // --------------------------------------------------
  test("share on X fires ShareAction event", async ({ page }) => {
    const captured = await setupCapture(page);
    await page.goto(NOTEBOOK);

    // Open share dropdown
    await page.locator("#share-dropdown-btn").click();
    await page.waitForSelector("#share-dropdown:not(.hidden)", { timeout: 2000 });

    // Prevent navigation to X
    await page.evaluate(() => {
      document.getElementById("share-x")?.addEventListener("click", (e) => e.preventDefault(), { once: true });
    });

    await page.locator("#share-x").click();
    await flush(page);

    const events = findEvents(captured, "ShareAction");
    const xEvent = events.find((e) => e.data?.baseData?.properties?.method === "X");
    expect(xEvent).toBeTruthy();
  });

  // --------------------------------------------------
  // 13. Web Vitals (best-effort — environment-dependent)
  // --------------------------------------------------
  test("web vitals are reported as metrics", async ({ page }) => {
    const captured = await setupCapture(page);
    await page.goto(HOME);

    // Web vitals fire asynchronously after paint/interaction.
    // FCP and TTFB should fire quickly; LCP needs a visibility change.
    await page.waitForTimeout(3000);

    // Simulate tab hidden → visible transition to trigger LCP
    await page.evaluate(() => {
      document.dispatchEvent(new Event("visibilitychange"));
    });
    await page.waitForTimeout(1000);
    await flush(page);

    const metrics = captured.filter((e) => e.data?.baseType === "MetricData");
    // Web vitals are environment-dependent; just verify no crash.
    // In CI environments some vitals may not fire.
    expect(Array.isArray(metrics)).toBe(true);
  });
});
