"""Assemble data/processed/wage_loss.parquet from real NASA POWER + cited
wage/elasticity data (CLAUDE.md Golden Rules 5 and 9).

For every REAL POWER node/day: WBGT (real, computed from T2M+RH2M) ->
wage_loss_fraction (cited elasticity) * cited baseline daily wage -> absolute
loss. Prints a provenance banner covering both real APIs, the cited wage
schedule, the elasticity citation, and the MODE B proxy rate.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import pandas as pd
import yaml

from backend.data import elasticity
from backend.data.survey import SurveyDataLoader
from backend.data.wages import WageLoader, WORLD_BANK_HOST
from backend.data.weather import POWER_HOST, WeatherLoader, default_end_date

CITIES_YAML_PATH = Path(__file__).parent / "cities.yaml"
DEFAULT_OUTPUT_PATH = Path("data/processed/wage_loss.parquet")
WORLDBANK_INDICATOR = "SL.EMP.WORK.ZS"
OCCUPATIONS = ("vendor", "construction", "delivery")


def _effective_elasticity(occupation: str, overrides: dict[str, dict]) -> dict:
    if occupation in overrides:
        return overrides[occupation]
    key = elasticity._OCCUPATION_ELASTICITY_KEY.get(occupation, "default")
    return elasticity.ELASTICITY[key]


def _wage_loss_fraction_series(wbgt: pd.Series, params: dict) -> pd.Series:
    threshold = params["wbgt_threshold_c"]
    per_deg = params["per_deg"]
    frac = (wbgt - threshold) * per_deg
    return frac.clip(lower=0.0, upper=elasticity.MAX_LOSS_FRACTION)


def build(city_key: str | None = None, start: str = "20140101", end: str | None = None,
          output_path: Path = DEFAULT_OUTPUT_PATH) -> pd.DataFrame:
    end = end or default_end_date()
    with open(CITIES_YAML_PATH) as f:
        config = yaml.safe_load(f)
    key = city_key or config["default_city"]
    city = config["cities"][key]

    # 1. Real weather: NASA POWER
    weather_loader = WeatherLoader(bbox=city["bbox"])
    raw_weather = weather_loader.fetch_daily(start=start, end=end)
    filled_weather, weather_proxies = weather_loader.fill_gaps(raw_weather)
    wbgt = weather_loader.to_wbgt_approx(filled_weather)
    filled_weather = filled_weather.assign(wbgt_c=wbgt)

    # 2. Real wage-structure context: World Bank (labor structure only)
    wage_loader = WageLoader(country_iso3=city["country_iso3"])
    wb_df = wage_loader.fetch_worldbank([WORLDBANK_INDICATOR])
    baseline_wages = wage_loader.occupation_baseline_wages(city_key=key)
    wage_provenance = wage_loader.wage_provenance(city_key=key)

    # 3. Cited elasticity, with optional real-survey override (swap seam)
    survey = SurveyDataLoader()
    overrides = survey.load_overrides()

    # 4. Assemble wage-loss rows for every real node/day x occupation
    frames = []
    for occupation in OCCUPATIONS:
        params = _effective_elasticity(occupation, overrides)
        fraction = _wage_loss_fraction_series(filled_weather["wbgt_c"], params)
        baseline_wage = baseline_wages[occupation]
        frames.append(pd.DataFrame({
            "node_id": filled_weather["node_id"],
            "ts": filled_weather["date"],
            "occupation": occupation,
            "wage_loss_fraction": fraction,
            "wage_loss_abs": fraction * baseline_wage,
        }))

    result = pd.concat(frames, ignore_index=True)

    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    result.to_parquet(output_path, index=False)

    # 5. Provenance banner
    weather_total_cells = len(filled_weather) * 2  # T2M, RH2M
    wage_total_cells = len(wb_df) if not wb_df.empty else 0
    total_proxies = len(weather_proxies) + len(wage_loader.last_gap_proxies)
    total_cells = weather_total_cells + wage_total_cells
    proxy_rate = (total_proxies / total_cells * 100) if total_cells else 0.0

    print("=" * 72)
    print("PROVENANCE BANNER -- data/processed/wage_loss.parquet")
    print("=" * 72)
    print(f"[REAL API] Weather: NASA POWER regional API ({POWER_HOST})")
    print(f"           nodes={filled_weather['node_id'].nunique()} "
          f"days={filled_weather['date'].nunique()} bbox={city['bbox']}")
    print(f"[REAL API] Wages (labor structure only): World Bank Indicators v2 "
          f"({WORLD_BANK_HOST}), indicator={WORLDBANK_INDICATOR}")
    print("[CITED]    Baseline daily wages:")
    for rec in wage_provenance:
        verified_tag = "verified:true" if rec["verified"] else "verified:false [UNCONFIRMED]"
        print(f"           {rec['occupation']}: {rec['currency']} {rec['value']} "
              f"-- {rec['source_name'].strip()} ({rec['source_url']}, {rec['effective_date']}) "
              f"[{verified_tag}]")
    print("[CITED]    Elasticity:")
    for rec in elasticity.provenance():
        for occ in rec["occupations"]:
            eff = _effective_elasticity(occ, overrides)
            tag = "primary field data" if occ in overrides else eff["source"]
            print(f"           {occ}: {eff['per_deg']}/degC above {eff['wbgt_threshold_c']}C WBGT -- {tag}")
    print(f"[MODE B]   Gap-filled cells: {total_proxies}/{total_cells} "
          f"({proxy_rate:.3f}% proxy rate)")
    print("=" * 72)

    return result


def main():
    parser = argparse.ArgumentParser(description="Build wage_loss.parquet from real data")
    parser.add_argument("--city", default=None)
    parser.add_argument("--start", default="20140101")
    parser.add_argument("--end", default=None, help="YYYYMMDD; defaults to today minus NASA POWER's real processing lag")
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT_PATH))
    args = parser.parse_args()

    build(city_key=args.city, start=args.start, end=args.end, output_path=Path(args.output))


if __name__ == "__main__":
    sys.exit(main() or 0)
