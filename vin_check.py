"""
VIN cross-check (V2 roadmap) -- an independent signal against classify.py's
text-based inference, for listings that expose a VIN (mainly dealer
listings; private sellers rarely include one in the ad itself).

Uses NHTSA's public vPIC API (vpic.nhtsa.dot.gov), a free, stable, no-key-
required US government service. It decodes model year and manufacturer
from VIN structure -- it does NOT know Tesla-specific Autopilot hardware
generation (that's not part of the standard VIN decode for any
manufacturer), so this cross-checks the *model year* classify.py already
extracts from ad text, it doesn't replace the HW/MCU/FSD logic.

Honesty note: this sandbox's network egress is restricted to a package-
registry allowlist and does not include vpic.nhtsa.dot.gov, so this has
been verified against NHTSA's documented request/response contract, not
tested end-to-end from here. Confirm it actually round-trips correctly
once deployed somewhere with normal internet access (Railway has this).
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Optional

import httpx

VPIC_DECODE_URL = "https://vpic.nhtsa.dot.gov/api/vehicles/DecodeVinValues/{vin}?format=json"

_VIN_PATTERN = re.compile(r"\b([A-HJ-NPR-Z0-9]{17})\b")


def extract_vin(text: str) -> Optional[str]:
    """Finds a plausible 17-character VIN in free text. Excludes I, O, Q,
    which are never used in real VINs to avoid confusion with 1/0 -- a
    match containing them is something else, not a VIN."""
    m = _VIN_PATTERN.search(text.upper())
    return m.group(1) if m else None


@dataclass
class VinCheckResult:
    vin: str
    decoded_year: Optional[int]
    decoded_make: Optional[str]
    decoded_model: Optional[str]
    matches_ad_year: Optional[bool]  # None if the ad didn't state a year to compare against
    note: str


async def cross_check_vin(vin: str, ad_stated_year: Optional[int]) -> Optional[VinCheckResult]:
    """Returns None on any failure (network, bad VIN, non-Tesla result) rather
    than raising -- this is a best-effort enrichment, not a required step,
    and a decode failure shouldn't take down classification for the rest of
    the listing."""
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.get(VPIC_DECODE_URL.format(vin=vin))
        if resp.status_code != 200:
            return None
        results = resp.json().get("Results", [])
        fields = {r.get("Variable"): r.get("Value") for r in results if r.get("Value")}

        make = fields.get("Make")
        if make and make.strip().lower() != "tesla":
            return VinCheckResult(
                vin=vin, decoded_year=None, decoded_make=make, decoded_model=fields.get("Model"),
                matches_ad_year=None,
                note=f"VIN decodes to make '{make}', not Tesla -- likely a mistyped VIN or wrong listing.",
            )

        year_str = fields.get("Model Year")
        decoded_year = int(year_str) if year_str and year_str.isdigit() else None

        matches = None
        note = "VIN decoded; no ad-stated year available to cross-check against."
        if decoded_year and ad_stated_year:
            matches = decoded_year == ad_stated_year
            note = (
                f"VIN decodes to model year {decoded_year}, matching the ad's stated {ad_stated_year}."
                if matches else
                f"VIN decodes to model year {decoded_year}, which doesn't match the ad's stated {ad_stated_year} -- worth asking the seller about."
            )

        return VinCheckResult(
            vin=vin, decoded_year=decoded_year, decoded_make=make, decoded_model=fields.get("Model"),
            matches_ad_year=matches, note=note,
        )
    except Exception:
        return None
