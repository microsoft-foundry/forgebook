import { test, expect } from "@playwright/test";

const HOME = "/forgebook";
const NOTEBOOK = "/forgebook/notebook/foundry-agent-part-1";

test.describe("Site Navigation", () => {
  test("homepage loads correctly", async ({ page }) => {
    await page.goto(HOME);
    await expect(page).toHaveTitle(/Forgebook/);
    await expect(page.getByRole("heading", { name: "Forgebook", level: 1 })).toBeVisible();
  });

  test("notebook card links to notebook page", async ({ page }) => {
    await page.goto(HOME);
    await page.getByRole("link", { name: /Create Your First Agent/ }).click();
    await expect(page).toHaveURL(/\/notebook\/foundry-agent-part-1/);
    await expect(page.getByRole("heading", { name: "Create Your First Agent (Part 1)", level: 1 })).toBeVisible();
  });

  test("notebook card tags stay on one row", async ({ page }) => {
    await page.goto(HOME);

    const rows = page.locator(".notebook-tags-row");
    await expect(rows.first()).toBeVisible();

    const wrappedRows = await rows.evaluateAll((elements) =>
      elements
        .map((row) => {
          const visibleChildren = Array.from(row.children).filter(
            (child) => !(child as HTMLElement).hidden,
          );
          const lineTops = new Set(
            visibleChildren.map((child) => Math.round(child.getBoundingClientRect().top)),
          );
          return {
            text: visibleChildren.map((child) => child.textContent?.trim()).join(" "),
            lineCount: lineTops.size,
          };
        })
        .filter((row) => row.lineCount > 1),
    );

    expect(wrappedRows).toEqual([]);
  });

  test("notebook page has action buttons", async ({ page }) => {
    await page.goto(NOTEBOOK);
    await expect(page.getByRole("link", { name: "Open in GitHub" })).toBeVisible();
    await expect(page.getByRole("button", { name: "Open options" })).toBeVisible();
    await expect(page.getByRole("button", { name: "Copy page" })).toBeVisible();
    await expect(page.getByRole("button", { name: "Markdown options" })).toBeVisible();
    await expect(page.getByRole("button", { name: "Share", exact: true })).toBeVisible();
    await expect(page.getByRole("button", { name: "Share options" })).toBeVisible();
  });

  test("header navigation works", async ({ page }) => {
    await page.goto(NOTEBOOK);
    await page.getByRole("link", { name: "Forgebook" }).click();
    await expect(page).toHaveURL(/\/forgebook\/?$/);
  });

  test("GitHub link points to correct repo", async ({ page }) => {
    await page.goto(HOME);
    const githubLink = page.getByRole("link", { name: "View on GitHub" });
    await expect(githubLink).toHaveAttribute("href", "https://github.com/microsoft-foundry/forgebook");
  });

  test("footer exposes public repository and legal links", async ({ page }) => {
    await page.goto(HOME);

    const footer = page.locator("footer");
    await expect(footer.getByRole("link", { name: "GitHub" })).toHaveAttribute("href", "https://github.com/microsoft-foundry/forgebook");
    await expect(footer.getByRole("link", { name: "License" })).toHaveAttribute("href", "https://github.com/microsoft-foundry/forgebook/blob/main/LICENSE");
    await expect(footer.getByRole("link", { name: "Code of Conduct" })).toHaveAttribute("href", "https://github.com/microsoft-foundry/forgebook/blob/main/CODE_OF_CONDUCT.md");
    await expect(footer.getByRole("link", { name: "Security" })).toHaveAttribute("href", "https://github.com/microsoft-foundry/forgebook/blob/main/SECURITY.md");
    await expect(footer.getByRole("link", { name: "Support" })).toHaveAttribute("href", "https://github.com/microsoft-foundry/forgebook/blob/main/SUPPORT.md");
    await expect(footer.getByRole("link", { name: "Privacy" })).toHaveAttribute("href", "https://privacy.microsoft.com/privacystatement");
    await expect(footer.getByRole("link", { name: "Terms of Use" })).toHaveAttribute("href", "https://www.microsoft.com/legal/terms-of-use");
    await expect(footer.getByRole("link", { name: "Trademarks" })).toHaveAttribute("href", "https://www.microsoft.com/legal/intellectualproperty/trademarks");
  });
});
