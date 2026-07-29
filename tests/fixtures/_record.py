"""One-time fixture recorder: makes ONE small real call each to NASA POWER
and World Bank, trims the responses, and saves them for OFFLINE unit tests.

Run manually, with network access, whenever fixtures need refreshing:
    PYTHONPATH=. python tests/fixtures/_record.py

Committed outputs:
    tests/fixtures/nasa_power_sample.json
    tests/fixtures/nasa_power_gap_sample.json  (one cell forced to -999)
    tests/fixtures/worldbank_sample.json
"""

from __future__ import annotations

import json
from pathlib import Path

import requests

FIXTURES_DIR = Path(__file__).parent

NASA_POWER_URL = "https://power.larc.nasa.gov/api/temporal/daily/regional"
WORLD_BANK_URL = "https://api.worldbank.org/v2/country/IND/indicator/SL.EMP.WORK.ZS"


def record_nasa_power():
    params = {
        "parameters": "T2M",
        "community": "AG",
        "longitude-min": 71.5,
        "longitude-max": 73.5,
        "latitude-min": 22.0,
        "latitude-max": 24.0,
        "start": "20230101",
        "end": "20230107",
        "format": "json",
    }
    resp = requests.get(NASA_POWER_URL, params=params, timeout=30)
    resp.raise_for_status()
    data = resp.json()

    # Trim to first 3 nodes to keep the fixture small.
    data["features"] = data["features"][:3]

    with open(FIXTURES_DIR / "nasa_power_sample.json", "w") as f:
        json.dump(data, f, indent=2)

    # Holed variant: force one real cell to the -999 MODE-B sentinel.
    gap_data = json.loads(json.dumps(data))  # deep copy
    first_feature = gap_data["features"][0]
    t2m = first_feature["properties"]["parameter"]["T2M"]
    first_date = sorted(t2m.keys())[0]  # first day: only a +1-day neighbor exists, unambiguous
    t2m[first_date] = -999

    with open(FIXTURES_DIR / "nasa_power_gap_sample.json", "w") as f:
        json.dump(gap_data, f, indent=2)

    print(f"Saved nasa_power_sample.json ({len(data['features'])} nodes) "
          f"and nasa_power_gap_sample.json (gap at {first_date})")


def record_worldbank():
    resp = requests.get(WORLD_BANK_URL, params={"format": "json", "per_page": 20000}, timeout=30)
    resp.raise_for_status()
    data = resp.json()

    meta, records = data[0], data[1]
    trimmed = [meta, records[:10]]

    with open(FIXTURES_DIR / "worldbank_sample.json", "w") as f:
        json.dump(trimmed, f, indent=2)

    print(f"Saved worldbank_sample.json ({len(trimmed[1])} records)")


if __name__ == "__main__":
    record_nasa_power()
    record_worldbank()
