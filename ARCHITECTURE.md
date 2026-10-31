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
            │               ├── find_nearby_pois ───── Overpass → Geoapify on failure (optional)
            │               └── get_destination_context ─ Wikivoyage (optional)
            │
            ├── Pydantic output and coordinate validation
            ├── PyDeck map and itinerary rendering
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
4. Nominatim verifies the destination. Overpass supplies nearby named places.
   If Overpass fails and a Geoapify key is configured, Geoapify supplies
   equivalent normalized POI records with a provider marker. A successful
   empty Overpass result does not trigger fallback. Wikivoyage adds optional
   context when available.
5. The model returns a strict JSON-schema itinerary. Pydantic checks its shape;
   application validation checks destination consistency and requested days.
6. The app verifies coordinates, renders the plan/map, and stores the active
   plan. Refinement supplies only the selected itinerary and the user's change
   request, not unrelated conversation history.

The UI shows tool calls, arguments, outcomes, and bounded outputs. It does not
expose hidden model reasoning. Persistence is deterministic and is not
delegated to the model.

## Components

| Component | Responsibility |
|---|---|
| `app.py` | Inputs, session state, itinerary/map rendering, refinement, feedback |
| `utils/agent.py` | Request validation, orchestration, final coordinate and itinerary checks |
| `utils/openai_agent.py` | Bounded Responses API function-calling loop and trace |
| `utils/tools.py` | Strict function schemas, tool registry, deterministic dispatch |
| `utils/geocoding.py` | Nominatim request, rate limiting, retry, and memoization |
| `utils/poi_search.py` | Overpass primary, optional Geoapify fallback, POI normalization, retry, memoization |
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
- The tool loop has a fixed turn limit. OpenAI retries are bounded, prompts
  reuse one system instruction, and refinement sends only relevant context.
- Wikivoyage failure is non-fatal. Destination lookup failure blocks itinerary
  presentation; POI failure is shown in the trace and the plan can continue
  without retrieved places.
- Logs contain operation names and exception types, not credentials or request
  bodies. The application logger does not enable third-party SDK debug logs.
  User-facing errors distinguish authentication, quota, permissions, and request
  errors without including provider response bodies.
- Geoapify uses a POST body and an `x-api-key` header, never a key-bearing URL.
  Its successful responses are cached and attributed in the POI/map UI.

## External services and deployment

The app runs as one Streamlit process and calls OpenAI, Nominatim, Overpass,
and optionally Geoapify and Wikivoyage directly. It requires no database, vector store, or
separate service. Run it from the repository root:

```powershell
streamlit run app.py
```
