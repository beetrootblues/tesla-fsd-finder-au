"""
Tesla FSD Finder Australia - Classification Engine
===================================================
Replaces the old `_detect_fsd` / `_infer_hw_version` in scrapers.py.

This never reads a VIN or the car's own settings screen -- it only reads
whatever text a seller typed into a classifieds ad. That means every field
is a (value, confidence, evidence) triple, never a bare fact. "confirmed"
still just means "the seller said so in text", not a VIN decode. The API/
frontend should always be able to show the evidence, not just the value.

Facts encoded here (verified July 2026 -- re-check before this drifts):
  - AP1 (Mobileye): Sep 2014 - Oct 2016, Model S/X only.
  - AP2 (Nvidia Drive PX2): Oct 2016 - Aug 2017.
  - AP2.5: Aug 2017 - Mar 2019 (early Model 3 shipped on this).
  - HW3 ("FSD Computer"): Mar 2019 - ~Dec 2022.
  - HW4 / "AI4": shipping from Jan 2023, mixed with HW3 through most of
    2023. Visual tell: red-tinted camera lenses (2 red + 1 black dummy
    front) vs HW3's uniform black lenses. Not retrofittable from HW3.
  - HW5 / "AI5": NOT in any consumer vehicle as of July 2026 (delayed to
    mid/late 2027) -- a listing claiming it is a red flag, not a fact.
  - MCU1 (Nvidia Tegra 3): pre-March 2018 build. No Netflix/YouTube/
    Theater/Arcade. Retrofittable to MCU2 for ~$1,500-2,000.
  - MCU2 (Intel Atom E8000): April 2018+ build (March is a genuine
    toss-up). Model 3/Y have shipped MCU2-class hardware since launch --
    MCU1 vs 2 is only a Model S/X question.
  - Model S and Model X were never sold new in Australia after ~2020 and
    RHD production was cancelled outright in 2023 -- every AU-market S/X
    is a 2014-2020 build. That hard-caps them: no HW4/AI4, no refresh-era
    MCU, ever, on a genuinely AU-delivered car.
  - FSD (Supervised) in AU: launched Sept 2025, Model 3/Y with HW4 only
    (HW3 support still pending as of early 2026). Outright purchase
    ($10,100) ended 31 Mar 2026 -- now subscription-only ($149/mo).
    Outright-purchased FSD is VIN-locked and transfers on private sale;
    an active subscription does not.
  - Free Unlimited Supercharging: only genuinely transferable on cars
    delivered before ~2017 (a handful of early-2017 cars included). Later
    promotions are tied to the original owner's account, not the VIN.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date
from typing import Optional

Confidence = str  # "confirmed" | "likely" | "possible" | "unknown"


@dataclass
class Field:
    value: str
    confidence: Confidence = "unknown"
    evidence: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {"value": self.value, "confidence": self.confidence, "evidence": self.evidence}


@dataclass
class Classification:
    model: Field
    autopilot_hw: Field
    mcu: Field
    fsd: Field
    supercharging: Field
    warnings: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "model": self.model.to_dict(),
            "autopilot_hw": self.autopilot_hw.to_dict(),
            "mcu": self.mcu.to_dict(),
            "fsd": self.fsd.to_dict(),
            "supercharging": self.supercharging.to_dict(),
            "warnings": self.warnings,
        }


_MONTHS = ["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"]
_NAMED_DATE = re.compile(
    r"\b(jan(?:uary)?|feb(?:ruary)?|mar(?:ch)?|apr(?:il)?|may|jun(?:e)?|jul(?:y)?|aug(?:ust)?|"
    r"sep(?:t(?:ember)?)?|oct(?:ober)?|nov(?:ember)?|dec(?:ember)?)[a-z]*\s+(20[12]\d)\b",
    re.IGNORECASE,
)
_NUMERIC_DATE = re.compile(r"\b(0?[1-9]|1[0-2])[/\-.](20[12]\d)\b")


def _extract_build_date(text: str) -> Optional[date]:
    """Very forgiving date extraction: '03/2018', 'March 2018', 'compliance 04/19'."""
    m = _NAMED_DATE.search(text)
    if m:
        month_str = m.group(1).lower()
        idx = next((i for i, mo in enumerate(_MONTHS) if month_str.startswith(mo)), None)
        if idx is not None:
            return date(int(m.group(2)), idx + 1, 1)
    m = _NUMERIC_DATE.search(text)
    if m:
        return date(int(m.group(2)), int(m.group(1)), 1)
    return None


def _is_negated(text: str, match_start: int, match_end: int) -> bool:
    """
    Guards against scoring a disclaimed feature as present. Covers both
    word orders sellers use: negator-before-feature ("no FSD", "doesn't
    have full self driving" -- allowing a couple of filler words in
    between) and feature-before-negator ("FSD not included").
    """
    before = text[max(0, match_start - 35):match_start]
    after = text[match_end:match_end + 20]
    before_negated = re.search(
        r"\b(no|not|without|isn'?t|doesn'?t|does\s+not|didn'?t|lacks?|excludes?|n/a)\b(\s+\w+){0,2}\s*[:\-]?\s*$",
        before,
        re.IGNORECASE,
    )
    after_negated = re.match(r"^\s*(is\s+|was\s+)?not\b", after, re.IGNORECASE)
    return bool(before_negated or after_negated)


def classify_model(text: str) -> Field:
    t = text.lower()
    if re.search(r"\bmodel\s*s\b", t):
        return Field("S", "confirmed", ["title/text mentions 'Model S'"])
    if re.search(r"\bmodel\s*x\b", t):
        return Field("X", "confirmed", ["title/text mentions 'Model X'"])
    if re.search(r"\bmodel\s*y\b", t):
        return Field("Y", "confirmed", ["title/text mentions 'Model Y'"])
    if re.search(r"\bmodel\s*3\b", t):
        return Field("3", "confirmed", ["title/text mentions 'Model 3'"])
    return Field("unknown")


_HW_EXPLICIT: list[tuple[re.Pattern, str]] = [
    (re.compile(r"\bhw\s*-?\s*4\b|hardware\s*4(\.0)?\b|\bai\s*-?\s*4\b", re.I), "HW4"),
    (re.compile(r"\bhw\s*-?\s*3\b|hardware\s*3(\.0)?\b|fsd\s*computer", re.I), "HW3"),
    (re.compile(r"\bhw\s*-?\s*2\.5\b|hardware\s*2\.5", re.I), "AP2.5"),
    (re.compile(r"\bhw\s*-?\s*2\b|hardware\s*2(\.0)?\b", re.I), "AP2"),
    (re.compile(r"\bap\s*-?\s*1\b|\bhw\s*-?\s*1\b|hardware\s*1\b|mobileye", re.I), "AP1"),
]

_HW_DATE_WINDOWS: list[tuple[date, date, str]] = [
    (date(2014, 9, 1), date(2016, 10, 1), "AP1"),
    (date(2016, 10, 1), date(2017, 8, 1), "AP2"),
    (date(2017, 8, 1), date(2019, 3, 1), "AP2.5"),
    (date(2019, 3, 1), date(2023, 1, 1), "HW3"),
    (date(2023, 1, 1), date(2030, 1, 1), "HW4"),
]


def classify_autopilot_hw(text: str, model: str) -> Field:
    t = text.lower()

    for pattern, hw in _HW_EXPLICIT:
        m = pattern.search(t)
        if m:
            evidence = [f"text explicitly mentions {hw}"]
            if hw == "HW4" and model in ("S", "X"):
                return Field(
                    "HW4",
                    "possible",
                    evidence + ["flagged: no Australian-delivered Model S/X ever shipped with HW4 -- "
                                "verify this isn't a template/copy error or a private US import"],
                )
            return Field(hw, "confirmed", evidence)

    if re.search(r"\bred\s*(camera|lens)", t):
        return Field("HW4", "likely", ["mentions red-tinted camera lenses, a HW4/AI4 visual tell"])

    if "enhanced autopilot" in t:
        return Field(
            "unknown",
            "possible",
            ["mentions 'Enhanced Autopilot' -- confirms at least HW2, but EAP was sold across "
             "HW2/2.5/HW3 so it doesn't pin an exact generation"],
        )

    build_date = _extract_build_date(text)
    if build_date:
        for start, end, hw in _HW_DATE_WINDOWS:
            if start <= build_date < end:
                if hw == "HW4" and model in ("S", "X"):
                    return Field(
                        "unknown",
                        "unknown",
                        [f"build date {build_date.year}-{build_date.month:02d} would imply HW4, "
                         "but no AU-delivered S/X was built that late -- treat as unverifiable"],
                    )
                mid_transition = hw == "HW4" and build_date.year == 2023
                ev = [f"inferred from build/compliance date {build_date.year}-{build_date.month:02d}"]
                if mid_transition:
                    ev.append("2023 builds shipped as a mix of HW3 and HW4 -- date alone isn't conclusive")
                return Field(hw, "possible" if mid_transition else "likely", ev)

    return Field("unknown")


def classify_mcu(text: str, model: str) -> Field:
    if model in ("3", "Y"):
        return Field("MCU2", "confirmed", ["Model 3/Y have shipped MCU2-class hardware since launch"])

    t = text.lower()

    if re.search(r"\bmcu\s*-?\s*3\b", t) or re.search(r"plaid interior|yoke steering", t):
        return Field(
            "MCU3",
            "possible",
            ["mentions MCU3/refresh-era interior -- no refreshed Model S/X was ever sold new in "
             "Australia, so verify this isn't describing a private import"],
        )
    if re.search(r"\bmcu\s*-?\s*2\b", t):
        return Field("MCU2", "confirmed", ["text explicitly mentions MCU2"])
    if re.search(r"\bmcu\s*-?\s*1\b", t):
        return Field("MCU1", "confirmed", ["text explicitly mentions MCU1"])
    if re.search(r"infotainment upgrade|mcu2 upgrade|mcu retrofit", t):
        return Field("MCU2", "likely", ["mentions an MCU2 infotainment retrofit -- supersedes original build-date MCU1"])

    if re.search(r"netflix|youtube|tesla theater|tesla arcade|streaming apps", t):
        return Field("MCU2", "likely", ["mentions Netflix/YouTube/Theater/Arcade, which require MCU2"])
    if re.search(r"tegra|nvidia infotainment", t):
        return Field("MCU1", "likely", ["mentions Tegra/Nvidia infotainment chip, which is MCU1"])

    build_date = _extract_build_date(text)
    if build_date:
        cutoff = date(2018, 3, 1)
        if build_date.year == 2018 and build_date.month == 3:
            return Field("unknown", "possible", ["build date is March 2018 -- the exact MCU1/MCU2 cutover month, genuinely ambiguous from date alone"])
        value = "MCU1" if build_date < cutoff else "MCU2"
        return Field(value, "possible", ["inferred from build date vs the March 2018 MCU1->MCU2 cutover (retrofits can override this)"])

    return Field("unknown")


def classify_fsd(text: str, autopilot_hw: str) -> Field:
    t = text.lower()
    m = re.search(r"full[\s-]?self[\s-]?driving|\bfsd\b", t)
    if not m or _is_negated(t, m.start(), m.end()):
        return Field("none")

    sub_hit = re.search(r"fsd subscription|subscribed to fsd|fsd sub\b|\$149\s*/?\s*(p\.?m\.?|month|mo\b)", t)
    outright_hit = re.search(
        r"fsd purchased|paid[\s-]?in[\s-]?full fsd|lifetime fsd|fsd outright|"
        r"purchased full self[\s-]?driving|fsd capability purchased",
        t,
    )

    if outright_hit and not sub_hit:
        evidence = ["ad describes FSD as purchased/paid outright -- this is VIN-locked and should transfer on private sale"]
        if autopilot_hw not in ("HW4", "unknown"):
            evidence.append("older hardware can still have the paid FSD Capability option even though "
                             "AU's FSD (Supervised) feature itself currently requires HW4")
        return Field("purchased_outright", "likely", evidence)

    if sub_hit:
        return Field(
            "subscription_active",
            "likely",
            ["ad references an active FSD subscription -- this is tied to the seller's Tesla account and will NOT transfer to a buyer"],
        )

    return Field(
        "mentioned_unclear",
        "possible",
        ["mentions FSD without saying whether it's a one-off purchase (transfers) or a live subscription "
         "(doesn't) -- ask the seller directly and ask for the original invoice"],
    )


def classify_supercharging(text: str) -> Field:
    t = text.lower()
    m = re.search(r"unlimited supercharging|free supercharging|lifetime supercharging", t)
    if not m or _is_negated(t, m.start(), m.end()):
        return Field("none")

    evidence = [
        "ad claims free/unlimited Supercharging -- genuinely transferable Unlimited Supercharging is "
        "reliably only on cars delivered before ~2017; later promotions are usually tied to the "
        "original owner's account, not the car"
    ]
    build_date = _extract_build_date(text)
    if build_date and build_date < date(2017, 7, 1):
        evidence.append(f"build date {build_date.year} falls in the pre-2017 window where this typically is transferable")
        return Field("unlimited_transferable_claimed", "likely", evidence)
    evidence.append("verify in the Tesla app's Charging screen before paying any premium for this")
    return Field("unlimited_transferable_claimed", "possible", evidence)


def classify(title: str, body_text: str) -> Classification:
    text = f"{title}\n{body_text}"
    model = classify_model(text)
    autopilot_hw = classify_autopilot_hw(text, model.value)
    mcu = classify_mcu(text, model.value)
    fsd = classify_fsd(text, autopilot_hw.value)
    supercharging = classify_supercharging(text)

    warnings: list[str] = []
    if model.value in ("S", "X") and autopilot_hw.value == "HW4":
        warnings.append("HW4 claimed on a Model S/X -- no Australian-delivered example should have this; double-check before relying on it")
    if fsd.value == "purchased_outright" and autopilot_hw.value not in ("HW4", "unknown"):
        warnings.append("FSD purchase claimed on pre-HW4 hardware -- the paid option can predate AU's FSD "
                         "(Supervised) feature rollout, so this isn't necessarily wrong, just worth confirming what exactly was purchased")

    return Classification(model, autopilot_hw, mcu, fsd, supercharging, warnings)


# Backward-compatible bridge to the field names scrapers.py / main.py / app.js
# already read (fsd_status, hw_version), so existing filters/badges/CSV export
# keep working while new, more precise fields are added alongside them.
_FSD_STATUS_COMPAT = {
    "purchased_outright": "confirmed",
    "subscription_active": "likely",
    "mentioned_unclear": "possible",
    "none": "none",
}
_HW_COMPAT = {"AP1": "HW1", "AP2": "HW2", "AP2.5": "HW2.5", "HW3": "HW3", "HW4": "HW4", "unknown": None}


def classify_to_legacy_fields(title: str, body_text: str) -> dict:
    """Everything the old schema expects, plus the new precise fields alongside it."""
    c = classify(title, body_text)
    return {
        # legacy fields the existing frontend already renders
        "fsd_status": _FSD_STATUS_COMPAT[c.fsd.value],
        "has_fsd": c.fsd.value in ("purchased_outright", "subscription_active"),
        "has_eap": "enhanced autopilot" in f"{title} {body_text}".lower(),
        "fsd_keywords_found": c.fsd.evidence,
        "fsd_confidence": {"confirmed": 1.0, "likely": 0.7, "possible": 0.3, "unknown": 0.0}[c.fsd.confidence],
        "hw_version": _HW_COMPAT.get(c.autopilot_hw.value),
        # new, precise fields
        "classification": c.to_dict(),
        "mcu_version": c.mcu.value if c.mcu.value != "unknown" else None,
        "fsd_transfer": c.fsd.value,  # purchased_outright | subscription_active | mentioned_unclear | none
        "supercharging_status": c.supercharging.value,
        "warnings": c.warnings,
    }
