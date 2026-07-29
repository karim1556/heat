"""Print exactly what a human needs to check to confirm cited baseline wages.

This tool does NOT fetch or fabricate a replacement wage figure -- it only
surfaces the citation (value, source_url, effective_date) and the current
verified:true/false state from cities.yaml, so a human can go confirm it
against the live government notification and flip verified: true themselves.
The agent must never set verified:true itself; it cannot confirm a live
government figure.

Optionally prints a World Bank labor-structure indicator alongside, purely as
plausibility CONTEXT -- never as a stand-in for the wage level itself. That
lookup is best-effort: if the API is unreachable, this script still exits 0
(this is a human-facing checklist, not a required-data fetch).
"""

from __future__ import annotations

import sys
from pathlib import Path

import yaml

CITIES_YAML_PATH = Path(__file__).parent / "cities.yaml"


def _fetch_worldbank_context(country_iso3: str) -> str | None:
    """Best-effort WB context fetch. Never raises; returns None on failure."""
    try:
        from backend.data.wages import WageLoader

        indicator = "SL.EMP.WORK.ZS"
        loader = WageLoader(country_iso3=country_iso3)
        df = loader.fetch_worldbank([indicator])
        if df.empty:
            return None
        latest = df.sort_values("year").iloc[-1]
        return (
            f"World Bank {indicator} (labor structure, NOT the wage level) "
            f"latest: {latest['value']:.2f} in {int(latest['year'])} "
            f"-- context only, do not use as the wage"
        )
    except SystemExit:
        return None
    except Exception:
        return None


def main() -> int:
    with open(CITIES_YAML_PATH) as f:
        config = yaml.safe_load(f)

    print("=" * 72)
    print("WAGE VERIFICATION CHECKLIST -- human action required")
    print("=" * 72)

    for city_key, city in config["cities"].items():
        print(f"\nCity: {city['name']} ({city_key})")

        wb_context = _fetch_worldbank_context(city["country_iso3"])
        if wb_context:
            print(f"  [context] {wb_context}")
        else:
            print("  [context] World Bank cross-check unavailable (optional; skipped)")

        for occupation, info in city["occupations"].items():
            wage = info["baseline_daily_wage"]
            verified = wage.get("verified", False)
            status = "verified:true" if verified else "verified:false [ACTION NEEDED]"
            print(f"  {occupation}: {wage['currency']} {wage['value']} "
                  f"({status})")
            print(f"    source: {wage['source_name'].strip()}")
            print(f"    url:    {wage['source_url']}")
            print(f"    as of:  {wage['effective_date']}")
            if not verified:
                print(f"    -> HUMAN ACTION: open the source_url above, confirm the "
                      f"{occupation} rate for {city['name']}, then set "
                      f"verified: true in cities.yaml. The agent cannot do this step.")

    print("\n" + "=" * 72)
    return 0


if __name__ == "__main__":
    sys.exit(main())
