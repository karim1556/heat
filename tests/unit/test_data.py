"""Offline unit tests for the data pipeline (backend/data/*).

Uses ONLY committed fixtures (tests/fixtures/*.json) -- no network calls.
Covers NOAA heat-index correctness, cited elasticity behavior, real-API
response parsing, and both CLAUDE.md Golden Rule 5 failure modes:
  MODE A (unreachable source -> fatal_abort -> nonzero exit, no output file)
  MODE B (null/-999 cell -> nearest-real-observation fill, never fabricated)
"""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import pytest

from backend.data import elasticity, recovery, wages, weather

FIXTURES_DIR = Path(__file__).parent.parent / "fixtures"


def _load_fixture(name: str) -> dict:
    with open(FIXTURES_DIR / name) as f:
        return json.load(f)


# ---------------------------------------------------------------------------
# to_heat_index matches NOAA (Rothfusz regression) on 3 known pairs
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("temp_f,rh,expected_hi", [
    (80.0, 40.0, 79.58),
    (90.0, 50.0, 94.47),
    (100.0, 55.0, 123.44),
])
def test_to_heat_index_matches_noaa(temp_f, rh, expected_hi):
    temp_c = (temp_f - 32.0) * 5.0 / 9.0
    df = pd.DataFrame({"T2M": [temp_c], "RH2M": [rh]})
    result = weather.WeatherLoader.to_heat_index(df)
    assert result.iloc[0] == pytest.approx(expected_hi, abs=0.01)


# ---------------------------------------------------------------------------
# wage_loss_fraction: 0 below threshold, monotonic increasing above
# ---------------------------------------------------------------------------

def test_wage_loss_fraction_zero_below_threshold():
    assert elasticity.wage_loss_fraction(20.0, "vendor") == 0.0
    assert elasticity.wage_loss_fraction(24.0, "vendor") == 0.0


def test_wage_loss_fraction_monotonic_increasing_above_threshold():
    values = [elasticity.wage_loss_fraction(wbgt, "vendor") for wbgt in range(25, 35)]
    assert all(b > a for a, b in zip(values, values[1:]))
    assert all(v > 0 for v in values)


def test_wage_loss_fraction_capped():
    assert elasticity.wage_loss_fraction(200.0, "vendor") == elasticity.MAX_LOSS_FRACTION


# ---------------------------------------------------------------------------
# World Bank parser extracts a value from the sample fixture
# ---------------------------------------------------------------------------

def test_worldbank_parser_extracts_value(monkeypatch, tmp_path):
    fixture = _load_fixture("worldbank_sample.json")

    def fake_fetch_json_cached(url, cache_path, **kwargs):
        return fixture

    monkeypatch.setattr(wages, "fetch_json_cached", fake_fetch_json_cached)

    loader = wages.WageLoader(country_iso3="IND", cache_dir=tmp_path)
    df = loader.fetch_worldbank(["SL.EMP.WORK.ZS"])

    assert not df.empty
    assert "value" in df.columns
    assert df["value"].notna().any()
    assert (df["indicator_code"] == "SL.EMP.WORK.ZS").all()


# ---------------------------------------------------------------------------
# NASA POWER parser reshapes the sample into node/day
# ---------------------------------------------------------------------------

def test_nasa_power_parser_reshapes_to_node_day():
    fixture = _load_fixture("nasa_power_sample.json")
    rows = weather.parse_regional_response(fixture, "T2M")

    n_nodes = len(fixture["features"])
    n_days = len(fixture["features"][0]["properties"]["parameter"]["T2M"])
    assert len(rows) == n_nodes * n_days

    df = pd.DataFrame(rows)
    assert set(df.columns) == {"node_id", "lat", "lon", "date", "T2M"}
    assert df["node_id"].nunique() == n_nodes


# ---------------------------------------------------------------------------
# MODE A: unreachable source -> fatal_abort -> SystemExit nonzero + FATAL
# string, and no output (cache) file written.
# ---------------------------------------------------------------------------

def test_mode_a_fatal_abort_on_unreachable_source(monkeypatch, tmp_path, capsys):
    import requests

    def raise_connection_error(*args, **kwargs):
        raise requests.exceptions.ConnectionError("simulated network failure")

    monkeypatch.setattr(recovery.requests, "get", raise_connection_error)
    monkeypatch.setattr(recovery.time, "sleep", lambda _: None)

    cache_path = tmp_path / "should_not_exist.json"

    with pytest.raises(SystemExit) as exc_info:
        recovery.fetch_json_cached(
            "https://power.larc.nasa.gov/api/temporal/daily/regional",
            cache_path,
            name="NASA POWER (test)",
        )

    assert exc_info.value.code != 0
    captured = capsys.readouterr()
    assert "FATAL" in captured.out
    assert "No fabricated or synthetic data is permitted" in captured.out
    assert not cache_path.exists()
    assert not (tmp_path / "should_not_exist.meta.json").exists()


# ---------------------------------------------------------------------------
# MODE B: known hole filled with the EXACT nearest-neighbor value (same node,
# +1 day), never mean/random/interpolated; proxy record has correct distance.
# ---------------------------------------------------------------------------

def test_mode_b_fills_gap_with_exact_nearest_neighbor():
    gap_fixture = _load_fixture("nasa_power_gap_sample.json")
    rows = weather.parse_regional_response(gap_fixture, "T2M")
    df = pd.DataFrame(rows)

    gap_node = df.iloc[0]["node_id"]
    gap_row = df[(df["node_id"] == gap_node) & (df["T2M"] == -999)].iloc[0]
    gap_date = gap_row["date"]

    # The real (non-gap) value observed 1 day later for the same node.
    next_day = pd.to_datetime(gap_date, format="%Y%m%d") + pd.Timedelta(days=1)
    expected_value = df[
        (df["node_id"] == gap_node)
        & (pd.to_datetime(df["date"], format="%Y%m%d") == next_day)
    ]["T2M"].iloc[0]
    assert expected_value != -999  # sanity: the neighbor is a real observation

    filled, proxies = recovery.fill_gaps_nearest(
        df, value_cols=["T2M"], node_key="node_id", time_key="date",
        max_temporal_gap=7,
    )

    filled_value = filled[
        (filled["node_id"] == gap_node)
        & (filled["date"] == pd.to_datetime(gap_date, format="%Y%m%d"))
    ]["T2M"].iloc[0]

    assert filled_value == expected_value  # exact nearest-neighbor value

    matching_proxies = [p for p in proxies if p["target_node"] == gap_node]
    assert len(matching_proxies) == 1
    proxy = matching_proxies[0]
    assert proxy["method"] == "same_node_nearest_time"
    assert proxy["distance_days"] == 1
    assert proxy["source_node"] == gap_node


# ---------------------------------------------------------------------------
# MODE B escalation: a hole with no real neighbor in range -> fatal_abort
# ---------------------------------------------------------------------------

def test_mode_b_escalates_to_fatal_abort_when_unfillable(capsys):
    df = pd.DataFrame({
        "node_id": ["only_node"],
        "date": ["20230101"],
        "T2M": [-999],
    })

    with pytest.raises(SystemExit) as exc_info:
        recovery.fill_gaps_nearest(
            df, value_cols=["T2M"], node_key="node_id", time_key="date",
            max_temporal_gap=7,
        )

    assert exc_info.value.code != 0
    captured = capsys.readouterr()
    assert "FATAL" in captured.out
