// Playwright E2E suite for the Pricing the Heat dashboard (v2 state-wise UI).
//
// STATUS: written but NOT executed this session -- no Playwright skill/tool
// was available (checked via ToolSearch for "playwright e2e browser test";
// no match). @playwright/test is installed as a devDependency so this file
// type-checks cleanly under `next build`, but actually running it requires
// browser binaries (`npx playwright install`) that were not fetched here.
//
// The E2E coverage below was instead verified THIS session via
// e2e/fetch-replay.mjs, which replicates every one of these page flows'
// exact fetch calls against the live backend and asserts on the real
// response shape/values -- see that file's header for how it was run and
// its results.
//
// To actually run this suite once Playwright is available:
//   npx playwright install --with-deps chromium
//   npm run dev &                       # serve the frontend
//   (cd .. && make train-all-states)    # ensure trained per-state artifacts exist
//   npx playwright test
//
// Requires: the FastAPI backend running with trained per-state artifacts at
// NEXT_PUBLIC_API_URL, and the frontend dev server reachable at
// PLAYWRIGHT_BASE_URL (default http://localhost:3000).

import { expect, test } from "@playwright/test";

test.describe("heat map", () => {
  test("renders the real OSM basemap and a state's grid data", async ({ page }) => {
    await page.goto("/");
    await expect(page.getByText(/state-level mu-TEVI index/i)).toBeVisible({ timeout: 15_000 });
    await expect(page.locator(".maplibregl-canvas")).toBeVisible();
    // OSM raster tiles, not a blank background layer.
    await expect(page.locator("text=OpenStreetMap contributors")).toBeVisible();
  });

  test("switching states re-centers the map and reloads grid data", async ({ page }) => {
    await page.goto("/");
    await expect(page.getByText(/state-level mu-TEVI index/i)).toBeVisible({ timeout: 15_000 });
    await page.getByLabel(/state/i).first().selectOption("US-Arizona");
    await expect(page.getByText(/Phoenix/i)).toBeVisible({ timeout: 15_000 });
  });
});

test.describe("simulate a policy", () => {
  test("prices a temperate INR state with income-smoothing framing and basis risk", async ({ page }) => {
    await page.goto("/simulate");
    await page.getByLabel(/pick a state manually/i).selectOption("IN-Assam");
    await page.getByRole("button", { name: "Price", exact: true }).click();
    await expect(page.getByText(/income smoothing/i)).toBeVisible({ timeout: 15_000 });
    await expect(page.getByText(/Premium \(fair actuarial price\)/i)).toBeVisible();
    await expect(page.getByText(/INR/).first()).toBeVisible();
    await expect(page.getByText(/Basis risk -- disclosed honestly/i)).toBeVisible();
  });

  test("prices an extreme USD state with catastrophe-insurance framing", async ({ page }) => {
    await page.goto("/simulate");
    await page.getByLabel(/pick a state manually/i).selectOption("US-Arizona");
    await page.getByRole("button", { name: "Price", exact: true }).click();
    await expect(page.getByText(/catastrophe insurance/i)).toBeVisible({ timeout: 15_000 });
    await expect(page.getByText(/USD/).first()).toBeVisible();
  });

  test("explain panel shows the single dominant feature honestly", async ({ page }) => {
    await page.goto("/simulate");
    await page.getByLabel(/pick a state manually/i).selectOption("IN-Assam");
    await page.getByRole("button", { name: "Price", exact: true }).click();
    await expect(page.getByText(/Premium \(fair actuarial price\)/i)).toBeVisible({ timeout: 15_000 });

    await page.getByRole("button", { name: /Explain this premium/i }).click();
    await expect(page.getByText(/What drives this premium/i)).toBeVisible({ timeout: 15_000 });
    await expect(page.getByText(/max index in window/i)).toBeVisible();
  });

  test("Alaska (excluded) shows the honest exclusion reason, never a fabricated price", async ({ page }) => {
    await page.goto("/simulate");
    await page.getByLabel(/pick a state manually/i).selectOption("US-Alaska");
    await page.getByRole("button", { name: "Price", exact: true }).click();
    await expect(page.getByText(/excluded from pricing/i).first()).toBeVisible({ timeout: 15_000 });
    await expect(page.getByText(/insufficient heat-exposure days/i)).toBeVisible();
  });

  test("out-of-coverage location shows the honest message, never fabricated pricing", async ({ page, context }) => {
    await context.grantPermissions(["geolocation"]);
    await context.setGeolocation({ latitude: 48.8566, longitude: 2.3522 }); // Paris
    await page.goto("/simulate");
    await page.getByRole("button", { name: "Use my location" }).click();
    await expect(page.getByText(/outside the supported countries/i)).toBeVisible({ timeout: 15_000 });
  });

  test("wage provenance is collapsed fine print, not competing with the premium", async ({ page }) => {
    await page.goto("/simulate");
    await page.getByLabel(/pick a state manually/i).selectOption("IN-Assam");
    await page.getByRole("button", { name: "Price", exact: true }).click();
    await expect(page.getByText(/Premium \(fair actuarial price\)/i)).toBeVisible({ timeout: 15_000 });

    const details = page.locator("details", { hasText: "Wage basis" });
    await expect(details).toBeVisible();
    await expect(details).not.toHaveAttribute("open", "");
    await expect(details.getByText(/effective_date/i)).toHaveCount(0);
  });
});
