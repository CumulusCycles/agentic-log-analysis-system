import { test, expect } from "./fixtures";

test.describe("Error Detail screen (7e PR 4b)", () => {
  test("renders the friendly not-found copy for an unknown entry id", async ({
    loggedInPage: page,
  }) => {
    // 16 zero hex chars — well-formed but guaranteed not in Chroma.
    await page.goto("/errors/fnol:0000000000000000");

    // Wait for either the 404 copy OR the 503 banner (degraded mode when
    // OPENAI_API_KEY is the placeholder). Both are valid empty-corpus paths.
    const notFound = page.getByRole("heading", { name: /Entry not found/i });
    const unavailable = page.getByRole("heading", { name: /Error detail unavailable/i });
    await expect(notFound.or(unavailable)).toBeVisible();

    // The back-link is always rendered.
    await expect(page.getByRole("link", { name: /Back to Log Explorer/i }).first()).toBeVisible();
  });

  test("clicking View Error Detail on an ERROR row navigates to /errors/:id", async ({
    loggedInPage: page,
  }) => {
    await page.goto("/logs");
    // Narrow to ERROR rows only.
    await page.getByTestId("filter-level-DEBUG").uncheck();
    await page.getByTestId("filter-level-INFO").uncheck();
    await page.getByTestId("filter-level-WARN").uncheck();
    await page.waitForLoadState("networkidle");

    const errorRows = page
      .getByTestId("log-row")
      .filter({ has: page.locator('[data-level="ERROR"]') });
    const count = await errorRows.count();
    test.skip(count === 0, "no ERROR rows in the live stack — skipping detail navigation test");

    await errorRows.first().click();
    const link = page.getByTestId("view-detail-link").first();
    await expect(link).toBeVisible();
    await link.click();

    await expect(page).toHaveURL(/\/errors\/[a-z][a-z-]*%3A[0-9a-f]{16}/);

    // Either the Suggested Fix renders (Chroma has the entry) or the 404
    // copy renders (entry was filtered out of Chroma despite appearing in
    // the operator-facing /api/logs). Both are valid outcomes.
    const suggestedFix = page.getByRole("heading", { name: /Suggested Fix/i });
    const notFound = page.getByRole("heading", { name: /Entry not found/i });
    const unavailable = page.getByRole("heading", { name: /Error detail unavailable/i });
    await expect(suggestedFix.or(notFound).or(unavailable)).toBeVisible();
  });
});
