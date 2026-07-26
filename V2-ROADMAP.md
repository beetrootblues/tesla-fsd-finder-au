# V2 Roadmap

Grounded in what actually surfaced while building and debugging v2.0 —
not a generic feature wishlist. Split into bugs (things that are wrong
right now) and features (things that would make this a sharper tool).

## Bugs / known gaps, carried over from v2.0

1. **Historical listings mostly lack free-text descriptions.** Backfilling
   classify.py onto the 146 existing listings only resolved HW version on
   5 of them, and zero FSD-purchase or Supercharging signals — because
   most of those listings have blank `description` fields (structured
   JSON-LD summaries, not seller-written text). The classifier is only as
   good as the text it gets. Real fix is in discovery.py's detail-page
   fetch actually landing more often — see "Photo-based classification"
   below for a path that doesn't depend on ad text at all.

2. **`OfflineViewController.swift` exists but nothing presents it.** No
   network-loss hook wires it to the Capacitor bridge. Either implement
   the hook (`@capacitor/network` plugin + swap the root view controller
   on a `WKWebView` load failure) or remove the dead file — right now it's
   the same "looks done, isn't wired up" pattern this whole rewrite was
   partly about fixing elsewhere.

3. **Push notifications register but nothing sends one.** `/api/register-
   device` stores a token; nothing in `main.py` reads `data/devices.json`
   and calls APNs when a price drop fires. Needs a `.p8` APNs key and a
   sender (e.g. `PyAPNs2`) added to the Railway backend.

4. **Legacy year-based HW guesses linger at lower confidence than they
   display.** The v2.0 backfill only overwrote `hw_version` when
   classify.py found real evidence; where it didn't, the old model-
   year-only guess (the one with the Model S/X 2023+ bug) is still
   sitting in the field with no confidence marker at all, since it
   predates the confidence system. Worth a pass to either re-tag these
   explicitly as `possible`/`unknown` or strip them so the UI doesn't
   show an un-scored value next to scored ones.

## Features

### Photo-based classification (the highest-leverage one)
The HW4 tell — red-tinted camera lenses vs HW3's black ones — is
currently only caught if a seller happens to mention "red camera" in
text, which almost none do. Most listings have photos, though. A Vision/
Core ML pass over listing images (front camera cluster crop → lens-colour
classifier) would catch this reliably where text never will, and the
same approach could spot an MCU2-era centre console vs MCU1's in an
interior shot. This is the one feature that would most change how often
the app can say "confirmed" instead of "unknown."

### Ask-the-seller templates
For every `mentioned_unclear` FSD classification, generate the exact
question a buyer should send: *"Can you confirm via your Tesla app
whether FSD shows as a one-off purchase or a monthly subscription?"*
Turns an ambiguous classification into an actionable next step instead
of a shrug.

### Fair-price scoring
`price_history.json` is already being collected per listing but never
aggregated across listings. Compare a listing's price against others of
the same model/year/HW-generation/FSD-status in the dataset and surface
over/under-priced relative to comparable specs — not just "the price
dropped," which is all the current alert system does.

### Classification-aware saved searches
Current alerts are price-drop-only. Extend to: "notify me of any HW4
Model Y under $60k with FSD purchased outright" — filtering on the
fields this app uniquely computes, not just price.

### VIN cross-check
If a listing exposes a VIN (some dealer listings do), decode model year/
plant from the VIN structure itself and cross-check against the text-
based classification — an independent signal to raise or lower
confidence, rather than relying on ad text alone.

### Home Screen widget
Small WidgetKit extension showing the top new or most-recently-price-
dropped listing. Native SwiftUI, so unlike the main app it would
genuinely run through Apple's real Liquid Glass rendering, not a CSS
approximation.

### Community verification
Let a user mark "I inspected this in person, MCU2 confirmed" on a
listing — a lightweight trust layer on top of the automated
classification, visible to anyone else looking at the same ad.

## Explicitly not planned
Re-adding Facebook Marketplace or Pickles as sources — see README for
why those were dropped in v2.0 rather than ported. Re-adding either
would need a genuinely different, ToS-compliant approach, not a revert.
