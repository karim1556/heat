# Instructions

- Following Playwright test failed.
- Explain why, be concise, respect Playwright best practices.
- Provide a snippet of code with the fix, if possible.

# Test info

- Name: dashboard.spec.ts >> simulate a policy >> wage provenance is collapsed fine print, not competing with the premium
- Location: e2e/dashboard.spec.ts:90:7

# Error details

```
Error: expect(locator).toBeVisible() failed

Locator: locator('details').filter({ hasText: 'Wage basis' })
Expected: visible
Timeout: 5000ms
Error: element(s) not found

Call log:
  - Expect "toBeVisible" with timeout 5000ms
  - waiting for locator('details').filter({ hasText: 'Wage basis' })

```

```yaml
- banner:
  - link "Pricing the Heat Climate Micro-Insurance AI":
    - /url: /
  - navigation:
    - link "Heat Map & Live Data":
      - /url: /
    - link "Policy Simulator":
      - /url: /simulate
    - link "Manager Dashboard":
      - /url: /admin
    - link "Insurance Provider":
      - /url: /insurance
    - link "Methodology & Models":
      - /url: /methodology
  - link "Log In":
    - /url: /login
  - text: 79 STATES
- main:
  - text: Interactive Parametric Pricer
  - heading "Simulate a Policy" [level=1]
  - paragraph: Price real heat-wage insurance policies for outdoor workers. Frame options (income smoothing vs catastrophe insurance) and local minimum wage scales are automatically determined per state.
  - heading "01. Configure Coverage Parameters" [level=2]
  - text: Occupation Type
  - button "Street Vendor Outdoor market stall & retail vendors":
    - text: Street Vendor
    - paragraph: Outdoor market stall & retail vendors
  - button "Construction Worker Heavy physical outdoor site work":
    - text: Construction Worker
    - paragraph: Heavy physical outdoor site work
  - button "Delivery Rider Courier & last-mile transit riders":
    - text: Delivery Rider
    - paragraph: Courier & last-mile transit riders
  - text: "Coverage Window Length Default: 14d"
  - button "14 Days State Default"
  - button "30 Days"
  - button "60 Days"
  - button "90 Days"
  - text: "Window Start Date Policy Ends: 2026-08-01"
  - textbox: 2026-07-19
  - text: "Latest Available Weather: 2026-08-01"
  - paragraph:
    - text: Dates after
    - strong: 2026-07-19
    - text: are locked for a 14-day window because 4-day NASA POWER satellite latency requires full observation data up to 2026-08-01.
  - button "Use my location": Auto-Detect My Location
  - paragraph: "Detected: Maharashtra, IN"
  - text: Or Pick a State Manually
  - combobox "Or Pick a State Manually"
  - button "Price": Price Policy For Selected Region
  - text: Priced Policy Quote
  - heading "Maharashtra, IN" [level=2]
  - text: "Occupation: vendor income smoothing Premium (fair actuarial price) INR 324.83 Pure actuarial loss cost Insurer Price (with Wang Risk Load) INR 349.56 Loaded with capital risk margin"
  - img: Total Window Wage Pure Premium Loaded Premium INR 0 INR 2000 INR 4000 INR6000 INR 8000
  - text: "Parametric Payout Schedule Strike: 75"
  - img "Payout schedule chart": "0 100 Strike: 75"
  - text: mu-TEVI Index History (Coverage Window) 14 data points
  - img "mu-TEVI index series"
  - text: Basis risk -- disclosed honestly Shortfall Rate 53.7% Overpay Rate 32.2% Correlation 0.81
  - img: Trigger Accuracy Shortfall Risk Overpay Risk 0 25 50 75 100
  - button "Explain Premium Contributions"
  - button "Wage Basis & Legal Minimum Wage Provenance"
  - heading "Groq AI Underwriter Dashboard LLaMA 3.3 70B" [level=3]
  - paragraph: Real-time Actuarial Analysis & Interactive Risk Policy Advisor
  - text: Automated Actuarial & Optimization Report AI Analysis Unavailable
  - paragraph: "Error code: 400 - {'error': {'message': 'The model `llama3-8b-8192` has been decommissioned and is no longer supported. Please refer to https://console.groq.com/docs/deprecations for a recommendation on which model to use instead.', 'type': 'invalid_request_error', 'code': 'model_decommissioned'}}"
  - paragraph: "Ensure `GROQ_API_KEY` is set in your backend `.env` file."
  - text: Ask the Underwriter
  - paragraph: Ask any question about this policy quote
  - button "\"Why is the premium set at this rate?\""
  - button "\"How can we lower the basis risk?\""
  - textbox "Ask about risk, strike, payouts..."
  - button [disabled]
- contentinfo: Parametric Heat Wage Insurance © 2026 Pricing the Heat NASA POWER API STGCN Neural Net Wang Copula Transformer
- alert
```

# Test source

```ts
  1   | // Playwright E2E suite for the Pricing the Heat dashboard (v2 state-wise UI).
  2   | //
  3   | // STATUS: written but NOT executed this session -- no Playwright skill/tool
  4   | // was available (checked via ToolSearch for "playwright e2e browser test";
  5   | // no match). @playwright/test is installed as a devDependency so this file
  6   | // type-checks cleanly under `next build`, but actually running it requires
  7   | // browser binaries (`npx playwright install`) that were not fetched here.
  8   | //
  9   | // The E2E coverage below was instead verified THIS session via
  10  | // e2e/fetch-replay.mjs, which replicates every one of these page flows'
  11  | // exact fetch calls against the live backend and asserts on the real
  12  | // response shape/values -- see that file's header for how it was run and
  13  | // its results.
  14  | //
  15  | // To actually run this suite once Playwright is available:
  16  | //   npx playwright install --with-deps chromium
  17  | //   npm run dev &                       # serve the frontend
  18  | //   (cd .. && make train-all-states)    # ensure trained per-state artifacts exist
  19  | //   npx playwright test
  20  | //
  21  | // Requires: the FastAPI backend running with trained per-state artifacts at
  22  | // NEXT_PUBLIC_API_URL, and the frontend dev server reachable at
  23  | // PLAYWRIGHT_BASE_URL (default http://localhost:3000).
  24  | 
  25  | import { expect, test } from "@playwright/test";
  26  | 
  27  | test.describe("heat map", () => {
  28  |   test("renders the real OSM basemap and a state's grid data", async ({ page }) => {
  29  |     await page.goto("/");
  30  |     await expect(page.getByText(/state-level mu-TEVI index/i)).toBeVisible({ timeout: 15_000 });
  31  |     await expect(page.locator(".maplibregl-canvas")).toBeVisible();
  32  |     // OSM raster tiles, not a blank background layer.
  33  |     await expect(page.locator("text=OpenStreetMap contributors")).toBeVisible();
  34  |   });
  35  | 
  36  |   test("switching states re-centers the map and reloads grid data", async ({ page }) => {
  37  |     await page.goto("/");
  38  |     await expect(page.getByText(/state-level mu-TEVI index/i)).toBeVisible({ timeout: 15_000 });
  39  |     await page.getByLabel(/state/i).first().selectOption("US-Arizona");
  40  |     await expect(page.getByText(/Phoenix/i)).toBeVisible({ timeout: 15_000 });
  41  |   });
  42  | });
  43  | 
  44  | test.describe("simulate a policy", () => {
  45  |   test("prices a temperate INR state with income-smoothing framing and basis risk", async ({ page }) => {
  46  |     await page.goto("/simulate");
  47  |     await page.getByLabel(/pick a state manually/i).selectOption("IN-Assam");
  48  |     await page.getByRole("button", { name: "Price", exact: true }).click();
  49  |     await expect(page.getByText(/income smoothing/i)).toBeVisible({ timeout: 15_000 });
  50  |     await expect(page.getByText(/Premium \(fair actuarial price\)/i)).toBeVisible();
  51  |     await expect(page.getByText(/INR/).first()).toBeVisible();
  52  |     await expect(page.getByText(/Basis risk -- disclosed honestly/i)).toBeVisible();
  53  |   });
  54  | 
  55  |   test("prices an extreme USD state with catastrophe-insurance framing", async ({ page }) => {
  56  |     await page.goto("/simulate");
  57  |     await page.getByLabel(/pick a state manually/i).selectOption("US-Arizona");
  58  |     await page.getByRole("button", { name: "Price", exact: true }).click();
  59  |     await expect(page.getByText(/catastrophe insurance/i)).toBeVisible({ timeout: 15_000 });
  60  |     await expect(page.getByText(/USD/).first()).toBeVisible();
  61  |   });
  62  | 
  63  |   test("explain panel shows the single dominant feature honestly", async ({ page }) => {
  64  |     await page.goto("/simulate");
  65  |     await page.getByLabel(/pick a state manually/i).selectOption("IN-Assam");
  66  |     await page.getByRole("button", { name: "Price", exact: true }).click();
  67  |     await expect(page.getByText(/Premium \(fair actuarial price\)/i)).toBeVisible({ timeout: 15_000 });
  68  | 
  69  |     await page.getByRole("button", { name: /Explain this premium/i }).click();
  70  |     await expect(page.getByText(/What drives this premium/i)).toBeVisible({ timeout: 15_000 });
  71  |     await expect(page.getByText(/max index in window/i)).toBeVisible();
  72  |   });
  73  | 
  74  |   test("Alaska (excluded) shows the honest exclusion reason, never a fabricated price", async ({ page }) => {
  75  |     await page.goto("/simulate");
  76  |     await page.getByLabel(/pick a state manually/i).selectOption("US-Alaska");
  77  |     await page.getByRole("button", { name: "Price", exact: true }).click();
  78  |     await expect(page.getByText(/excluded from pricing/i).first()).toBeVisible({ timeout: 15_000 });
  79  |     await expect(page.getByText(/insufficient heat-exposure days/i)).toBeVisible();
  80  |   });
  81  | 
  82  |   test("out-of-coverage location shows the honest message, never fabricated pricing", async ({ page, context }) => {
  83  |     await context.grantPermissions(["geolocation"]);
  84  |     await context.setGeolocation({ latitude: 48.8566, longitude: 2.3522 }); // Paris
  85  |     await page.goto("/simulate");
  86  |     await page.getByRole("button", { name: "Use my location" }).click();
  87  |     await expect(page.getByText(/outside the supported countries/i)).toBeVisible({ timeout: 15_000 });
  88  |   });
  89  | 
  90  |   test("wage provenance is collapsed fine print, not competing with the premium", async ({ page }) => {
  91  |     await page.goto("/simulate");
  92  |     await page.getByLabel(/pick a state manually/i).selectOption("IN-Assam");
  93  |     await page.getByRole("button", { name: "Price", exact: true }).click();
  94  |     await expect(page.getByText(/Premium \(fair actuarial price\)/i)).toBeVisible({ timeout: 15_000 });
  95  | 
  96  |     const details = page.locator("details", { hasText: "Wage basis" });
> 97  |     await expect(details).toBeVisible();
      |                           ^ Error: expect(locator).toBeVisible() failed
  98  |     await expect(details).not.toHaveAttribute("open", "");
  99  |     await expect(details.getByText(/effective_date/i)).toHaveCount(0);
  100 |   });
  101 | });
  102 | 
```