/* ==========================================================================
   Tesla FSD Finder Australia v2.0 - Runtime configuration
   ==========================================================================
   The same frontend is served three ways:
     - Web preview:      same-origin  ->  API_BASE stays "" and /api calls
                                           hit the FastAPI backend directly.
     - Bundled mobile:   the Capacitor app loads static/ locally, so the
                           backend lives elsewhere. Point API_BASE at your
                           deployed backend, e.g.:
                           window.API_BASE = "https://fsd-finder.example.com";
   Edit this file, then rebuild the .apk / .ipa (or just reload the page
   on web). No other code changes needed.
   ========================================================================== */

(function () {
  // Empty string = same origin. Trailing slashes are stripped so callers can
  // write api("/api/listings") regardless of whether this ends in "/".
  window.API_BASE = (window.API_BASE || "").replace(/\/+$/, "");
})();
