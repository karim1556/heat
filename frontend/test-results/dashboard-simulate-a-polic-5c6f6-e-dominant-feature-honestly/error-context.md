# Instructions

- Following Playwright test failed.
- Explain why, be concise, respect Playwright best practices.
- Provide a snippet of code with the fix, if possible.

# Test info

- Name: dashboard.spec.ts >> simulate a policy >> explain panel shows the single dominant feature honestly
- Location: e2e/dashboard.spec.ts:63:7

# Error details

```
Test timeout of 30000ms exceeded.
```

```
Error: locator.click: Test timeout of 30000ms exceeded.
Call log:
  - waiting for getByRole('button', { name: /Explain this premium/i })

```

# Page snapshot

```yaml
- generic [active] [ref=e1]:
  - banner [ref=e2]:
    - generic [ref=e3]:
      - link "Pricing the Heat Climate Micro-Insurance AI" [ref=e4] [cursor=pointer]:
        - /url: /
        - generic [ref=e11]:
          - text: Pricing the Heat
          - generic [ref=e12]: Climate Micro-Insurance AI
      - navigation [ref=e13]:
        - link "Heat Map & Live Data" [ref=e14] [cursor=pointer]:
          - /url: /
        - link "Policy Simulator" [ref=e18] [cursor=pointer]:
          - /url: /simulate
        - link "Manager Dashboard" [ref=e22] [cursor=pointer]:
          - /url: /admin
        - link "Insurance Provider" [ref=e29] [cursor=pointer]:
          - /url: /insurance
        - link "Methodology & Models" [ref=e33] [cursor=pointer]:
          - /url: /methodology
      - generic [ref=e38]:
        - link "Log In" [ref=e39] [cursor=pointer]:
          - /url: /login
        - generic [ref=e44]: 79 STATES
  - main [ref=e49]:
    - generic [ref=e50]:
      - generic [ref=e51]: Interactive Parametric Pricer
      - heading "Simulate a Policy" [level=1] [ref=e55]
      - paragraph [ref=e56]: Price real heat-wage insurance policies for outdoor workers. Frame options (income smoothing vs catastrophe insurance) and local minimum wage scales are automatically determined per state.
    - generic [ref=e57]:
      - generic [ref=e59]:
        - heading "01. Configure Coverage Parameters" [level=2] [ref=e60]
        - generic [ref=e62]:
          - generic [ref=e63]: Occupation Type
          - generic [ref=e64]:
            - button "Street Vendor Outdoor market stall & retail vendors" [ref=e65] [cursor=pointer]:
              - generic [ref=e70]:
                - generic [ref=e71]: Street Vendor
                - paragraph [ref=e76]: Outdoor market stall & retail vendors
            - button "Construction Worker Heavy physical outdoor site work" [ref=e77] [cursor=pointer]:
              - generic [ref=e83]:
                - generic [ref=e84]: Construction Worker
                - paragraph [ref=e86]: Heavy physical outdoor site work
            - button "Delivery Rider Courier & last-mile transit riders" [ref=e87] [cursor=pointer]:
              - generic [ref=e94]:
                - generic [ref=e95]: Delivery Rider
                - paragraph [ref=e97]: Courier & last-mile transit riders
        - generic [ref=e98]:
          - generic [ref=e99]:
            - generic [ref=e100]: Coverage Window Length
            - generic [ref=e101]: "Default: 14d"
          - generic [ref=e102]:
            - button "14 Days State Default" [ref=e103] [cursor=pointer]:
              - text: 14 Days
              - generic [ref=e104]: State Default
            - button "30 Days" [ref=e105] [cursor=pointer]
            - button "60 Days" [ref=e106] [cursor=pointer]
            - button "90 Days" [ref=e107] [cursor=pointer]
        - generic [ref=e108]:
          - generic [ref=e109]:
            - generic [ref=e110]: Window Start Date
            - generic [ref=e111]: "Policy Ends: 2026-08-01"
          - textbox [ref=e113]: 2026-07-19
          - generic [ref=e114]:
            - generic [ref=e115]:
              - generic [ref=e116]: "Latest Available Weather:"
              - generic [ref=e120]: 2026-08-01
            - paragraph [ref=e121]:
              - text: Dates after
              - strong [ref=e122]: 2026-07-19
              - text: are locked for a 14-day window because 4-day NASA POWER satellite latency requires full observation data up to 2026-08-01.
        - generic [ref=e123]:
          - button "Use my location" [ref=e124] [cursor=pointer]:
            - generic [ref=e128]: Auto-Detect My Location
          - paragraph [ref=e129]: "Detected: Maharashtra, IN"
        - generic [ref=e130]:
          - generic [ref=e131]: Or Pick a State Manually
          - combobox "Or Pick a State Manually" [ref=e132]:
            - option "Alabama"
            - option "Alaska (Excluded)"
            - option "Arizona"
            - option "Arkansas"
            - option "California"
            - option "Colorado"
            - option "Connecticut"
            - option "Delaware"
            - option "District of Columbia"
            - option "Florida"
            - option "Georgia"
            - option "Hawaii"
            - option "Idaho"
            - option "Illinois"
            - option "Indiana"
            - option "Iowa"
            - option "Kansas"
            - option "Kentucky"
            - option "Louisiana"
            - option "Maine"
            - option "Maryland"
            - option "Massachusetts"
            - option "Michigan"
            - option "Minnesota"
            - option "Mississippi"
            - option "Missouri"
            - option "Montana"
            - option "Nebraska"
            - option "Nevada"
            - option "New Hampshire"
            - option "New Jersey"
            - option "New Mexico"
            - option "New York"
            - option "North Carolina"
            - option "North Dakota"
            - option "Ohio"
            - option "Oklahoma"
            - option "Oregon"
            - option "Pennsylvania"
            - option "Rhode Island"
            - option "South Carolina"
            - option "South Dakota"
            - option "Tennessee"
            - option "Texas"
            - option "Utah"
            - option "Vermont"
            - option "Virginia"
            - option "Washington"
            - option "West Virginia"
            - option "Wisconsin"
            - option "Wyoming"
            - option "Andhra Pradesh"
            - option "Arunachal Pradesh"
            - option "Assam"
            - option "Bihar"
            - option "Chhattisgarh"
            - option "Delhi"
            - option "Goa"
            - option "Gujarat"
            - option "Haryana"
            - option "Himachal Pradesh"
            - option "Jharkhand"
            - option "Karnataka"
            - option "Kerala"
            - option "Madhya Pradesh"
            - option "Maharashtra" [selected]
            - option "Manipur"
            - option "Meghalaya"
            - option "Mizoram"
            - option "Nagaland"
            - option "Odisha"
            - option "Punjab"
            - option "Rajasthan"
            - option "Sikkim"
            - option "Tamil Nadu"
            - option "Telangana"
            - option "Tripura"
            - option "Uttar Pradesh"
            - option "West Bengal"
          - button "Price" [ref=e133] [cursor=pointer]:
            - generic [ref=e137]: Price Policy For Selected Region
      - generic [ref=e139]:
        - generic [ref=e140]:
          - generic [ref=e141]:
            - generic [ref=e142]: Priced Policy Quote
            - heading "Maharashtra, IN" [level=2] [ref=e143]
            - generic [ref=e144]: "Occupation: vendor"
          - generic [ref=e145]: income smoothing
        - generic [ref=e147]:
          - generic [ref=e148]:
            - generic [ref=e149]: Premium (fair actuarial price)
            - generic [ref=e150]: INR 324.83
            - generic [ref=e151]: Pure actuarial loss cost
          - generic [ref=e152]:
            - generic [ref=e153]: Insurer Price (with Wang Risk Load)
            - generic [ref=e154]: INR 349.56
            - generic [ref=e155]: Loaded with capital risk margin
        - img [ref=e160]:
          - generic [ref=e164]:
            - generic [ref=e165]: Total Window Wage
            - generic [ref=e167]: Pure Premium
            - generic [ref=e169]: Loaded Premium
          - generic [ref=e172]:
            - generic [ref=e173]: INR 0
            - generic [ref=e175]: INR2000
            - generic [ref=e177]: INR4000
            - generic [ref=e179]: INR6000
            - generic [ref=e181]: INR8000
        - generic [ref=e192]:
          - generic [ref=e193]:
            - generic [ref=e194]: Parametric Payout Schedule
            - generic [ref=e195]: "Strike: 75"
          - img "Payout schedule chart" [ref=e197]:
            - generic [ref=e204]: "0"
            - generic [ref=e205]: "100"
            - generic [ref=e206]: "Strike: 75"
        - generic [ref=e207]:
          - generic [ref=e208]:
            - generic [ref=e209]: mu-TEVI Index History (Coverage Window)
            - generic [ref=e210]: 14 data points
          - img "mu-TEVI index series" [ref=e212]
        - generic [ref=e216]:
          - generic [ref=e217]: Basis risk -- disclosed honestly
          - generic [ref=e222]:
            - generic [ref=e223]:
              - generic [ref=e224]: Shortfall Rate
              - generic [ref=e225]: 53.7%
            - generic [ref=e226]:
              - generic [ref=e227]: Overpay Rate
              - generic [ref=e228]: 32.2%
            - generic [ref=e229]:
              - generic [ref=e230]: Correlation
              - generic [ref=e231]: "0.81"
          - img [ref=e236]:
            - generic [ref=e248]:
              - generic [ref=e249]: Trigger Accuracy
              - generic [ref=e251]: Shortfall Risk
              - generic [ref=e254]: Overpay Risk
            - generic [ref=e259]:
              - generic [ref=e260]: "0"
              - generic [ref=e262]: "25"
              - generic [ref=e264]: "50"
              - generic [ref=e266]: "75"
              - generic [ref=e268]: "100"
        - button "Explain Premium Contributions" [ref=e274] [cursor=pointer]
        - button "Wage Basis & Legal Minimum Wage Provenance" [ref=e280] [cursor=pointer]
        - generic [ref=e285]:
          - generic [ref=e292]:
            - heading "Groq AI Underwriter Dashboard LLaMA 3.3 70B" [level=3] [ref=e293]:
              - generic [ref=e294]: Groq AI Underwriter Dashboard
              - generic [ref=e295]: LLaMA 3.3 70B
            - paragraph [ref=e296]: Real-time Actuarial Analysis & Interactive Risk Policy Advisor
          - generic [ref=e297]:
            - generic [ref=e298]:
              - generic [ref=e299]: Automated Actuarial & Optimization Report
              - generic [ref=e305]:
                - generic [ref=e306]: AI Analysis Unavailable
                - paragraph [ref=e310]: "Error code: 400 - {'error': {'message': 'The model `llama3-8b-8192` has been decommissioned and is no longer supported. Please refer to https://console.groq.com/docs/deprecations for a recommendation on which model to use instead.', 'type': 'invalid_request_error', 'code': 'model_decommissioned'}}"
                - paragraph [ref=e311]: "Ensure `GROQ_API_KEY` is set in your backend `.env` file."
            - generic [ref=e312]:
              - generic [ref=e313]: Ask the Underwriter
              - generic [ref=e317]:
                - generic [ref=e319]:
                  - paragraph [ref=e323]: Ask any question about this policy quote
                  - generic [ref=e324]:
                    - button "\"Why is the premium set at this rate?\"" [ref=e325] [cursor=pointer]
                    - button "\"How can we lower the basis risk?\"" [ref=e326] [cursor=pointer]
                - generic [ref=e327]:
                  - textbox "Ask about risk, strike, payouts..." [ref=e328]
                  - button [disabled] [ref=e329]
  - contentinfo [ref=e333]:
    - generic [ref=e334]:
      - generic [ref=e335]: Parametric Heat Wage Insurance © 2026 Pricing the Heat
      - generic [ref=e339]:
        - generic [ref=e340]: NASA POWER API
        - generic [ref=e341]: STGCN Neural Net
        - generic [ref=e342]: Wang Copula Transformer
  - alert [ref=e343]
  - generic [ref=e344]: INR 0
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
> 69  |     await page.getByRole("button", { name: /Explain this premium/i }).click();
      |                                                                       ^ Error: locator.click: Test timeout of 30000ms exceeded.
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
  97  |     await expect(details).toBeVisible();
  98  |     await expect(details).not.toHaveAttribute("open", "");
  99  |     await expect(details.getByText(/effective_date/i)).toHaveCount(0);
  100 |   });
  101 | });
  102 | 
```