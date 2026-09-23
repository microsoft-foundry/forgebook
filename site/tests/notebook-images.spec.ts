import { test, expect } from "@playwright/test";

const NOTEBOOK = "/forgebook/notebook/foundry-agent-part-1";
const VIDEO_NOTEBOOK = "/forgebook/notebook/sora-video-generation-rest-api";

test.describe("Notebook Images", () => {
  test("OYD migration diagram and editable source resolve under the site base", async ({ page, baseURL }) => {
    const basePath = new URL(baseURL ?? "http://localhost:4321/forgebook").pathname.replace(/\/+$/, "");
    const mediaPath = `${basePath}/notebook/media/migrate-oyd-to-foundry-iq/01-oyd-migration-decision-tree`;
    await page.goto(`${basePath}/notebook/migrate-oyd-to-foundry-iq/`);

    const diagram = page.getByRole("img", { name: /^Migration decision tree:/ });
    await expect(diagram).toHaveAttribute("src", `${mediaPath}.png`);
    await expect(diagram).toBeVisible();
    await expect.poll(() => diagram.evaluate((image: HTMLImageElement) => image.naturalWidth)).toBeGreaterThan(0);

    const source = page.getByRole("link", { name: "Download editable Excalidraw source" });
    await expect(source).toHaveAttribute("href", `${mediaPath}.excalidraw`);
    const response = await page.request.get(`${mediaPath}.excalidraw`);
    expect(response.status()).toBe(200);
    const scene = await response.json();
    expect(scene).toMatchObject({ type: "excalidraw", version: 2 });
    expect(scene.elements).toEqual(expect.arrayContaining([
      expect.objectContaining({ type: "text", text: "Direct KB answers\nAuto + answer synthesis" }),
      expect.objectContaining({ type: "text", text: "Foundry Prompt Agent + KB\nUse the KB as a knowledge tool" }),
    ]));
  });

  test("all images on notebook page have absolute src paths", async ({ page }) => {
    await page.goto(NOTEBOOK);

    const images = page.locator(".notebook-content img");
    const count = await images.count();
    expect(count).toBeGreaterThan(0);

    for (let i = 0; i < count; i++) {
      const src = await images.nth(i).getAttribute("src");
      expect(src).toBeTruthy();
      // Every src should be absolute (/...), a data URI, or an external URL — never a bare relative path
      expect(
        src!.startsWith("/") || src!.startsWith("data:") || src!.startsWith("http"),
        `Image ${i} has relative src: ${src}`,
      ).toBe(true);
    }
  });

  test("notebook images return 200", async ({ page }) => {
    await page.goto(NOTEBOOK);

    const images = page.locator(".notebook-content img");
    const count = await images.count();
    expect(count).toBeGreaterThan(0);

    // Collect unique non-data-URI image URLs
    const urls = new Set<string>();
    for (let i = 0; i < count; i++) {
      const src = await images.nth(i).getAttribute("src");
      if (src && !src.startsWith("data:")) {
        urls.add(new URL(src, page.url()).href);
      }
    }

    // Verify each image URL returns 200
    for (const url of urls) {
      const response = await page.request.get(url);
      expect(response.status(), `Broken image: ${url}`).toBe(200);
    }
  });

  test("notebook media sources use absolute paths", async ({ page }) => {
    await page.goto(VIDEO_NOTEBOOK);

    const media = page.locator(".notebook-content video, .notebook-content audio, .notebook-content source, .notebook-content track");
    const count = await media.count();
    expect(count).toBeGreaterThan(0);

    for (let i = 0; i < count; i++) {
      const src = await media.nth(i).getAttribute("src");
      if (!src) continue;

      expect(
        src.startsWith("/") || src.startsWith("data:") || src.startsWith("http"),
        `Media ${i} has relative src: ${src}`,
      ).toBe(true);
    }
  });

  test("notebook media sources return 200", async ({ page }) => {
    await page.goto(VIDEO_NOTEBOOK);

    const media = page.locator(".notebook-content video, .notebook-content audio, .notebook-content source, .notebook-content track");
    const count = await media.count();
    expect(count).toBeGreaterThan(0);

    const urls = new Set<string>();
    for (let i = 0; i < count; i++) {
      const src = await media.nth(i).getAttribute("src");
      if (src && !src.startsWith("data:")) {
        urls.add(new URL(src, page.url()).href);
      }
    }

    for (const url of urls) {
      const response = await page.request.get(url);
      expect(response.status(), `Broken media: ${url}`).toBe(200);
    }
  });
});
