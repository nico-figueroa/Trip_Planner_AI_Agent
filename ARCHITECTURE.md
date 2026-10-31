# Architecture

## Goals

Follow the [product requirements](./PRODUCT_REQUIREMENTS.md): keep the app
modular but simple, use deterministic code for persistence and validation, and
use the model only for planning decisions and itinerary generation.

## Runtime shape

```text
Root app.py
    │
    └── trip-planner/app.py (Streamlit UI and session state)
            │
            ├── TripPlannerAgent
            │       └── OpenAI Responses API tool loop
            │               ├── geocode_city ───────── Nominatim
            │               ├── find_nearby_pois ───── Geoapify Places (key required)
            │               └── get_destination_context ─ Wikivoyage (optional)
            │
            ├── Pydantic output and coordinate validation
            ├── PyDeck map (auto-fit zoom) and itinerary rendering
            ├── PDF export ── fpdf2 (generated on download)
            ├── JSON persistence ── app_state.json / feedback.jsonl
            └── Safe application logging ── terminal / log.json (200 events)
```

The root `app.py` provides the documented `streamlit run app.py` command and
loads the implementation from `trip-planner/`. Data paths are resolved relative
to the implementation, so the launch directory does not affect persistence.

## Agent workflow

1. The UI collects destination, duration, interests, optional budget and travel
   style, and an optional natural-language request.
2. The Responses API receives a concise request and a reusable system prompt.
   The model chooses and invokes the registered functions.
3. Tool calls are validated and executed; each call and its bounded result or
   user-safe error is added to the execution trace and returned to the model.
   POI addresses stay in the trace but are omitted from model inputs to save
   tokens. The loop allows 6 tool rounds and 16 tool calls. When either budget
   is reached, unexecuted calls receive a "budget reached" output and the next
   request uses `tool_choice="none"`, so the model finishes the itinerary with
   the data already gathered instead of failing.
4. Nominatim verifies the destination. For multi-region or long trips, the
   prompt allows up to four regional bases, each geocoded as "Town, Country".
   Geoapify supplies named places (with addresses) near each base; the planner
   merges and deduplicates them (up to 80) and records extra bases as `stops`.
   Wikivoyage adds optional context when available.
5. The model returns a strict JSON-schema itinerary. Pydantic checks its shape;
   application validation checks destination consistency and requested days.
6. The app verifies coordinates, renders the plan/map, and stores the active
   plan. Refinement supplies only the selected itinerary, the original
   additional request and start date, and the user's change request, not
   unrelated conversation history. The plan selector uses plan IDs, so a new
   plan is shown immediately instead of a previously selected saved plan.

When a start date is set, `utils/prompts.py` adds `day_dates` (with holiday
labels), `fixed_commitments` (single-date clauses of the additional request
mapped to day numbers), and `free_windows` (uncommitted day ranges with an
allowed travel radius) to the request, so the model never counts calendar days
or guesses how far it may roam. `utils/agent.py` then checks that each
commitment's key words appear on its day; misses trigger one repair request and,
if still missing, a deterministic insertion recorded as
`verify_fixed_commitments` in the trace.

Planning runs in a worker thread so the UI can rotate 20 lighthearted progress
messages every 2.5 seconds in one `st.status` element; the worker never calls
Streamlit. The map's initial
view is centered on the bounding box of the destination, regional bases, and
POIs, with a Web Mercator zoom that keeps every point visible (zoom 12 for a
single point). The "Save as PDF" button builds the report only when clicked.

The UI shows tool calls, arguments, outcomes, and bounded outputs. It does not
expose hidden model reasoning. Persistence is deterministic and is not
delegated to the model.

## Components

| Component | Responsibility |
|---|---|
| `app.py` | Inputs, session state, progress messages, itinerary/map rendering, PDF download, refinement, feedback |
| `utils/agent.py` | Request validation, orchestration, final coordinate and itinerary checks, POI/stop aggregation |
| `utils/openai_agent.py` | Bounded Responses API function-calling loop, forced final answer, and trace |
| `utils/tools.py` | Strict function schemas, tool registry, deterministic dispatch |
| `utils/geocoding.py` | Nominatim request, rate limiting, retry, and memoization |
| `utils/poi_search.py` | Geoapify Places request, POI/address normalization, retry, memoization |
| `utils/pdf_report.py` | Latin-1-safe itinerary PDF report |
| `utils/rag.py` | Bounded optional Wikivoyage retrieval |
| `utils/schemas.py` | Pydantic itinerary and daily-plan models |
| `utils/output_parser.py` | JSON recovery and model-output validation |
| `utils/validation.py` | User request and destination/day consistency validation |
| `utils/persistence.py` | Atomic state writes, safe paths, corrupt-file recovery, feedback append |
| `utils/openai_client.py` | Environment-only key selection and safe OpenAI failure classification |
| `utils/logging_config.py` | Idempotent application-only console/JSON handlers and credential redaction |

## State and data

- Streamlit session state holds the active browser session's plan and transient
  preferences.
- `data/app_state.json` holds the active itinerary and explicitly saved plans.
- `data/feedback.jsonl` holds one feedback record per line.
- `data/log.json` holds the latest 200 sanitized application events.
- OpenAI and Geoapify keys resolve from `trip-planner/.env`, then `.env` in the
  launch directory and its parents (nearest first), then process environment
  variables. The first non-empty value wins. There are no session overrides,
  Streamlit-secrets lookup, or separate connection checks. Resolution does not
  modify process environment variables. Credentials are never persisted or logged.
- Persistence paths are fixed inside the application data directory. Writes
  use a temporary file and atomic replacement.

## Reliability and cost controls

- External requests use explicit timeouts and retry transient/network and
  throttling errors only.
- Nominatim requests are spaced at least 1.1 seconds apart and successful
  geocodes are memoized. POI and guide results use bounded in-process caches.
- The tool loop has fixed round and call budgets with a forced final answer.
  OpenAI requests use a 90-second timeout (long itineraries can exceed 30
  seconds) and one retry. Prompts reuse one system instruction, and refinement
  sends only relevant context.
- Wikivoyage failure is non-fatal. Destination lookup failure blocks itinerary
  presentation; POI failure (including a missing Geoapify key) is shown in the
  trace and the plan can continue without retrieved places.
- Logs contain operation names and exception types, not credentials or request
  bodies. The application logger does not enable third-party SDK debug logs.
  User-facing errors distinguish authentication, quota, permissions, and request
  errors without including provider response bodies.
- Geoapify uses a POST body and an `x-api-key` header, never a key-bearing URL.
  Its successful responses are cached and attributed in the POI/map UI.

## External services and deployment

The app runs as one Streamlit process and calls OpenAI, Nominatim, Geoapify,
and optionally Wikivoyage directly. It requires no database, vector store, or
separate service. Run it from the repository root:

```powershell
streamlit run app.py
```
