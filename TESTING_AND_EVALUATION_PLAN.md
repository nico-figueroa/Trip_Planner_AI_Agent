# Testing and Evaluation Plan

## Strategy

The default test suite is offline and deterministic. It mocks external HTTP
services and the OpenAI Responses API so tests do not consume API quota or
violate Nominatim's public-service rate limit.

Run from the repository root:

```powershell
Push-Location .\trip-planner
python -m pytest
Pop-Location
```

## Unit coverage

| Area | Coverage |
|---|---|
| Request validation | Missing/oversized input, duration boundaries, destination consistency |
| Structured output | JSON recovery, Pydantic validation, Unicode destination matching, day count |
| Nominatim | Address and coordinate mapping, User-Agent, empty results |
| Geoapify Places | Address/category normalization, invalid points, cache isolation, missing key, header authentication, sanitized provider failure |
| Wikivoyage | Extract parsing and non-fatal retrieval failure |
| Tool layer | Registered dispatch, unknown tools, invalid arguments |
| Agent loop | Responses API function calls, call-output linkage, structured final output, tool errors, forced final itinerary at call/round budgets, addresses omitted from model inputs |
| Planner workflow | Verified destination, coordinates, POI results, merged multi-region POIs and stops, prompt length |
| PDF export | Valid PDF bytes, Unicode text replacement, legacy plan shapes |
| Persistence | Save/load, missing and corrupt files, path safety, JSONL append |
| OpenAI configuration | .env search order and precedence, blank/missing values, environment fallback, no Streamlit secrets, safe HTTP 401/429/400 guidance, 90-second timeout |
| Logging | Exact 200-event bound, corrupt-log recovery, path safety, redaction, write failures, idempotent handlers |
| Streamlit UI | Root entry point, background generation with progress messages, Name/Category/Address places table, Geoapify attribution, PDF button, auto-fit map view, text-only map tooltips, absence of API-key sidebar |

## Integration and manual acceptance

With an OpenAI key configured, submit a short trip request and verify:

1. The model invokes geocoding and POI retrieval through the Responses API.
2. The trace shows each call, arguments, result or graceful error.
3. The final JSON validates and includes destination, overview, travel notes,
   and one activity list per requested day.
4. The destination, regional bases, retrieved POIs, and any matched itinerary
   stops appear on the PyDeck map, and the initial zoom shows all of them.
5. Active and explicitly saved plans survive an app restart.
6. Refinement updates the active plan, and feedback appends to JSONL.
7. Missing keys, invalid destinations, provider failures, and malformed model
   output produce user-facing errors without displaying secrets.
8. Generation and refinement use `OPENAI_API_KEY` from the documented `.env`
   search order or process environment; invalid keys produce safe HTTP 401
   guidance. No key-entry or connection-test controls are displayed.
9. Nearby places show name, category, and address with Geoapify/OSM
   attribution; "Save as PDF" downloads a readable report.
10. Progress messages rotate in place, without flicker, while a plan is
    generated or refined.
11. Tool and validation events appear in both terminal output and
    `trip-planner/data/log.json`, without credentials or provider response bodies.
12. A newly generated plan is displayed even when a saved plan was previously
    selected.
13. With a start date, dated commitments (comma-, semicolon-, or line-separated)
    land on the matching day, day headers show dates, and travel between
    commitments stays realistic (manual check: 19-day Costa Rica trip starting
    2026-12-21 places Dec 22/24/25/31, Jan 1, and Jan 7 on days 2/4/5/11/12/18,
    keeps days 1-4 near San Jose, and uses the 5-day gaps for La Fortuna and
    the beach). The trace's `verify_fixed_commitments` step reports repairs.

Live integration checks are manual and should be run sparingly. Nominatim
requests are limited to one uncached request per 1.1 seconds; use a single
destination per manual check. Wikivoyage is optional and its absence must not
block itinerary generation.

### Verified live checks

A previous minimal OpenAI Responses connection check succeeded using the local `.env`
configuration. A one-day Seattle itinerary also completed with real OpenAI
function calls and schema validation (10.4 seconds, Geoapify places).

After Overpass was removed, the previously failing 19-day, multi-region Costa
Rica request completed in 26 seconds: 12 tool calls (one unmatched geocode
handled gracefully), 19 validated days, 61 merged Geoapify places with
addresses, and 5 regional bases on the map. The prior attempt failed after
about 3.5 minutes because Overpass timeouts and a hard tool limit stopped
the loop. These runs verify integration paths, not an availability SLA or a
general latency guarantee. Tests never reproduce these paid/quota-consuming
calls automatically.
The standalone connection-check function and UI were subsequently removed;
normal planning remains the live integration path.

## Quality evaluation

Score benchmark itineraries from 1–5 for relevance, personalization, and
practicality. Spot-check named venues against retrieved POIs. Track completion
rate and user feedback over representative requests; do not make automated
claims about hallucination rates or a 30-second latency target from unit tests.

## Security checks

- Confirm no API key is committed, written to persistence, logged, or rendered
  in plain text.
- Confirm no API-key input is present and credentials are not read from browser
  session state or Streamlit secrets, or added to saved plans or feedback.
- Confirm persistence rejects paths outside the app data directory.
- Confirm request and provider errors do not render response bodies or headers.
- Confirm map tooltips use plain text rather than interpolating untrusted POI
  names or categories into HTML.
