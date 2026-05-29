import { expect, test } from "@playwright/test";

const HOME = "/forgebook/";
const NOTEBOOK = "/forgebook/notebook/foundry-agent-part-1/";

async function readJsonLd(page: import("@playwright/test").Page) {
  const raw = await page.locator('script[type="application/ld+json"]').first().textContent();
  expect(raw).toBeTruthy();
  return JSON.parse(raw!);
}

test.describe("SEO metadata", () => {
  test("homepage exposes discovery metadata and WebSite JSON-LD", async ({ page }) => {
    await page.goto(HOME);

    await expect(page).toHaveTitle("Forgebook | Microsoft Foundry notebook recipes");
    await expect(page.locator('meta[name="description"]')).toHaveAttribute(
      "content",
      /Microsoft Foundry cookbook of runnable Jupyter notebook recipes/,
    );
    await expect(page.locator('link[rel="canonical"]')).toHaveAttribute(
      "href",
      "https://microsoft-foundry.github.io/forgebook/",
    );
    await expect(page.locator('meta[property="og:type"]')).toHaveAttribute("content", "website");
    await expect(page.locator('link[rel="alternate"][type="application/rss+xml"]')).toHaveAttribute(
      "href",
      "https://microsoft-foundry.github.io/forgebook/rss.xml",
    );

    const jsonLd = await readJsonLd(page);
    expect(jsonLd["@context"]).toBe("https://schema.org");
    expect(jsonLd["@graph"].some((node: { "@type": string }) => node["@type"] === "WebSite")).toBe(true);
    expect(jsonLd["@graph"].some((node: { "@type": string }) => node["@type"] === "Organization")).toBe(true);
  });

  test("recipe pages expose article metadata and TechArticle JSON-LD", async ({ page }) => {
    await page.goto(NOTEBOOK);

    await expect(page.getByRole("heading", { name: "Create Your First Agent (Part 1)", level: 1 })).toBeVisible();
    await expect(page.locator('link[rel="canonical"]')).toHaveAttribute(
      "href",
      "https://microsoft-foundry.github.io/forgebook/notebook/foundry-agent-part-1/",
    );
    await expect(page.locator('meta[property="og:type"]')).toHaveAttribute("content", "article");
    await expect(page.locator('meta[property="article:published_time"]')).toHaveAttribute(
      "content",
      "2026-06-02T00:00:00.000Z",
    );

    const jsonLd = await readJsonLd(page);
    const article = jsonLd["@graph"].find((node: { "@type": string }) => node["@type"] === "TechArticle");
    expect(article).toMatchObject({
      headline: "Create Your First Agent (Part 1)",
      learningResourceType: "Jupyter notebook recipe",
      programmingLanguage: "Python",
      isBasedOn: "https://github.com/microsoft-foundry/forgebook/blob/main/notebooks/foundry-agent-part-1.ipynb",
    });
    expect(article.author[0].name).toBeTruthy();
  });

  test("robots.txt and llms.txt expose crawl and AI discovery hints", async ({ page }) => {
    const robots = await page.request.get("/forgebook/robots.txt");
    expect(robots.ok()).toBe(true);
    expect(await robots.text()).toContain("Sitemap: https://microsoft-foundry.github.io/forgebook/sitemap-index.xml");

    const llms = await page.request.get("/forgebook/llms.txt");
    expect(llms.ok()).toBe(true);
    const llmsText = await llms.text();
    expect(llmsText).toContain("## Recipes");
    expect(llmsText).toContain("[Create Your First Agent (Part 1)](https://microsoft-foundry.github.io/forgebook/notebook/foundry-agent-part-1.md)");
    expect(llmsText).toContain("## Optional");
    expect(llmsText).not.toContain("Raw Markdown page:");
    expect(llmsText).not.toContain("Source notebook:");
  });

  test("sitemap includes homepage and recipe URLs", async ({ page }) => {
    const sitemap = await page.request.get("/forgebook/sitemap-index.xml");
    expect(sitemap.ok()).toBe(true);

    const sitemapIndex = await sitemap.text();
    const sitemapUrl = sitemapIndex.match(/<loc>([^<]+sitemap-[^<]+\.xml)<\/loc>/)?.[1];
    expect(sitemapUrl).toBeTruthy();

    const urls = await page.request.get(new URL(sitemapUrl!).pathname);
    expect(urls.ok()).toBe(true);
    const body = await urls.text();
    expect(body).toContain("https://microsoft-foundry.github.io/forgebook/");
    expect(body).toContain("https://microsoft-foundry.github.io/forgebook/notebook/foundry-agent-part-1/");
    expect(body).not.toContain("foundry-agent-part-1.md");
    expect(body).not.toContain("raw.md");
  });
});
