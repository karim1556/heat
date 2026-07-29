#!/usr/bin/env node
// E2E verification for the v2 state-wise API (replaces the v1 single-city
// Ahmedabad replay). No Playwright skill/tool was available (checked via
// ToolSearch for "playwright e2e browser test"; no match), so per this
// project's own fallback this script replicates each page's exact fetch
// calls against the LIVE backend and asserts on the real response
// shape/values. See dashboard.spec.ts alongside this file for the Playwright
// suite written for when a runner IS available.
//
// Requires: the FastAPI backend running with real trained artifacts for
// US-Arizona (catastrophe insurance), IN-Assam (income smoothing) and
// US-Alaska (excluded), reachable at API_URL (default http://localhost:8000).
//
// Usage: node e2e/fetch-replay.mjs
// Exits 0 if every check passes, 1 otherwise.

import assert from "node:assert/strict";

const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

let passed = 0;
let failed = 0;

async function check(name, fn) {
  try {
    await fn();
    passed += 1;
    console.log(`  PASS  ${name}`);
  } catch (err) {
    failed += 1;
    console.error(`  FAIL  ${name}`);
    console.error(`        ${err.message}`);
  }
}

async function main() {
  console.log(`E2E fetch-replay against ${API_URL}\n`);

  await check("GET /health returns ok", async () => {
    const r = await fetch(`${API_URL}/health`);
    assert.equal(r.status, 200);
    const body = await r.json();
    assert.equal(body.status, "ok");
  });

  await check("GET /states lists the real 79-state config", async () => {
    const r = await fetch(`${API_URL}/states`);
    assert.equal(r.status, 200);
    const body = await r.json();
    assert.equal(body.length, 79);
    const byKey = Object.fromEntries(body.map((row) => [row.state_key, row]));
    assert.ok(byKey["US-Arizona"], "expected US-Arizona in the state list");
    assert.ok(byKey["US-Alaska"], "expected US-Alaska in the state list");
  });

  await check("GET /heatmap?state_key=IN-Assam returns real per-node grid data", async () => {
    const r = await fetch(`${API_URL}/heatmap?state_key=IN-Assam&date=2023-12-31`);
    assert.equal(r.status, 200);
    const body = await r.json();
    assert.equal(body.type, "FeatureCollection");
    assert.ok(body.features.length > 0, "expected at least one grid cell");
    const props = body.features[0].properties;
    assert.ok("node_id" in props && "heat_index" in props && "mu_tevi" in props);
    assert.equal(typeof props.heat_index, "number");
    assert.equal(body.metadata.state_key, "IN-Assam");
  });

  let assamPolicyId;
  await check(
    "POST /simulate-policy (IN-Assam, income smoothing, INR) returns positive premiums + basis_risk",
    async () => {
      const r = await fetch(`${API_URL}/simulate-policy`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          state_key: "IN-Assam",
          occupation: "vendor",
          date_range: { start: "2019-06-01", end: "2019-06-14" },
        }),
      });
      assert.equal(r.status, 200);
      const body = await r.json();
      assert.equal(body.coverage_mode, "configured");
      assert.equal(body.frame, "income_smoothing");
      assert.equal(body.currency, "INR");
      assert.ok(body.premium_lsmc > 0, "expected a positive LSMC premium");
      assert.ok(body.premium_wang > 0, "expected a positive Wang-loaded premium");
      assert.ok(body.basis_risk, "expected a basis_risk block");
      for (const key of ["basis_risk_rmse", "shortfall_rate", "overpay_rate", "correlation"]) {
        assert.ok(key in body.basis_risk, `basis_risk missing ${key}`);
      }
      assert.ok(body.wage_provenance, "expected a wage_provenance block");
      assert.ok(!("effective_date" in body.wage_provenance), "wage_provenance must not invent effective_date");
      assamPolicyId = body.policy_id;
    },
  );

  await check(
    "POST /simulate-policy (US-Arizona via lat/lon, catastrophe insurance, USD) prices correctly",
    async () => {
      const r = await fetch(`${API_URL}/simulate-policy`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          occupation: "construction",
          date_range: { start: "2019-06-01", end: "2019-06-14" },
          lat: 33.541926,
          lon: -112.071938,
        }),
      });
      assert.equal(r.status, 200);
      const body = await r.json();
      assert.equal(body.coverage_mode, "configured");
      assert.equal(body.state_key, "US-Arizona");
      assert.equal(body.frame, "catastrophe_insurance");
      assert.equal(body.currency, "USD");
      assert.ok(body.premium_lsmc > 0, "expected a positive LSMC premium");
    },
  );

  await check("GET /explain/{policy_id} shows a real feature-contribution breakdown", async () => {
    assert.ok(assamPolicyId, "requires a priced policy from a previous check");
    const r = await fetch(`${API_URL}/explain/${assamPolicyId}`);
    assert.equal(r.status, 200);
    const body = await r.json();
    const values = Object.values(body.feature_contributions_normalized);
    const sum = values.reduce((a, b) => a + b, 0);
    assert.ok(Math.abs(sum - 1) < 1e-6, "normalized contributions must sum to 1");
  });

  await check("POST /simulate-policy (US-Alaska, excluded) returns the honest reason, no fabricated price", async () => {
    const r = await fetch(`${API_URL}/simulate-policy`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        state_key: "US-Alaska",
        occupation: "vendor",
        date_range: { start: "2019-06-01", end: "2019-06-14" },
      }),
    });
    assert.equal(r.status, 200);
    const body = await r.json();
    assert.equal(body.coverage_mode, "excluded");
    assert.equal(body.premium_lsmc, null);
    assert.ok(body.message.toLowerCase().includes("insufficient heat-exposure days"));
  });

  await check("POST /simulate-policy (out-of-coverage coordinate) returns the honest message with null premiums", async () => {
    const r = await fetch(`${API_URL}/simulate-policy`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        occupation: "vendor",
        date_range: { start: "2019-06-01", end: "2019-06-14" },
        lat: 48.8566, // Paris -- outside India/US
        lon: 2.3522,
      }),
    });
    assert.equal(r.status, 200);
    const body = await r.json();
    assert.equal(body.coverage_mode, "out_of_coverage");
    assert.equal(body.premium_lsmc, null);
    assert.equal(body.basis_risk, null);
    assert.ok(body.message, "expected an honest out-of-coverage message");
    assert.ok(body.note.toLowerCase().includes("no data was fabricated"));
  });

  console.log(`\n${passed} passed, ${failed} failed.`);
  if (failed > 0) {
    console.error("E2E fetch-replay FAILED.");
    process.exit(1);
  }
  console.log("E2E fetch-replay OK.");
}

main();
