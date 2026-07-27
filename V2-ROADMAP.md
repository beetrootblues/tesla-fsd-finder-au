# V2 Roadmap

Grounded in what actually surfaced while building and debugging v2.0 —
not a generic feature wishlist. Status as of the V2 implementation pass.

## Shipped

- **Seller-question templates** (`classify.py` → `suggest_seller_questions`) —
  for every unresolved field, the exact question to send. Rendered as a
  card disclosure with a one-tap "draft email" action (mailto:, human
  sends — see "Explicitly not built" below for why nothing sends on its own).
- **Fair-price scoring** (`pricing.py`) — compares each listing against
  others of similar model/HW-tier/build-year, requires >=3 real
  comparables before scoring, explicit caveat everywhere that it doesn't
  account for odometer/trim/condition.
- **VIN cross-check** (`vin_check.py`) — decodes year/make via NHTSA's
  public vPIC API for listings that expose a VIN. Written against the
  documented API contract; the live round-trip is unverified from this
  sandbox's restricted network — confirm it works once deployed.
- **Community verification** — buyers can mark a field as physically
  confirmed. Kept deliberately separate from classify.py's own confidence
  system rather than merged into it (different evidence categories).
- **Legacy HW guess cleanup + date-sanity bound** — the year-based
  guesses from v1.2 and a date-extraction bug that could infer a build
  date in the future are both fixed.

## Explicitly not built, on purpose

- **Autonomous email contact** — asked for directly, declined as
  specified. No reliable seller email exists on these platforms in the
  first place, and even where one did, autonomous unsolicited contact at
  scale raises real Spam Act and platform-ToS exposure, plus account-
  flagging risk. Built the safer version instead: a human-reviewed
  mailto: draft.
- **Photo-based classification** — still the highest-leverage idea on
  this list (the HW4 red-camera-lens tell is real and currently only
  caught if a seller happens to type it out), but this sandbox can't
  fetch real listing photos to calibrate or test against. Shipping an
  uncalibrated heuristic with a confident-sounding label would be exactly
  the problem this whole rewrite was trying to fix elsewhere. Worth
  doing properly, with real photos to validate against, not blind.
- **Home Screen widget** — needs a new Xcode target, which means hand-
  editing `project.pbxproj`'s interlinked sections without Xcode's GUI.
  Too high a risk of corrupting the project that's currently building
  correctly, for something that can't be visually verified from here
  anyway. Add this one in Xcode directly.
- **Classification-aware saved searches** — not started. Reasonable next
  piece if there's appetite for more: storage + matching logic is
  straightforward, though actual delivery still depends on the push-
  notification sender (see README/DEPLOY-IOS.md) which isn't wired up
  either.

## Bugs / known gaps carried over from v2.0, still open

1. Historical listings mostly lack free-text descriptions, capping how
   often the classifier can say anything beyond "unknown."
2. `OfflineViewController.swift` exists but nothing presents it.
3. Push notifications register but nothing sends one server-side.

## Explicitly not planned
Re-adding Facebook Marketplace or Pickles as sources — see README for
why those were dropped in v2.0 rather than ported.

