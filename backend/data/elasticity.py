"""Cited heat -> wage-loss elasticity constants.

This is the ONE labeled modeling assumption in the pipeline (per CLAUDE.md).
Every number here carries an explicit literature citation. Vendor and
delivery occupations use the "default" elasticity until a field survey
(SurveyDataLoader, see build_wage_loss.py) provides a measured override.
"""

from __future__ import annotations

ELASTICITY = {
    "default": {
        "per_deg": 0.026,
        "wbgt_threshold_c": 24.0,
        "source": "Foster/Kjellstrom meta-analysis, ~2.6%/C wage-loss above 24C WBGT",
    },
    "construction": {
        "per_deg": 0.0057,
        "wbgt_threshold_c": 24.0,
        "source": "Construction-sector WBGT productivity study, ~0.57%/C above 24C WBGT",
    },
}

MAX_LOSS_FRACTION = 0.9

_OCCUPATION_ELASTICITY_KEY = {
    "vendor": "default",
    "construction": "construction",
    "delivery": "default",
}


def wage_loss_fraction(wbgt_c: float, occupation: str) -> float:
    """Cited, pure function: fraction of daily wage lost to heat exposure.

    0 below the WBGT threshold; per_deg * (wbgt - threshold) above it,
    capped at MAX_LOSS_FRACTION.
    """
    key = _OCCUPATION_ELASTICITY_KEY.get(occupation, "default")
    params = ELASTICITY[key]
    threshold = params["wbgt_threshold_c"]
    if wbgt_c <= threshold:
        return 0.0
    fraction = params["per_deg"] * (wbgt_c - threshold)
    return min(fraction, MAX_LOSS_FRACTION)


def provenance() -> list[dict]:
    """Return the citation record for every elasticity constant in use."""
    records = []
    for key, params in ELASTICITY.items():
        occupations = [
            occ for occ, ekey in _OCCUPATION_ELASTICITY_KEY.items() if ekey == key
        ]
        records.append({
            "elasticity_key": key,
            "occupations": occupations,
            "per_deg": params["per_deg"],
            "wbgt_threshold_c": params["wbgt_threshold_c"],
            "source": params["source"],
        })
    return records
