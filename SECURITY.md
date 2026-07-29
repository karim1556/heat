# Security review (Prompt 11)

This documents the security hardening pass run on 2026-07-18: `pip-audit` on
backend dependencies, `npm audit --production` on the frontend, `bandit -r`
on backend/models Python code, and a full git-history + working-tree secret
scan. No dedicated "trailofbits" skill/tool was available this session, so
these were run manually with the actual CLI tools.

Everything rated medium or higher was either fixed or is documented below
with the specific reason it was not, per the standing rule: **fix what's
fixable safely; document what genuinely isn't, and say why.**

## Fixed

| Package | Was | Now | Why |
|---|---|---|---|
| `python-dotenv` | 1.0.1 | 1.2.2 | PYSEC-2026-2270 (symlink-following file overwrite in `set_key`/`unset_key`, which this repo doesn't even call) -- safe patch bump, zero risk. |
| `requests` | 2.32.3 | 2.33.0 | PYSEC-2026-1872 (`.netrc` credential leak via crafted URLs) and PYSEC-2026-2275 (`extract_zipped_paths()` predictable temp path) -- neither code path is used here, but this library makes real outbound calls (NASA POWER, World Bank) so a defense-in-depth patch bump is cheap and safe. |

Also fixed live during E2E verification: `backend/main.py`'s `/simulate-policy`
`note` field said "(NOT catastrophe insurance)" -- a Prompt 7-era string that
predates Prompt 9's stricter "never say catastrophe" framing rule. Caught by
the new `frontend/e2e/fetch-replay.mjs` check and fixed to "(not cover for a
rare, one-off disaster)".

## Deliberately not fixed (with reason)

### `starlette` 0.37.2 -- multiple CVEs, fixes require 0.40.0 through 1.3.1

FastAPI 0.111.0 hard-pins `starlette>=0.37.2,<0.38.0` (confirmed via
`importlib.metadata.requires("fastapi")`); 0.37.2 is already the newest patch
in that pinned range, so there is no in-range fix. Reaching any fixed version
requires bumping FastAPI itself to a newer minor/major release -- a
materially larger change than a hardening pass, with real regression risk to
an already-tested 181-test backend.

More importantly, every one of the flagged CVEs requires a code path this
app does not exercise:
- Host-header / request-path URL-reconstruction bypasses (PYSEC-2026-161,
  -248) only matter to code that makes security decisions from
  `request.url`/`request.url.path` -- this app never does (no such
  middleware or route logic exists in `backend/main.py`).
- Unbounded multipart form-field DoS (PYSEC-2026-1943, -1941, -249) only
  applies to routes that call `request.form()` / accept `UploadFile` /
  `Form(...)` -- every POST route here takes a Pydantic JSON body instead
  (verified: `grep -n "Form(\|UploadFile\|StaticFiles\|HTTPEndpoint\|request\.url" backend/main.py` is empty).
- Windows UNC-path SSRF via `StaticFiles` (PYSEC-2026-2281) -- this app
  serves no static files.
- `HTTPEndpoint` subclass method-dispatch confusion (PYSEC-2026-2280) --
  every route here is a plain `@app.get`/`@app.post` function, never a
  class-based `HTTPEndpoint`.

**Recommendation for a real deployment**: bump FastAPI (and re-run the full
test suite) before putting this behind a public, multi-tenant endpoint.

### `pytest` 8.2.2 -- PYSEC-2026-1845 (predictable `/tmp/pytest-of-{user}` dir)

Dev/test-only dependency; never ships in the running API, so it is not part
of the deployed attack surface at all. The fix is a 8→9 major version bump,
which is a real compatibility risk to the existing 181-test suite for a
local-only, low-severity issue. Not attempted.

### `pyarrow` 16.1.0 -- PYSEC-2024-161, PYSEC-2026-113

Both advisories explicitly state they do **not** affect the PyArrow Python
bindings this project uses: PYSEC-2024-161 is scoped to "the arrow R package,
not other Apache Arrow implementations or bindings"; PYSEC-2026-113's
vulnerable API "is not exposed in language bindings (Python, Ruby, C GLib)".
Confirmed non-applicable; left at the pinned version to avoid an unnecessary
Parquet-compatibility risk to `data/processed/*.parquet` for zero real
benefit.

### `torch` 2.3.1 -- 22 findings (pip-audit against `requirements-torch.txt`)

Reviewed every finding's description. They fall into two buckets, neither of
which this app exposes:
1. **Deserialization RCE via `torch.load`** (PYSEC-2025-41, PYSEC-2024-259,
   PYSEC-2026-139, PYSEC-2026-2286) -- exploitable only if an attacker can
   substitute the file being loaded. Every `torch.load` call in this repo
   (`backend/main.py`, `models/stgcn/evaluate_spatial.py`) reads a
   **hardcoded, server-authored path constant** (`models/artifacts/stgcn.pt`,
   `models/artifacts/forecaster.pt`) -- never a path built from a request
   parameter -- so no network-reachable input can substitute a malicious
   checkpoint. See the `# nosec B614` comments at each call site.
2. **Memory corruption / DoS in specific low-level ops** (e.g.
   `torch.lstm_cell`, `torch.nn.utils.rnn.pad_packed_sequence`,
   `torch.jit.script`, `torch.mkldnn_max_pool2d`) -- these require an
   attacker to control the shape/content of the tensor fed into that
   specific op. `/heatmap`'s only client input (`date`) indexes into
   real, pre-fetched weather data server-side; `/forecast`'s only input
   (`horizon_days`) only slices a precomputed output array's length. No
   request parameter ever shapes or populates tensor content in this app.

A fix requires a major-version torch bump (2.3 -> 2.9+), which would need
retraining and re-verifying every artifact (STGCN, PPO, GRU forecaster) to
confirm the project's determinism/reproducibility guarantees (CLAUDE.md
Golden Rule 3) still hold -- squarely out of scope for a hardening-only pass,
and not exploitable via this app's actual code paths today.

### Frontend: `next` 14.2.35 -- multiple advisories, fix is `next@16.2.10`

`npm audit --production` flags Next.js for Image Optimizer DoS, RSC cache
poisoning/DoS, middleware/proxy cache poisoning, CSP-nonce XSS,
`beforeInteractive` script XSS, and WebSocket-upgrade SSRF. Every one of
these requires a feature this dashboard doesn't use -- confirmed via
`grep -rn "next/image\|next/script\|middleware\|rewrites\|redirects\|WebSocket" app/ components/ lib/ next.config.js`
(no matches). This is a 4-page, client-fetch-only static dashboard with no
middleware, no Image Optimizer usage, no Server Actions, no WebSockets.

The fix (`next@16.2.10`) is a two-major-version jump that `npm audit` itself
flags as a breaking change (React version bump, App Router changes, config
surface changes) -- out of scope for this pass given no exploitable surface
exists today. **Recommendation**: revisit before adding any of the above
features, or before a production deploy.

## bandit (Python security scan)

`bandit -r backend/ models/ -ll` (medium+ severity) found 4 issues, all the
same root cause: `torch.load(..., weights_only=False)` (x3) and
`pickle.load()` (x1) used to deserialize this project's own trained
artifacts. As detailed in the torch section above, every one of these reads
from a hardcoded path constant never influenced by request input, so they
are not exploitable via this app's API surface. Each site now carries an
explicit `# nosec B614` / `# nosec B301` with an inline justification
comment pointing back to this file. **`bandit -r backend/ models/ -ll` is
clean (0 medium/high findings)** after these documented suppressions.

Three Low-severity findings remain (below the DoD's "medium or higher" bar,
left as-is):
- Two `B403` (`import pickle`) -- companion warnings to the `pickle.load`
  finding above; same accepted-risk reasoning.
- One `B110` (`try/except/pass`) in `models/behavioral_agent/ppo_rllib.py`'s
  `finally` block, swallowing a possible `ray.shutdown()` failure during
  cleanup of an explicitly optional, best-effort comparison path (the code's
  own comment: "optional path, build unaffected"). Legitimate defensive
  cleanup, not a real risk.

## Secrets

- `git log -p --all` grepped for `sk-ant`, `api[_-]?key\s*=`,
  `password\s*=`, `secret\s*=` (case-insensitive): the only matches are the
  `os.environ.get("ANTHROPIC_API_KEY", ...)` code pattern (not a secret) and
  two placeholder values in `.env.example`
  (`POSTGRES_PASSWORD=postgres`, `ANTHROPIC_API_KEY=your_api_key_here`).
  No real credential has ever been committed.
- `.env` is gitignored, was never tracked (`git ls-files` confirms), and does
  not currently exist on disk. Only `.env.example` (placeholders only) is
  tracked.
- A broader working-tree grep for live-looking patterns (`sk-ant-...`, AWS
  `AKIA...` keys, PEM private-key headers) across `.py`/`.ts`/`.tsx`/`.js`/
  `.json`/`.yaml`/`.env*` found nothing.

## E2E verification method

No Playwright skill/tool was available this session (checked via
`ToolSearch`). Per this prompt's own fallback clause:
- `frontend/e2e/dashboard.spec.ts` -- the full Playwright suite, **written
  but not executed** (`@playwright/test` is installed as a devDependency so
  it type-checks under `next build`, but browser binaries were never
  fetched).
- `frontend/e2e/fetch-replay.mjs` -- **the method that actually ran**,
  replicating every page's exact fetch calls against the live backend with
  real `assert`-based checks. Run via `node e2e/fetch-replay.mjs` with the
  backend up and `ANTHROPIC_API_KEY` unset; result: 6/6 passed, covering the
  real heatmap grid, a positive-premium `/simulate-policy` response with
  basis_risk in income-smoothing framing, the single-dominant-feature
  `/explain` result, the no-key assistant fallback within a timeout, and the
  honest out-of-coverage path.

## ruff

`ruff check .` is clean repo-wide (previously 83 findings: 80 auto-fixed via
`ruff check --fix`, all mechanical -- unused imports, extraneous f-string
prefixes on strings with no placeholders; 3 fixed manually -- two genuinely
unused local variables in `backend/backtest/report.py`, one ambiguous
single-letter variable name `l` in `tests/unit/test_behavioral.py`). Full
181-test suite re-verified passing after every change in this pass.
