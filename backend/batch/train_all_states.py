"""Resumable, sequential batch runner: trains the full per-state pipeline for
every state in config/wages_by_state.yaml, one state at a time, isolating
failures so an unattended multi-hour run over 79 states self-heals and never
restarts from zero.

DESIGN (reviewed before build):
  * INTERPRETER inheritance -- every stage is launched as
    [sys.executable, "-m", module], so it runs on THIS process's interpreter
    (the canonical .venv the Makefile pins), never a bare python/python3 off
    PATH. Silent interpreter drift is exactly what broke reproducibility earlier
    in this project; the batch is the highest-stakes place for it to recur, so
    the interpreter is pinned explicitly and recorded in the manifest.
  * RESUME -- a state whose REQUIRED artifacts all exist
    (StateContext.is_trained) is skipped. ppo_policy.pt is now a REQUIRED
    artifact, so a state with a missing or smoke-run policy is NOT treated as
    done. --force re-runs regardless.
  * ISOLATION -- one subprocess per STAGE; a per-state try/except-equivalent
    (a nonzero exit, a timeout, or a crash) marks the state failed and, unless
    --fail-fast, the batch moves on to the next state (continue-on-error).
  * TIMEOUT -- each stage gets --stage-timeout seconds (default 1200 = 20 min,
    generous against the normal 1-3 min) so one hung NASA fetch or training loop
    is recorded as a failure instead of silently stalling the whole batch.
  * MANIFEST -- notebooks/artifacts/batch_manifest.json, keyed by state_key,
    rewritten ATOMICALLY (temp file + os.replace) after EVERY state, so a crash
    mid-batch never leaves a half-written manifest and a resumed run sees exactly
    what finished.
  * LOGS -- each state's combined stdout/stderr -> notebooks/artifacts/
    batch_logs/<state_key>.log for unattended post-mortem debugging.
  * SEQUENTIAL -- no cross-state parallelism (simpler logs, no shared-cache
    races, matches how every state has been validated individually so far).

WHY build_wage_loss IS NOT A STAGE: calibration.py is the real state-aware
producer of wage_loss.parquet -- it BUILDS it from the calibrated logit over the
state's own real heat + wages. Nothing reads wage_loss before calibration
overwrites it, so build_wage_loss's literature version would be dead I/O; it is
also not STATE_KEY-aware and would write the legacy path. So the batch runs
`make reproduce` minus that one stage.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

from backend.state_context import all_state_keys, get_context

REPO_ROOT = Path(__file__).resolve().parents[2]
MANIFEST_PATH = REPO_ROOT / "notebooks" / "artifacts" / "batch_manifest.json"
LOG_DIR = REPO_ROOT / "notebooks" / "artifacts" / "batch_logs"

# The per-state pipeline, in dependency order (mirrors `make reproduce` minus
# build_wage_loss -- see module docstring). Each runs with STATE_KEY set.
STAGES = (
    "models.stgcn.train",                      # weather.parquet + stgcn.pt
    "models.behavioral_agent.ppo_from_scratch",  # ppo_policy.pt (uses default kappa/gamma)
    "models.behavioral_agent.calibration",     # calibration.json + wage_loss.parquet
    "models.stgcn.evaluate_spatial",           # spatial_baseline_metrics.json (tevi gates on it)
    "models.fusion.tevi",                       # mu_tevi.parquet + copula.json
    "models.forecast.train",                    # forecaster.pt
    "backend.backtest.report",                  # backtest_report.md + claims.parquet + contract.json
    "models.anomaly.train",                     # anomaly.pkl
)

DEFAULT_STAGE_TIMEOUT = 1200  # seconds (20 min); stages normally run 1-3 min.


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _atomic_write_json(path: Path, obj: dict) -> None:
    """Write JSON via temp-file + os.replace so the manifest is never observed
    half-written, even if the process dies mid-write."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(obj, indent=2) + "\n")
    os.replace(tmp, path)  # atomic within a filesystem


def _load_manifest(path: Path) -> dict:
    if path.exists():
        try:
            m = json.loads(path.read_text())
            m.setdefault("states", {})
            return m
        except (json.JSONDecodeError, OSError):
            pass
    return {"created": _now(), "states": {}}


def run_stage(state_key: str, module: str, timeout: int, env: dict) -> tuple[bool, dict]:
    """Run one pipeline stage as a subprocess on THIS interpreter, appending its
    combined stdout/stderr to the state's log. Returns (ok, info)."""
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    log_path = LOG_DIR / f"{state_key}.log"
    cmd = [sys.executable, "-m", module]
    started = time.time()
    with open(log_path, "a") as log:
        log.write(f"\n{'=' * 78}\n[{_now()}] STAGE {module}  (STATE_KEY={state_key})\n"
                  f"cmd: {' '.join(cmd)}\n{'=' * 78}\n")
        log.flush()
        try:
            proc = subprocess.run(
                cmd, cwd=str(REPO_ROOT), env=env,
                stdout=log, stderr=subprocess.STDOUT,
                timeout=timeout, check=False,
            )
        except subprocess.TimeoutExpired:
            log.write(f"\n[{_now()}] TIMEOUT after {timeout}s -- stage killed.\n")
            return False, {"stage": module, "status": "timeout",
                           "seconds": round(time.time() - started, 1)}
        except Exception as exc:  # noqa: BLE001 -- record any launch failure, never crash the batch
            log.write(f"\n[{_now()}] LAUNCH ERROR: {type(exc).__name__}: {exc}\n")
            return False, {"stage": module, "status": "launch_error", "error": str(exc),
                           "seconds": round(time.time() - started, 1)}
    dt = round(time.time() - started, 1)
    if proc.returncode != 0:
        return False, {"stage": module, "status": "error", "returncode": proc.returncode,
                       "seconds": dt}
    return True, {"stage": module, "status": "ok", "seconds": dt}


def run_state(state_key: str, stages: tuple[str, ...], timeout: int, base_env: dict) -> dict:
    """Run all stages for one state, stopping at the first failure."""
    env = dict(base_env)
    env["STATE_KEY"] = state_key
    env["PYTHONPATH"] = str(REPO_ROOT)
    get_context(state_key).ensure_dirs()
    stage_results = []
    for module in stages:
        ok, info = run_stage(state_key, module, timeout, env)
        stage_results.append(info)
        if not ok:
            return {"status": "failed", "failed_stage": module, "stages": stage_results}
    return {"status": "ok", "stages": stage_results}


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Resumable sequential per-state pipeline batch runner.")
    parser.add_argument("--states", default=None,
                        help="comma-separated state_keys to run (default: all in "
                             "config/wages_by_state.yaml). Use for 2-3 state dry-runs.")
    parser.add_argument("--fail-fast", action="store_true",
                        help="stop the whole batch at the first state that fails a stage "
                             "(default: continue-on-error).")
    parser.add_argument("--stage-timeout", type=int, default=DEFAULT_STAGE_TIMEOUT,
                        help=f"per-stage timeout in seconds (default {DEFAULT_STAGE_TIMEOUT}).")
    parser.add_argument("--force", action="store_true",
                        help="re-run even states that is_trained() reports as already done.")
    args = parser.parse_args()

    all_keys = all_state_keys()
    if args.states:
        targets = [s.strip() for s in args.states.split(",") if s.strip()]
        unknown = [s for s in targets if s not in all_keys]
        if unknown:
            print(f"FATAL: unknown state_key(s): {unknown}\n"
                  f"       valid keys are in config/wages_by_state.yaml "
                  f"({len(all_keys)} total).")
            return 1
    else:
        targets = all_keys

    manifest = _load_manifest(MANIFEST_PATH)
    manifest["run_started"] = _now()
    manifest["interpreter"] = sys.executable  # recorded so drift is auditable
    manifest["stages"] = list(STAGES)
    manifest["stage_timeout_s"] = args.stage_timeout
    manifest["fail_fast"] = args.fail_fast

    base_env = dict(os.environ)
    base_env.pop("STATE_KEY", None)  # start clean; run_state sets it per state

    print("=" * 78)
    print(f"BATCH TRAIN -- {len(targets)} state(s) x {len(STAGES)} stages, sequential")
    print(f"interpreter : {sys.executable}")
    print(f"mode        : {'FAIL-FAST' if args.fail_fast else 'continue-on-error'} | "
          f"stage-timeout {args.stage_timeout}s | force={args.force}")
    print(f"manifest    : {MANIFEST_PATH}")
    print(f"logs        : {LOG_DIR}/<state_key>.log")
    print("=" * 78, flush=True)

    n_ok = n_failed = n_skipped = 0
    for i, sk in enumerate(targets, 1):
        prefix = f"[{i}/{len(targets)}] {sk:30s}"
        try:
            if not args.force and get_context(sk).is_trained():
                print(f"{prefix} SKIP (already trained)", flush=True)
                manifest["states"][sk] = {"status": "skipped", "at": _now()}
                _atomic_write_json(MANIFEST_PATH, manifest)
                n_skipped += 1
                continue
            print(f"{prefix} running {len(STAGES)} stages ...", flush=True)
            t0 = time.time()
            result = run_state(sk, STAGES, args.stage_timeout, base_env)
            result["at"] = _now()
            result["seconds"] = round(time.time() - t0, 1)
        except Exception as exc:  # noqa: BLE001 -- one bad state must never kill the batch
            result = {"status": "failed", "failed_stage": "<driver>", "seconds": 0.0,
                      "error": f"{type(exc).__name__}: {exc}", "at": _now()}
        manifest["states"][sk] = result
        _atomic_write_json(MANIFEST_PATH, manifest)  # persisted AFTER every state

        if result["status"] == "ok":
            n_ok += 1
            print(f"{prefix} OK   ({result['seconds']:.0f}s)", flush=True)
        else:
            n_failed += 1
            fs = result.get("failed_stage", "?")
            print(f"{prefix} FAIL at {fs} ({result['seconds']:.0f}s) "
                  f"-> {LOG_DIR}/{sk}.log", flush=True)
            if args.fail_fast:
                print(f"[FAIL-FAST] stopping: {sk} failed at {fs}.", flush=True)
                break

    manifest["run_ended"] = _now()
    manifest["summary"] = {"ok": n_ok, "failed": n_failed, "skipped": n_skipped,
                           "targeted": len(targets)}
    _atomic_write_json(MANIFEST_PATH, manifest)

    print("=" * 78)
    print(f"BATCH DONE: {n_ok} ok, {n_failed} failed, {n_skipped} skipped "
          f"(of {len(targets)} targeted).")
    print(f"manifest: {MANIFEST_PATH}")
    print("=" * 78)
    return 1 if n_failed else 0


if __name__ == "__main__":
    sys.exit(main())
