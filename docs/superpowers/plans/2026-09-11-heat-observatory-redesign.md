# Heat Observatory UI Redesign Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Rebuild every frontend route around the approved Heat Observatory visual system while preserving all current application behavior and backend interfaces.

**Architecture:** Establish semantic CSS tokens and a small set of reusable UI primitives first. Migrate the global shell and public pricing experience next, then apply the same primitives to operational and access routes. Existing data fetching, state management, component APIs, form names, route names, and request payloads remain unchanged.

**Tech Stack:** Next.js 14 App Router, React 18, TypeScript, Tailwind CSS 3, Lucide React, MapLibre, Recharts, Playwright.

## Global Constraints

- Preserve all existing route slugs, primary navigation labels, form field names/order, API request shapes, pricing copy, and authentication behavior.
- Do not change backend, database, model, calculation, or Supabase behavior.
- Use semantic CSS variables for light and dark themes. Respect `prefers-color-scheme` and `prefers-reduced-motion`.
- Use no pure black or pure white, no glass-card utilities, no rainbow/orange-gradient primary surfaces, no decorative pulse loops, and no visible em dash or en dash characters.
- Reuse existing `lucide-react`, MapLibre, Recharts, and Tailwind dependencies. Do not introduce a component-library dependency.
- Every new visual behavior gets a focused Playwright assertion written and observed failing before the production change that satisfies it.

---

## File Map

| File | Responsibility |
| --- | --- |
| `frontend/app/globals.css` | Semantic colors, type scale, surface, control, focus, motion, dark-mode, and responsive utility classes. |
| `frontend/tailwind.config.js` | Font variables and design-token aliases consumed by existing Tailwind markup. |
| `frontend/components/AppShell.tsx` | Responsive global header, navigation, account area, footer, and page frame. |
| `frontend/components/ui.tsx` | `SectionHeading`, `Surface`, `Metric`, `InlineNotice`, and `LoadingState` primitives. |
| `frontend/app/layout.tsx` | Font loading, global metadata, and `AppShell` integration. |
| `frontend/app/page.tsx` | Public observatory map and science narrative composition. |
| `frontend/app/simulate/page.tsx` | Two-stage pricing workspace composition. |
| `frontend/app/admin/page.tsx` | Group-manager command-center composition. |
| `frontend/app/insurance/page.tsx` | Insurance-provider command-center composition. |
| `frontend/app/super-admin/page.tsx` | Security-oriented access-management composition. |
| `frontend/app/methodology/page.tsx` | Editorial science-brief composition and table styling. |
| `frontend/app/login/page.tsx` | Focused authentication screen composition. |
| `frontend/app/join/[cohortId]/page.tsx` | Mobile-first worker onboarding composition. |
| `frontend/components/AIUnderwriter.tsx` | Underwriter surface and interaction styling. |
| `frontend/components/PaymentModal.tsx` | Payment dialog surface and state styling. |
| `frontend/components/PayoutChart.tsx` | Chart frame and tooltip theme. |
| `frontend/components/PremiumBarChart.tsx` | Chart frame and tooltip theme. |
| `frontend/components/RiskRadarChart.tsx` | Chart frame and tooltip theme. |
| `frontend/components/FeatureBars.tsx` | Compact explanatory data markers. |
| `frontend/components/Sparkline.tsx` | Compact chart color and label treatment. |
| `frontend/components/ErrorBanner.tsx` | Inline failure treatment. |
| `frontend/e2e/dashboard.spec.ts` | Regression checks for stable navigation, observatory landmark, simulator output, and reduced-motion-safe rendering. |

## Task 1: Establish Visual Regression Contracts

**Files:**
- Modify: `frontend/e2e/dashboard.spec.ts`
- Modify: `frontend/playwright.config.ts`

**Interfaces:**
- Consumes: existing route text and controls on `/` and `/simulate`.
- Produces: durable browser assertions for the shared application shell and public pricing flow.

- [ ] **Step 1: Write failing shell and observatory tests**

Add this test block before changing layout markup. It intentionally fails because the current shell has no `data-testid="app-shell"` or `data-testid="observatory-map"` contract.

```ts
test.describe("heat observatory shell", () => {
  test("keeps the product navigation and map landmark available", async ({ page }) => {
    await page.goto("/");
    await expect(page.getByTestId("app-shell")).toBeVisible();
    await expect(page.getByRole("navigation", { name: "Primary navigation" })).toContainText(
      "Heat Map & Live Data",
    );
    await expect(page.getByTestId("observatory-map")).toBeVisible({ timeout: 15_000 });
  });

  test("keeps the simulator output and basis-risk disclosure reachable", async ({ page }) => {
    await page.goto("/simulate");
    await page.getByLabel(/pick a state manually/i).selectOption("IN-Assam");
    await page.getByRole("button", { name: "Price", exact: true }).click();
    await expect(page.getByTestId("policy-result")).toBeVisible({ timeout: 15_000 });
    await expect(page.getByText(/Basis risk -- disclosed honestly/i)).toBeVisible();
  });
});
```

- [ ] **Step 2: Run the focused tests and confirm the expected RED result**

Run: `cd frontend && npx playwright test e2e/dashboard.spec.ts --grep "heat observatory shell"`

Expected: failures that identify the missing `app-shell`, `observatory-map`, and `policy-result` contracts. If Chromium is absent, run `npx playwright install chromium` once, then repeat the command against a running frontend and backend.

- [ ] **Step 3: Configure stable browser execution**

Update `frontend/playwright.config.ts` to keep the existing base URL behavior and add a single Chromium project. Keep test execution serial while it depends on a shared local backend.

```ts
export default defineConfig({
  testDir: "./e2e",
  testMatch: /.*\.spec\.ts/,
  timeout: 30_000,
  fullyParallel: false,
  use: {
    baseURL: process.env.PLAYWRIGHT_BASE_URL || "http://localhost:3000",
    trace: "retain-on-failure",
  },
  projects: [{ name: "chromium", use: { browserName: "chromium" } }],
});
```

- [ ] **Step 4: Commit the test contract**

```bash
git add frontend/e2e/dashboard.spec.ts frontend/playwright.config.ts
git commit -m "test: define observatory UI contracts"
```

## Task 2: Build the Shared Heat Observatory System

**Files:**
- Create: `frontend/components/AppShell.tsx`
- Create: `frontend/components/ui.tsx`
- Modify: `frontend/app/globals.css`
- Modify: `frontend/tailwind.config.js`
- Modify: `frontend/app/layout.tsx`

**Interfaces:**
- Consumes: `UserNav` and the existing nav label/href pairs.
- Produces: `AppShell`, `SectionHeading`, `Surface`, `Metric`, `InlineNotice`, and `LoadingState` for every route.

- [ ] **Step 1: Write a failing shell landmark test**

Keep the first test from Task 1 enabled. Add an assertion that checks the shell exposes its landmark and applies the automatic theme hook.

```ts
await expect(page.getByTestId("app-shell")).toHaveAttribute("data-theme", "auto");
await expect(page.getByRole("contentinfo")).toContainText("Parametric Heat Wage Insurance");
```

- [ ] **Step 2: Run the shell test and confirm RED**

Run: `cd frontend && npx playwright test e2e/dashboard.spec.ts --grep "product navigation"`

Expected: failure because the current layout does not expose the theme contract.

- [ ] **Step 3: Implement semantic tokens and primitives**

In `globals.css`, define `:root` and `@media (prefers-color-scheme: dark)` variables for `--canvas`, `--surface`, `--surface-strong`, `--ink`, `--muted`, `--line`, `--ember`, `--solar`, `--mineral`, `--danger`, and `--focus`. Define `.obs-shell`, `.obs-surface`, `.obs-surface-strong`, `.obs-control`, `.obs-button-primary`, `.obs-button-secondary`, `.obs-kicker`, `.obs-metric`, and `.obs-notice` using those variables. Add reduced-motion rules that disable nonessential transitions.

Create the reusable primitives with this API:

```tsx
import type { ReactNode } from "react";

type SurfaceTone = "default" | "strong" | "warning" | "data";

export function Surface({ tone = "default", className = "", children }: {
  tone?: SurfaceTone;
  className?: string;
  children: ReactNode;
}) {
  return <section className={`obs-surface obs-surface-${tone} ${className}`}>{children}</section>;
}

export function SectionHeading({ title, description, action }: {
  title: string;
  description?: string;
  action?: ReactNode;
}) {
  return <header className="obs-section-heading"><div><h1>{title}</h1>{description ? <p>{description}</p> : null}</div>{action}</header>;
}

export function Metric({ label, value, detail, tone = "default" }: {
  label: string;
  value: ReactNode;
  detail?: string;
  tone?: SurfaceTone;
}) {
  return <div className={`obs-metric obs-metric-${tone}`}><span>{label}</span><strong>{value}</strong>{detail ? <small>{detail}</small> : null}</div>;
}
```

Implement `AppShell` with the exact existing navigation labels/hrefs, `<nav aria-label="Primary navigation">`, `<main>`, `<footer>`, `data-testid="app-shell"`, and `data-theme="auto"`. Move the header/footer ownership out of `layout.tsx` without changing `AuthProvider` or `UserNav` behavior. Replace Inter with a distinctive readable Next font pairing supported by `next/font/google`, retaining `JetBrains_Mono` for numeric data.

- [ ] **Step 4: Run the shell test and confirm GREEN**

Run: `cd frontend && npx playwright test e2e/dashboard.spec.ts --grep "product navigation"`

Expected: PASS with stable navigation and footer content in Chromium.

- [ ] **Step 5: Commit the shared system**

```bash
git add frontend/app/globals.css frontend/tailwind.config.js frontend/app/layout.tsx frontend/components/AppShell.tsx frontend/components/ui.tsx frontend/e2e/dashboard.spec.ts
git commit -m "feat: add heat observatory design system"
```

## Task 3: Recompose the Public Map and Policy Simulator

**Files:**
- Modify: `frontend/app/page.tsx`
- Modify: `frontend/app/simulate/page.tsx`
- Modify: `frontend/components/AIUnderwriter.tsx`
- Modify: `frontend/components/ErrorBanner.tsx`
- Modify: `frontend/components/PayoutChart.tsx`
- Modify: `frontend/components/PremiumBarChart.tsx`
- Modify: `frontend/components/RiskRadarChart.tsx`
- Modify: `frontend/components/FeatureBars.tsx`
- Modify: `frontend/components/Sparkline.tsx`
- Modify: `frontend/e2e/dashboard.spec.ts`

**Interfaces:**
- Consumes: current `getHeatmap`, `getStateBoundary`, `getStates`, `resolveLocation`, `simulatePolicy`, `explainPolicy`, chart props, and route controls.
- Produces: map landmark `data-testid="observatory-map"` and policy output landmark `data-testid="policy-result"` without changing data semantics.

- [ ] **Step 1: Write failing public-route assertions**

Add tests that verify visual-semantic landmarks while retaining the existing real-data checks.

```ts
await expect(page.getByTestId("observatory-map")).toHaveAttribute("aria-label", "Live heat severity map");
await expect(page.getByRole("link", { name: /Policy Simulator/i })).toBeVisible();
await expect(page.getByTestId("policy-result")).toContainText(/Premium \(fair actuarial price\)/i);
```

- [ ] **Step 2: Run the public-route assertions and confirm RED**

Run: `cd frontend && npx playwright test e2e/dashboard.spec.ts --grep "heat observatory shell|prices a temperate"`

Expected: landmark assertions fail before their markup is introduced. The existing simulation behavior still passes.

- [ ] **Step 3: Implement the public observatory composition**

Keep all state hooks, MapLibre initialization, heat surface generation, state/date controls, and fetch calls in `page.tsx`. Replace only the rendered composition:

- Wrap the map section in `<section data-testid="observatory-map" aria-label="Live heat severity map">`.
- Use a map-first grid with a compact control rail, a date/status strip, and semantic `Metric` readouts for minimum, average, maximum, humidity, and sample count.
- Replace equal model cards with four varied science narrative blocks using existing copy and Lucide icons.
- Keep every current form label, selection, location detection action, map attribution, popup, loading state, and error message.

In `simulate/page.tsx`, keep all input state and API calls. Recompose its JSX into an input `Surface` and a result `Surface tone="strong"` with `data-testid="policy-result"`. Keep exact tested labels, Price button name, income-smoothing/catastrophe framing, basis-risk disclosure, source details, explain action, and chart props.

Restyle charts and assistant components with semantic CSS variables and accessible tooltip contrast. Do not change their input prop interfaces or data transformations.

- [ ] **Step 4: Run route tests and production type check**

Run: `cd frontend && npx playwright test e2e/dashboard.spec.ts`

Expected: all heat-map and simulator tests pass.

Run: `cd frontend && NEXT_PUBLIC_SUPABASE_URL=https://example.supabase.co SUPABASE_SERVICE_ROLE_KEY=build-check-placeholder npm run build`

Expected: production build succeeds with no TypeScript errors.

- [ ] **Step 5: Commit the public experience**

```bash
git add frontend/app/page.tsx frontend/app/simulate/page.tsx frontend/components/AIUnderwriter.tsx frontend/components/ErrorBanner.tsx frontend/components/PayoutChart.tsx frontend/components/PremiumBarChart.tsx frontend/components/RiskRadarChart.tsx frontend/components/FeatureBars.tsx frontend/components/Sparkline.tsx frontend/e2e/dashboard.spec.ts
git commit -m "feat: redesign public heat and pricing experience"
```

## Task 4: Rebuild Operational Workspaces

**Files:**
- Modify: `frontend/app/admin/page.tsx`
- Modify: `frontend/app/insurance/page.tsx`
- Modify: `frontend/app/super-admin/page.tsx`
- Modify: `frontend/components/PaymentModal.tsx`
- Modify: `frontend/components/QrCodeGenerator.tsx`
- Modify: `frontend/components/RoleSwitcher.tsx`

**Interfaces:**
- Consumes: all existing API fetches, `useAuth`, role-switch functions, modal props, QR-generator props, and operational form state.
- Produces: responsive command-center layouts with identical business actions.

- [ ] **Step 1: Write failing route-shell checks**

Add a focused test that asserts each operations route retains a main heading and an accessible main landmark after the redesign.

```ts
for (const route of ["/admin", "/insurance", "/super-admin"]) {
  await page.goto(route);
  await expect(page.getByRole("main")).toBeVisible();
}
```

Add route-specific heading assertions using existing visible text: `Group Manager Authentication Required`, `Insurance Provider Authentication Required`, and `Secret Super Admin Console`.

- [ ] **Step 2: Run route-shell checks and confirm RED**

Run: `cd frontend && npx playwright test e2e/dashboard.spec.ts --grep "operations"`

Expected: failure until each route has a semantic `<main>` landmark or explicit accessible name.

- [ ] **Step 3: Implement command-center layouts**

Keep all existing data interfaces, effects, handlers, dialog state, form names, and submit semantics. Replace visual wrappers with:

- a compact `SectionHeading` and context metrics at the top of each operational screen;
- responsive content bands for approvals, cohorts, workers, policies, templates, and audit events;
- direct visual distinction for actionable, pending, completed, and error states through semantic `Surface` tones;
- tables and lists that remain horizontally scrollable only inside their data container;
- dialogs and QR content that use the same focus, background, and button system as the app shell.

Do not retain theatrical gradients, decorative Sparkles, or generic glowing cards. Do not alter hard-coded role credentials, role switching, endpoint paths, payloads, or button actions.

- [ ] **Step 4: Run route-shell checks and build**

Run: `cd frontend && npx playwright test e2e/dashboard.spec.ts --grep "operations"`

Expected: PASS.

Run: `cd frontend && NEXT_PUBLIC_SUPABASE_URL=https://example.supabase.co SUPABASE_SERVICE_ROLE_KEY=build-check-placeholder npm run build`

Expected: PASS.

- [ ] **Step 5: Commit operational redesign**

```bash
git add frontend/app/admin/page.tsx frontend/app/insurance/page.tsx frontend/app/super-admin/page.tsx frontend/components/PaymentModal.tsx frontend/components/QrCodeGenerator.tsx frontend/components/RoleSwitcher.tsx frontend/e2e/dashboard.spec.ts
git commit -m "feat: redesign operational workspaces"
```

## Task 5: Rebuild Methodology and Entry Flows

**Files:**
- Modify: `frontend/app/methodology/page.tsx`
- Modify: `frontend/app/login/page.tsx`
- Modify: `frontend/app/join/[cohortId]/page.tsx`
- Modify: `frontend/e2e/dashboard.spec.ts`

**Interfaces:**
- Consumes: current filesystem-backed methodology parsing, `AuthProvider` methods, cohort request, worker registration request, and existing field values.
- Produces: concise editorial methodology and focused, mobile-safe access screens.

- [ ] **Step 1: Write failing entry-flow landmark tests**

Add route checks that do not depend on private account data.

```ts
test("renders focused access surfaces", async ({ page }) => {
  await page.goto("/login");
  await expect(page.getByRole("main")).toBeVisible();
  await expect(page.getByRole("heading", { name: /Pricing the Heat/i })).toBeVisible();

  await page.goto("/methodology");
  await expect(page.getByRole("main")).toContainText("How Pricing the Heat Works");
});
```

- [ ] **Step 2: Run entry-flow checks and confirm RED**

Run: `cd frontend && npx playwright test e2e/dashboard.spec.ts --grep "focused access"`

Expected: failure until pages expose the new semantic main structure and title hierarchy.

- [ ] **Step 3: Implement editorial and access compositions**

Retain all methodology parsers, documents, tables, headings, and claims. Apply an editorial content width, strong reading rhythm, toned code/table surfaces, and a visual four-model sequence without changing source content.

Retain all login/signup validation, role choices, partner key validation, API calls, cohort lookup, worker registration fields, and success/error branches. Replace only wrappers, typography, controls, and responsive layout using the shared primitives. Keep forms one column on small screens, preserve visible labels, and reserve fixed space for async feedback.

- [ ] **Step 4: Run entry-flow tests and production build**

Run: `cd frontend && npx playwright test e2e/dashboard.spec.ts --grep "focused access"`

Expected: PASS.

Run: `cd frontend && NEXT_PUBLIC_SUPABASE_URL=https://example.supabase.co SUPABASE_SERVICE_ROLE_KEY=build-check-placeholder npm run build`

Expected: PASS.

- [ ] **Step 5: Commit methodology and access redesign**

```bash
git add frontend/app/methodology/page.tsx frontend/app/login/page.tsx 'frontend/app/join/[cohortId]/page.tsx' frontend/e2e/dashboard.spec.ts
git commit -m "feat: redesign methodology and access flows"
```

## Task 6: Run the Redesign Pre-Flight and Ship

**Files:**
- Modify only when a pre-flight finding requires a scoped correction.

**Interfaces:**
- Consumes: completed routes, shared primitives, current backend API, and e2e suite.
- Produces: a clean, verified redesign commit ready to push.

- [ ] **Step 1: Run static pre-flight checks**

Run these commands:

```bash
cd frontend
grep -RIn "glass-card\|text-gradient\|bg-gradient-to\|animate-pulse-glow" app components --include='*.tsx' || true
grep -RIn "—\|–" app components --include='*.tsx' || true
```

Expected: no active production use of retired glass-card, generic gradient, decorative pulse, em dash, or en dash patterns in redesigned UI files.

- [ ] **Step 2: Test reduced-motion and theme contracts manually**

Run the frontend with the backend available, then inspect `/`, `/simulate`, `/methodology`, `/login`, `/admin`, `/insurance`, and `/super-admin` at 375px, 768px, and 1440px. Inspect both system light and dark modes. Enable reduced motion and confirm no interaction becomes inaccessible or unreadable.

- [ ] **Step 3: Run automated verification**

Run:

```bash
cd frontend
npx playwright test
NEXT_PUBLIC_SUPABASE_URL=https://example.supabase.co SUPABASE_SERVICE_ROLE_KEY=build-check-placeholder npm run build
node e2e/fetch-replay.mjs
```

Expected: Playwright route tests, optimized build, and backend-response replay checks pass. If the local backend is unavailable, record the environment blocker and run the build before asking for a backend-enabled verification pass.

- [ ] **Step 4: Inspect the final diff**

Run: `git diff --check origin/master...HEAD && git status --short`

Expected: no whitespace errors and only intended frontend/design documentation changes.

- [ ] **Step 5: Commit and push the verified redesign**

```bash
git add frontend docs/superpowers
git commit -m "feat: ship heat observatory redesign"
git push origin HEAD:master
```

## Coverage Review

- Shared theme, accessibility, motion, token, and primitive requirements are covered by Task 2.
- Public map, simulator, chart, assistant, loading, and error requirements are covered by Task 3.
- Manager, insurer, super-admin, modal, QR, and role-control requirements are covered by Task 4.
- Methodology, login, and worker onboarding requirements are covered by Task 5.
- Responsive behavior, dark mode, reduced motion, visual-retirement checks, e2e, build, replay, and diff inspection are covered by Task 6.
