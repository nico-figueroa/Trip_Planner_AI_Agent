# AI Trip Planner

A Streamlit application that creates personalized, structured itineraries using
the OpenAI Responses API and live OpenStreetMap-based data. The agent calls
Nominatim to verify a destination, the Geoapify Places API to retrieve nearby
places, and optionally Wikivoyage for destination context. It displays the
itinerary and locations on an interactive PyDeck map, exports itineraries as
PDF, saves plans and feedback as JSON/JSONL, and supports follow-up refinement.

## Features

- Responses API function calling with a bounded agent loop and visible tool trace
- Long, multi-region trips: the agent geocodes up to four regional bases; when
  its tool budget is reached it finishes the itinerary with the data gathered
- Pydantic validation for structured itineraries and destination coordinates
- Nominatim geocoding and Geoapify search for attractions, museums, parks,
  national parks, restaurants, cafes, and landmarks, listed with addresses
- Optional Wikivoyage context retrieval; guide failures do not block planning
- PyDeck map with destination, regional bases, retrieved POIs, and matched
  itinerary stops, auto-zoomed to fit every point
- Optional start date: each day shows its calendar date and holidays are
  labeled; dated commitments in the additional request (for example
  "December 24 San Jose christmas dinner") are pinned to the matching day in
  code, the route is planned around them with stated driving times, and the
  result is verified (repaired or inserted if missing); refinement keeps them
- Rotating, lighthearted progress messages while a plan is generated or refined
- Active and saved itineraries, PDF export, feedback, and refinement
- Request timeouts, retry policies, rate limiting, and in-memory response caches
- Credential-safe terminal logs plus the latest 200 events in `data/log.json`

## Requirements

- Python 3.14.6
- Dependencies listed in `trip-planner/requirements.txt`
- An OpenAI API key to generate or refine itineraries
- A free Geoapify API key for nearby places (planning continues without it,
  but no places are retrieved)

## Setup

Run these commands from the repository root:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r .\trip-planner\requirements.txt
$env:OPENAI_API_KEY = "your-api-key"
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

### Nearby places (Geoapify)

Nearby places come from the Geoapify Places API, which replaced Overpass after
repeated Overpass timeouts. Obtain a free key at
[Geoapify projects](https://myprojects.geoapify.com/) and configure
`GEOAPIFY_API_KEY` in a searched `.env` file or your process environment. Never
paste keys into chat or commit them.

Geoapify returns OpenStreetMap-based museums, parks, national parks, landmarks,
attractions, restaurants, and cafes, including a street address shown in the
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
    pdf_report.py              Itinerary PDF export (fpdf2)
    persistence.py             Safe JSON/JSONL storage
    poi_search.py              Geoapify Places retrieval with addresses
    prompts.py                 System instructions and request payload
    rag.py                     Optional Wikivoyage retrieval
    schemas.py                 Pydantic itinerary schemas
    tools.py                   Function registry and dispatch
    validation.py              Request and itinerary validation
```

See [PRODUCT_REQUIREMENTS.md](./PRODUCT_REQUIREMENTS.md) for product
acceptance criteria and [ARCHITECTURE.md](./ARCHITECTURE.md) for workflow
details.
