# AI Trip Planner

A Streamlit application that creates personalized, structured itineraries using
the OpenAI Responses API and live OpenStreetMap-based data. The agent calls
Nominatim to verify a destination, the Geoapify Places API to retrieve nearby
places, and optionally Wikivoyage for destination context. It displays the
itinerary and locations on an interactive PyDeck map, exports itineraries as
PDF/JSON, saves private plans and feedback in PostgreSQL, and supports refinement.
See [IMPLEMENTATION.md](./IMPLEMENTATION.md) for local PostgreSQL, Streamlit
Community Cloud, Azure, Supabase migrations, and optional OIDC setup.

## Features

- Responses API function calling with a bounded agent loop and visible tool trace
- Long, multi-region trips: the agent geocodes up to four regional bases; when
  its tool budget is reached it finishes the itinerary with the data gathered
- Pydantic validation for structured itineraries and destination coordinates
- Nominatim geocoding and Geoapify search for attractions, museums, parks,
  national parks, restaurants, cafes, and landmarks, listed with addresses
- Optional Wikivoyage semantic vector search using a local CPU model and
  source-linked passages; guide/model failures do not block planning
- PyDeck map with destination, regional bases, retrieved POIs, and matched
  itinerary stops, auto-zoomed to fit every point
- Optional start date: each day shows its calendar date and holidays are
  labeled; dated commitments in the additional request (for example
  "December 24 San Jose christmas dinner") are pinned to the matching day in
  code, the route is planned around them with stated driving times, and the
  result is verified (one repair attempt, then rejection if still inconsistent);
  refinement keeps them
- Rotating, lighthearted progress messages while a plan is generated or refined
- Inclusive start/end date ranges that synchronize duration
- Optional OIDC accounts with private PostgreSQL/Supabase saved plans
- Manual categorized expenses and separately labeled model cost estimates
- Sidebar-configurable outputs, light/dark maps, and stable day filtering
- Sidebar legacy-plan import, save/download actions, and optional agent trace
- Start-new-trip controls at the top and end of trip output reset session inputs
- Temporal schematic map paths and verified named beach locations
- PDF/JSON export/import, explicit day-only refinement, and before/after views
- Side-by-side trip comparison and explicitly enabled two-alternative generation
- Persistent feedback statistics, POI vote boosts, and administrator-approved
  advisory instruction improvements (never automatic core-prompt rewriting)
- Request timeouts, retry policies, rate limiting, and in-memory response caches
- Credential-safe terminal logs plus the latest 200 events in `data/log.json`

## Requirements

- Python 3.14.6
- Dependencies listed in `trip-planner/requirements.txt`
- An OpenAI API key to generate or refine itineraries
- A free Geoapify API key for nearby places (planning continues without it,
  but no places are retrieved)
- Local semantic weights prepared for vector retrieval
- Local PostgreSQL for development/testing, or Supabase for cloud persistence
- A configured OIDC provider only for optional personal account features

## Setup

Run these commands from the repository root:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r .\trip-planner\requirements.txt
$env:OPENAI_API_KEY = "your-api-key"
python .\deploy\prepare_model.py
streamlit run app.py
```

Alternatively, add the keys to `trip-planner/.env` (ignored by Git):

```dotenv
OPENAI_API_KEY = "your-api-key"
GEOAPIFY_API_KEY = "your-geoapify-key"
```

Key lookup uses **`trip-planner/.env` first, then `.env` in the launch directory
and each parent directory (nearest first), then the process environment**.
The first non-empty `OPENAI_API_KEY` value wins. Missing or blank values allow
lookup to continue. This also applies to `GEOAPIFY_API_KEY`.
There is no API-key sidebar, connection-test button, or session override.
Cloud administrators may convey top-level settings in gitignored
secrets.toml/Community Cloud Secrets; Streamlit exports these as environment
variables. API key lookup remains .env/environment, while native OIDC settings
use Streamlit secrets. Key values are never displayed or written to
application state, feedback, or logs. Never commit `.env`.

The entry point is root `app.py`; implementation files live under
`trip-planner/`. Anonymous plans are session-only. Configure `DATABASE_URL`
for local PostgreSQL, or `SUPABASE_URL` plus `SUPABASE_SERVICE_ROLE_KEY` for
cloud accounts/feedback. The existing shared JSON files remain intact but are
not automatically displayed to public users.

Sign-in starts a new session: sign in before planning to save directly, or
export plan JSON, sign in, import, then save. Keep exports private.

### Troubleshoot authentication

For HTTP 401, update `OPENAI_API_KEY` in the first matching `.env` file or the
process environment. A stale `.env` value takes priority over a valid process
environment value. Restart Streamlit after changing an environment variable.
Authentication is checked during normal generation/refinement requests; no
separate diagnostic API calls are made. HTTP 429 requires checking project
billing/quota or waiting for a rate limit to clear.

### Nearby places (Geoapify)

Nearby places come from the Geoapify Places API, which replaced Overpass after
repeated Overpass timeouts. Obtain a free key at
[Geoapify projects](https://myprojects.geoapify.com/) and configure
`GEOAPIFY_API_KEY` in a searched `.env` file or your process environment. Never
paste keys into chat or commit them.

Geoapify returns OpenStreetMap-based museums, parks, beaches, national parks,
landmarks, attractions, restaurants, and cafes, including a street address shown in the
Nearby places table and PDF. The published free plan provides
[3,000 credits/day](https://www.geoapify.com/pricing/); a Places request with
limit 20 costs [one credit](https://www.geoapify.com/pricing-details/). Quotas
and terms can change. The app shows Geoapify/OSM attribution with place data.
If the key is missing or Geoapify fails, the trace reports POI retrieval as
unavailable and the planner continues without retrieved places.

### Application logs

Application events appear in the launch terminal and in
`trip-planner/data/log.json`, a JSON array retaining the most recent **200 events**.
Each event contains a UTC timestamp, level, logger, and sanitized message.
Tool executions, validation outcomes, and safe API failure metadata are logged;
keys, provider response bodies, and hidden model reasoning are not.
Logs use atomic file replacement and are Git-ignored. A corrupt log is explicitly
reported and reset; an unwritable log is reported on stderr without disabling
terminal logging.

## Run tests

```powershell
Push-Location .\trip-planner
python -m pytest
Pop-Location
```

Unit tests mock all external services. To manually verify live integrations,
run the app with a valid API key and submit a short trip request. Nominatim is
limited to one uncached request per second; avoid repeated live test runs.

Database integration is opt-in with `TEST_DATABASE_URL` pointing to the
dedicated `trip_planner_test` database. The default suite explicitly skips it
when unconfigured and never uses development/user data as a test database.
The root Pyright configuration mirrors the runtime import path for the nested
application package and deployment scripts.

## Project layout

```text
app.py                         Root Streamlit entry point
trip-planner/
  app.py                       Streamlit interface
  requirements.txt             Runtime and test dependencies
  data/                        JSON/JSONL persistence
  tests/                       Offline unit tests
  utils/
    core/                      Shared service configuration
    planning/                  Agent, prompts, tools, schemas, validation, feedback review
    providers/                 OpenAI, Nominatim, Geoapify, Wikivoyage integrations
    storage/                   OIDC account access, PostgreSQL, JSON persistence, logging
    trips/                     Dates, budgets, maps, imports, and PDF reports
deploy/                        Database schemas, model preparation and cloud startup
IMPLEMENTATION.md              Administrator deployment and migration instructions
```

See [PRODUCT_REQUIREMENTS.md](./PRODUCT_REQUIREMENTS.md) for product
acceptance criteria and [ARCHITECTURE.md](./ARCHITECTURE.md) for workflow
details.
