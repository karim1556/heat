# Heat Observatory UI Redesign

## Goal

Replace the current generic glass-card and gradient-heavy interface with a distinctive, accessible "Heat Observatory" visual system. The redesign will make Pricing the Heat feel like a credible climate-risk product for workers, group managers, and insurance providers while preserving all routes, API contracts, policy calculations, field names, and existing user flows.

## Design Read

This is a climate-risk platform for a mixed audience: workers need clarity, group managers need confident operations, and insurers need credible data. The visual language is a heat observatory: precise, atmospheric, and editorial rather than a generic AI dashboard.

Design dials:

- Design variance: 8. The public experience gets asymmetric map-led composition, while operational screens retain predictable scanning patterns.
- Motion intensity: 5. Motion communicates hierarchy and state changes only. It is disabled or simplified for reduced-motion preferences.
- Visual density: 6. Information stays compact enough for live data and operations without returning to card-wall layouts.

## Current-State Audit

The current application has a strong functional surface but an inconsistent visual system:

- Shared layout uses Inter, white glass panels, rounded corners, orange gradients, and pulse animations.
- The public home page contains the live map, metric cards, location controls, and model summary.
- The simulator is a form followed by a pricing result and basis-risk explanation.
- Manager, insurer, and super-admin pages are operational screens with cohort, worker, policy, trigger, and payout controls.
- Login and cohort join are self-service entry points.
- Methodology explains the four scientific models.

The redesign retires decorative gradients, repeated glass cards, broad shadow use, generic pulse effects, and the current one-size-fits-all header. It preserves the existing information architecture, route slugs, primary navigation labels, data copy, backend requests, and authentication behavior.

## Visual System

### Tokens

- Base surfaces: ink blue, charcoal, mist, and warm off-white. No pure black or pure white.
- Heat accents: ember orange for urgent heat, solar yellow for elevated heat, and mineral teal for verified or protected states.
- Typography: a high-character display face for editorial headings paired with a highly legible sans serif for UI and tabular data. Numbers use the existing mono variable where useful.
- Shape: 12px small controls, 18px panels, 28px hero surfaces. Radius values are consistent across all screens.
- Elevation: hairline borders and restrained shadow. Surfaces use color, texture, and spacing to establish depth instead of glass blur.

### Theme and Accessibility

- A single automatic theme system respects `prefers-color-scheme`, with matching semantic CSS variables for light and dark modes.
- Text and controls meet WCAG AA contrast; body text targets AAA where feasible.
- Visible focus rings, keyboard navigation, form labels, and error states remain intact.
- All nonessential animation is gated by `prefers-reduced-motion`.

## Shared Components

Create a small design foundation that all routes consume:

- `AppShell`: responsive header, navigation, account controls, footer, and page framing.
- `SectionHeading`: page title, concise context, and optional action without decorative micro-labels.
- `Surface`: semantic panel variants for standard, emphasized, warning, and data contexts.
- `Metric`: compact numeric readout with a readable label and status treatment.
- `ActionButton` and `Field`: consistent primary, secondary, destructive, and keyboard-focused interactions.
- `EmptyState`, `LoadingState`, and `InlineNotice`: accessible asynchronous-state patterns.

Existing charts, map behavior, modals, role selection, and authentication components keep their public APIs. Their styling is adapted rather than their data behavior being rewritten.

## Page Designs

### Public Heat Map (`/`)

The home route becomes the observatory. The map is the dominant object, framed by a quiet control rail, a real-time data strip, and compact climate metrics. The scientific explanation moves beneath the map into an asymmetric four-model narrative that uses the actual product language and avoids repeated equal cards. The simulation action remains visible and clear.

### Policy Simulator (`/simulate`)

The simulator becomes a two-stage workspace. Inputs use a calm, readable form column. The result area becomes a high-contrast policy sheet with premium, coverage period, payout triggers, and basis-risk disclosure given clear visual order. Existing location detection, state selection, submission, API errors, and AI assistance remain unchanged.

### Group Manager (`/admin`) and Insurance Provider (`/insurance`)

Operational pages use a denser command-center layout: a compact page header, metrics that identify the current operating state, responsive content bands, and task-focused forms. Cohorts, workers, active policies, payout approvals, templates, and audit data keep their current actions and fields. The distinction comes from hierarchy, not different interaction models.

### Super Admin (`/super-admin`)

This stays intentionally constrained and security-oriented. The redesign replaces theatrical secret-console styling with a formal access-management surface that makes user roles and enterprise keys easy to scan and operate.

### Methodology (`/methodology`)

This becomes an editorial science brief. The model sequence is expressed as a continuous data story with real diagrams and plain language, preserving all existing claims and methodology content.

### Authentication and Onboarding (`/login`, `/join/[cohortId]`)

Entry screens use the same observatory branding but remain short, focused, and mobile-first. No user fields, validation behavior, submission mechanics, or role semantics change.

## Motion

Motion exists only to clarify: route headings fade upward on entry, map controls receive feedback on state changes, and actionable surfaces respond to hover/focus. Use CSS transforms and opacity only. Do not add scroll listeners, perpetual decorative animations, fake live activity, or animation to tables/forms. The static reduced-motion layout must preserve every interaction.

## Responsive Behavior

- Desktop public pages use offset map-led grids and editorial negative space.
- Operations screens use stable columns that collapse to one readable column below 768px.
- Navigation remains operable on small screens without clipped labels or horizontal scrolling.
- Charts and map containers retain reserved dimensions to avoid layout shift.

## Implementation Boundaries

- No backend, database, pricing, model, or auth logic changes are in scope.
- No route slug, primary navigation label, form field name/order, or API request shape changes are in scope.
- No new externally hosted images are required. Existing maps, charts, and repository diagrams remain the visual evidence.
- New dependencies are avoided unless the existing stack cannot meet the behavior safely.

## Verification

- Add focused automated checks for shared UI behavior introduced by the redesign before implementation code is written.
- Run the existing Playwright suite and frontend production build with environment-only build values.
- Manually inspect the public map, simulator, each authenticated role state, auth screens, loading/error states, mobile widths, light mode, dark mode, keyboard focus, and reduced motion.
- Confirm `git diff` contains only redesign-related frontend files and the approved design documentation.

## Acceptance Criteria

The redesign is complete when every existing route renders with the new system, core product flows work unchanged, no generic glass-card or rainbow-gradient visual language remains, page hierarchy is clearer on desktop and mobile, and the frontend build plus relevant end-to-end checks pass.
