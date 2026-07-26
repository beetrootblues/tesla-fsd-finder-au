# App Store Listing — Tesla FSD Finder AU

> Note on the name: "Tesla" is Tesla, Inc.'s trademark. Apple's review
> guidelines and trademark policy generally don't allow a third-party
> trademark to headline an app name/icon without permission, even for a
> compatible/enthusiast tool. Plenty of car-community apps get away with
> mentioning a make in the description; fewer get away with it as the
> literal app title. If you actually submit this, consider leading with
> something like "FSD Finder — for Tesla" or "EV Hardware Finder AU" and
> using "Tesla" only inside the description where it's describing
> compatibility, not branding the app. This doc gives you both a name
> variant and the description either way.

---

## App Name (30 char limit)
**FSD Finder — for Tesla**
(alt, if going the safer route: **EV Hardware Finder AU**)

## Subtitle (30 char limit)
Know what hardware you're buying

## Promotional Text (170 char, editable anytime without review)
Every listing gets a confidence-scored hardware readout — Autopilot generation, MCU version, and whether FSD actually transfers to you. Not just a keyword match.

## Description (4000 char limit)

Buying a used Tesla in Australia means decoding a used-car ad written by
someone who may not know their own car's hardware. "Full self-driving"
could mean a one-off purchase that transfers with the car, or an active
subscription that ends the moment ownership changes. "MCU2" and "HW4"
get used loosely. FSD Finder reads every listing the way a specialist
would, and tells you exactly how sure it is — not just what it thinks.

**What it checks, on every listing:**

• **Autopilot hardware generation** — AP1, AP2, AP2.5, HW3, or HW4/AI4,
  with the reasoning shown: an explicit mention, a build-date inference,
  or a visual cue like red-tinted camera lenses (a HW4 tell). Cross-
  checked against what's actually possible for an Australian-delivered
  car — HW4 was never fitted to a Model S or X sold new here, since
  local deliveries ended before HW4 existed.

• **MCU1 vs MCU2** (Model S/X) — from explicit mentions, feature
  references (Netflix/Theater/Arcade require MCU2), or build date
  against the March 2018 cutover, including the genuine ambiguity of
  cars built in that exact month.

• **FSD: purchased vs. subscribed** — the distinction that actually
  matters. A one-off FSD purchase is tied to the car's VIN and transfers
  to you on private sale. An active subscription is tied to the
  seller's Tesla account and does not. The app tells you which one an
  ad is actually describing, or flags it as unclear so you know to ask.

• **Unlimited Supercharging** — flags claims of free/unlimited
  Supercharging and cross-checks the pre-2017 delivery window where
  it's reliably transferable, versus later promotions that are usually
  tied to the original owner.

**Every field shows its confidence and its evidence** — Confirmed,
Likely, Possible, or Unknown — because none of this comes from the car
itself, only from what a seller wrote. The app also flags outright
contradictions, like HW4 claimed on a Model S, so you catch template
errors or ambiguous listings before you waste a trip.

**Beyond classification:**

• Searches Carsales, Drive, Gumtree, and CarsGuide, refreshed every 6
  hours
• Card, table, and map views
• Price history tracking with drop alerts
• Side-by-side comparison for up to 3 listings
• Watchlist with heart-to-save
• Free-text search across every field
• Dark and light themes
• Face ID lock on launch

FSD Finder doesn't just aggregate listings — it reads them critically,
the way you would if you already knew what to look for.

---

## Keywords (100 char, comma-separated)
tesla,fsd,autopilot,ev,electric car,used car,model 3,model y,model s,model x,supercharging,mcu

## What's New (for the first release)
Initial release: hardware/MCU/FSD-transfer classification across four
Australian marketplaces, price tracking, and comparison tools.

## App Privacy Nutrition Label (for App Store Connect, not shown to users directly)
- Data NOT linked to identity: search/filter usage (if you add analytics later)
- Data linked to identity: none currently collected
- Location: used locally for map view only, not transmitted anywhere
  (confirm this stays true if you add server-side location features)
- No advertising, no tracking across apps/websites
