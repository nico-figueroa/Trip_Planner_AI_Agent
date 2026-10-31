# AI Trip Planner

A Streamlit application that creates personalized, structured itineraries using
the OpenAI Responses API and live OpenStreetMap data. The agent calls Nominatim
to verify a destination, Overpass to retrieve nearby places, and optionally
Wikivoyage for destination context. It displays the itinerary and locations on
an interactive PyDeck map, saves plans and feedback as JSON/JSONL, and supports
follow-up refinement.

## Features

- Responses API function calling with a bounded agent loop and visible tool trace
- Pydantic validation for structured itineraries and destination coordinates
- Nominatim geocoding and Overpass search for attractions, museums, parks,
  restaurants, cafes, and landmarks
- Optional Geoapify Places fallback when Overpass fails
- Optional Wikivoyage context retrieval; guide failures do not block planning
- PyDeck map with destination, retrieved POIs, and matched itinerary stops
- Active and saved itineraries, feedback, and refinement
- Request timeouts, retry policies, rate limiting, and in-memory response caches
- Credential-safe terminal logs plus the latest 200 events in `data/log.json`

## Requirements

- Python 3.14.6
- Dependencies listed in `trip-planner/requirements.txt`
- An OpenAI API key to generate or refine itineraries

## Setup

Run these commands from the repository root:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r .\trip-planner\requirements.txt
$env:OPENAI_API_KEY = "your-api-key"
streamlit run app.py
```

Alternatively, add `OPENAI_API_KEY` to `trip-planner/.env` (ignored by Git):

```dotenv
OPENAI_API_KEY = "your-api-key"
```

Key lookup uses **`trip-planner/.env` first, then `.env` in the launch directory
and each parent directory (nearest first), then the process environment**.
The first non-empty `OPENAI_API_KEY` value wins. Missing or blank values allow
lookup to continue. This also applies to `GEOAPIFY_API_KEY`.
There is no API-key sidebar, connection-test button, session override, or
Streamlit-secrets lookup. Key values are never displayed or written to
application state, feedback, or logs. Never commit `.env`.

The entry point is the root `app.py`; implementation and data files live under
`trip-planner/`. Runtime state is stored in `trip-planner/data/app_state.json`
and `trip-planner/data/feedback.jsonl`.

### Troubleshoot authentication

For HTTP 401, update `OPENAI_API_KEY` in the first matching `.env` file or the
process environment. A stale `.env` value takes priority over a valid process
environment value. Restart Streamlit after changing an environment variable.
Authentication is checked during normal generation/refinement requests; no
separate diagnostic API calls are made. HTTP 429 requires checking project
billing/quota or waiting for a rate limit to clear.

### Optional free-tier POI fallback

Overpass remains the primary POI provider. To enable Geoapify when Overpass
fails, obtain a key at [Geoapify projects](https://myprojects.geoapify.com/) and
configure `GEOAPIFY_API_KEY` in a searched `.env` file or your process
environment. Never paste keys into chat or commit them. No additional dependency is
needed.

Geoapify supports the nearby museum, park, landmark/attraction, restaurant, and
cafe searches used here. Its indexed OpenStreetMap data is not an exact
replacement for live Overpass queries. The published free plan provides
[3,000 credits/day](https://www.geoapify.com/pricing/); a Places request with
limit 20 costs [one credit](https://www.geoapify.com/pricing-details/). Quotas
and terms can change. The app shows Geoapify/OSM attribution with fallback data.
A successful empty Overpass result does not trigger a billable fallback.
If both providers fail, the trace reports POI retrieval as unavailable and the
planner can continue without retrieved places.

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

## Project layout

```text
app.py                         Root Streamlit entry point
trip-planner/
  app.py                       Streamlit interface
  requirements.txt             Runtime and test dependencies
  data/                        JSON/JSONL persistence
  tests/                       Offline unit tests
  utils/
    agent.py                   Planner workflow and final validation
    config.py                  Service endpoints and model configuration
    geocoding.py               Nominatim client and cache
    logging_config.py          Safe terminal and bounded JSON logging
    openai_agent.py            Responses API tool loop and trace
    openai_client.py           API key resolution and client setup
    output_parser.py           Structured itinerary parsing
    persistence.py             Safe JSON/JSONL storage
    poi_search.py              Overpass retrieval and optional Geoapify fallback
    prompts.py                 System instructions and request payload
    rag.py                     Optional Wikivoyage retrieval
    schemas.py                 Pydantic itinerary schemas
    tools.py                   Function registry and dispatch
    validation.py              Request and itinerary validation
```

See [PRODUCT_REQUIREMENTS.md](./PRODUCT_REQUIREMENTS.md) for product
acceptance criteria and [ARCHITECTURE.md](./ARCHITECTURE.md) for workflow
details.
