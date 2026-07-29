"""OPTIONAL ILOSTAT SDMX enrichment. NEVER on the required path.

Nothing in the core pipeline (build_wage_loss.py) imports this module. If it
is invoked and fails for any reason (network, parsing, schema drift), it logs
a skip message and exits 0 rather than raising -- this is enrichment, not a
required real-data source, so its absence must never trigger MODE A.
"""

from __future__ import annotations

import sys

ILOSTAT_SDMX_URL = "https://www.ilo.org/sdmx/rest/data/ILO,DF_EAP_TEMP_SEX_AGE_RT,1.0"


def fetch_ilostat_enrichment(country_iso2: str = "IN") -> dict | None:
    """Best-effort ILOSTAT SDMX pull. Returns None on any failure."""
    try:
        import requests

        resp = requests.get(
            ILOSTAT_SDMX_URL,
            params={"startPeriod": "2018", "endPeriod": "2023", "ref_area": country_iso2},
            headers={"Accept": "application/json"},
            timeout=15,
        )
        resp.raise_for_status()
        return resp.json()
    except Exception:
        print("ILOSTAT enrichment skipped (optional)")
        return None


if __name__ == "__main__":
    fetch_ilostat_enrichment()
    sys.exit(0)
