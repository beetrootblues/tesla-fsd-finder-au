"""
Fair-price scoring (V2 roadmap).

price_history.json was already being collected per-listing in v1.2 but
never aggregated across listings -- the only existing signal was "did
this specific listing's price drop." This adds the other half: how does
this listing's price compare to others with similar specs already in the
dataset right now.

Deliberately conservative: requires a minimum comparable-group size
before saying anything, and reports the sample size alongside the
verdict so a thin comparison isn't presented with false confidence --
same principle as everything in classify.py.
"""

from __future__ import annotations

import statistics
from dataclasses import dataclass, field
from typing import Optional

MIN_COMPARABLE_GROUP = 3


@dataclass
class PriceComparison:
    verdict: str  # "below_market" | "at_market" | "above_market" | "insufficient_data"
    comparable_count: int
    median_comparable_price: Optional[int] = None
    percent_vs_median: Optional[float] = None
    group_description: str = ""
    caveat: str = (
        "Compares model, Autopilot-hardware tier, and build-year only -- not "
        "odometer, trim, or condition. A big gap can mean a genuine deal, or "
        "just very different kilometres or spec. Check those before assuming "
        "either."
    )


def _hw_tier(hw_version: Optional[str]) -> str:
    """Coarser than the full HW classification -- groups AP1/AP2/AP2.5 together
    as 'pre-HW3', since price-relevant capability splits mainly at HW3/HW4/unknown,
    and the comparable-group needs to be wide enough to have any members at all."""
    if hw_version in ("HW4",):
        return "HW4"
    if hw_version in ("HW3",):
        return "HW3"
    if hw_version in ("HW1", "HW2", "HW2.5"):
        return "pre-HW3"
    return "unspecified"


def _year_bucket(year: Optional[int]) -> str:
    if year is None:
        return "unknown-year"
    # 2-year buckets -- fine enough to matter for price, coarse enough that
    # a bucket actually has more than one listing in it
    start = (year // 2) * 2
    return f"{start}-{start + 1}"


def _group_key(listing: dict) -> tuple:
    return (listing.get("model"), _hw_tier(listing.get("hw_version")), _year_bucket(listing.get("year")))


def compare_price(listing: dict, all_listings: list[dict]) -> PriceComparison:
    """Compares one listing's price against others sharing model + HW tier +
    2-year build bucket. Excludes the listing itself from its own comparison
    group."""
    price = listing.get("price")
    if not price:
        return PriceComparison(verdict="insufficient_data", comparable_count=0)

    key = _group_key(listing)
    comparables = [
        other.get("price")
        for other in all_listings
        if other is not listing and other.get("id") != listing.get("id") and _group_key(other) == key and other.get("price")
    ]

    if len(comparables) < MIN_COMPARABLE_GROUP:
        return PriceComparison(
            verdict="insufficient_data",
            comparable_count=len(comparables),
            group_description=f"{key[0] or 'Tesla'}, {key[1]}, {key[2]}",
        )

    median = statistics.median(comparables)
    pct = ((price - median) / median) * 100

    if pct <= -8:
        verdict = "below_market"
    elif pct >= 8:
        verdict = "above_market"
    else:
        verdict = "at_market"

    return PriceComparison(
        verdict=verdict,
        comparable_count=len(comparables),
        median_comparable_price=int(median),
        percent_vs_median=round(pct, 1),
        group_description=f"{key[0] or 'Tesla'}, {key[1]}, {key[2]}",
    )


def annotate_all(listings: list[dict]) -> None:
    """Mutates each listing in place, adding a 'price_comparison' dict.
    Call after the full listing set is loaded/refreshed, not per-listing,
    since every comparison needs the full set to compare against."""
    for listing in listings:
        cmp = compare_price(listing, listings)
        listing["price_comparison"] = {
            "verdict": cmp.verdict,
            "comparable_count": cmp.comparable_count,
            "median_comparable_price": cmp.median_comparable_price,
            "percent_vs_median": cmp.percent_vs_median,
            "group_description": cmp.group_description,
            "caveat": cmp.caveat,
        }
