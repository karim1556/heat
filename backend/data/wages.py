"""World Bank Indicators v2 loader (keyless, free, uncapped) -- SOLE required
wage-context data source.

HONESTY NOTE: the World Bank indicator used here (SL.EMP.WORK.ZS) gives the
share of wage/salaried workers in total employment -- labor-STRUCTURE context,
not a currency wage LEVEL. The actual baseline daily wage (in INR) used for
pricing comes from a cited public minimum-wage schedule in cities.yaml, never
from this API. occupation_baseline_wages() makes that separation explicit.
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import yaml

from backend.data.recovery import fetch_json_cached, fill_gaps_nearest

WORLD_BANK_HOST = "api.worldbank.org"

CITIES_YAML_PATH = Path(__file__).parent / "cities.yaml"


def _worldbank_url(country_iso3: str, indicator_code: str) -> str:
    return f"https://{WORLD_BANK_HOST}/v2/country/{country_iso3}/indicator/{indicator_code}"


class WageLoader:
    def __init__(self, country_iso3: str = "IND", cache_dir: str | Path = "data/raw"):
        self.country_iso3 = country_iso3
        self.cache_dir = Path(cache_dir)
        self.last_gap_proxies: list[dict] = []

    def fetch_worldbank(self, indicator_codes: list[str], min_year: int = 2005) -> pd.DataFrame:
        """Fetch labor-structure indicators from the World Bank v2 API.

        MUST use /v2/ and &format=json. Body is [metadata, data]; parse [1].
        Recent years are often null (WB lags 1-2yr) -> MODE B fills them from
        the nearest real year within a 5-year reach, else MODE A.

        `min_year` scopes gap-filling to the recent window this pipeline
        actually needs. Many WB indicators (incl. SL.EMP.WORK.ZS, modeled
        since 1991) simply have no estimate at all for earlier decades --
        that is an out-of-scope absence, not a MODE B gap, and must not be
        force-filled or escalated to MODE A.
        """
        rows: list[dict] = []
        for code in indicator_codes:
            url = _worldbank_url(self.country_iso3, code)
            cache_path = self.cache_dir / f"worldbank_{self.country_iso3}_{code}.json"
            data = fetch_json_cached(
                url, cache_path,
                params={"format": "json", "per_page": 20000},
                name=f"World Bank {code}",
            )
            records = data[1] if isinstance(data, list) and len(data) > 1 else []
            for rec in records or []:
                rows.append({
                    "indicator_code": code,
                    "country_iso3": rec.get("countryiso3code", self.country_iso3),
                    "year": int(rec["date"]),
                    "value": rec.get("value"),
                })

        df = pd.DataFrame(rows)
        if df.empty:
            self.last_gap_proxies = []
            return df

        df = df[df["year"] >= min_year].reset_index(drop=True)
        df["value"] = pd.to_numeric(df["value"], errors="coerce")
        df["_time"] = pd.to_datetime(df["year"].astype(str) + "-01-01")

        filled, proxies = fill_gaps_nearest(
            df,
            value_cols=["value"],
            node_key="indicator_code",
            time_key="_time",
            max_temporal_gap=5 * 365,
        )
        self.last_gap_proxies = proxies

        filled = filled.drop(columns=["_time"])
        return filled.sort_values(["indicator_code", "year"]).reset_index(drop=True)

    def occupation_baseline_wages(self, city_key: str | None = None) -> dict[str, float]:
        """Cited baseline daily wages (INR) from cities.yaml -- NOT the API.

        World Bank data is labor-structure context only (see module docstring).
        """
        wages, _ = self._load_city_wages(city_key)
        return wages

    def wage_provenance(self, city_key: str | None = None) -> list[dict]:
        """Citation record (source_name/url/date) for every baseline wage."""
        _, provenance = self._load_city_wages(city_key)
        return provenance

    def _load_city_wages(self, city_key: str | None) -> tuple[dict[str, float], list[dict]]:
        with open(CITIES_YAML_PATH) as f:
            config = yaml.safe_load(f)

        key = city_key or config["default_city"]
        city = config["cities"][key]

        wages: dict[str, float] = {}
        provenance: list[dict] = []
        for occupation, info in city["occupations"].items():
            wage = info["baseline_daily_wage"]
            wages[occupation] = float(wage["value"])
            provenance.append({
                "city": key,
                "occupation": occupation,
                "value": wage["value"],
                "currency": wage.get("currency", "INR"),
                "source_name": wage["source_name"],
                "source_url": wage["source_url"],
                "effective_date": wage["effective_date"],
                "verified": wage.get("verified", False),
                "verification_note": wage.get("verification_note", ""),
            })
        return wages, provenance
