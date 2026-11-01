# Architecture

Follow [PRODUCT_REQUIREMENTS.md](./PRODUCT_REQUIREMENTS.md); deployment and
administrator configuration are in [IMPLEMENTATION.md](./IMPLEMENTATION.md).
One Streamlit process performs planning, retrieval, deterministic validation,
and optional feedback review; no orchestration service is required.

## Runtime

```text
Root app.py -> trip-planner/app.py
  |
  +-- Optional native OIDC -> verified issuer/subject -> private owner hash
  |
  +-- TripPlannerAgent -> OpenAI Responses API function loop
  |     +-- geocode_city -> Nominatim
  |     +-- search_pois -> cached Geoapify candidates + current feedback boosts
  |     +-- get_destination_context -> Wikivoyage chunks -> local semantic vectors
  |     +-- Pydantic/day/commitment validation + named-location resolution
  |
  +-- Session plans, filters, date ranges, expenses, alternatives/comparisons
  +-- PyDeck meter dots + temporal schematic paths + light/dark maps
  +-- Sidebar imports, save/download controls, and optional execution trace
  +-- PDF and private JSON exports/imports
  |
  +-- CloudStore / PostgresStore
  |     +-- Local PostgreSQL (development/testing)
  |     +-- Supabase PostgreSQL REST (cloud deployment, server-only key)
  |           +-- planner_accounts (owner + JSONB state)
  |           +-- planner_feedback (deduplicated explicit votes/comments)
  |           +-- planner_guidance (pending/approved/rejected proposals)
  |
  +-- Feedback review -> pending advisory rule -> administrator approval
  +-- Safe terminal + bounded data/log.json logging
```

## Planning and refinement

The UI resolves duration from an inclusive date range when provided. Code
computes day/date mappings, holiday labels, pinned commitments, and free travel
windows. The model receives concise instructions and up to eight approved
advisory rules; these cannot override core instructions or current-user
constraints.

The agent has six tool rounds and sixteen calls. Reaching a budget forces a
final answer from gathered data instead of further retrieval. Geoapify results
are merged/deduplicated up to eighty places. Provider addresses remain
display-only. Nominatim geocodes are cached and spaced 1.1 seconds apart;
Geoapify calls are also rate limited.

Pydantic validates the final itinerary and nullable daily cost estimates.
Destination/day validation follows. Missing commitments trigger one repair
request; continued failure rejects the result and preserves the previous plan.
No success-shaped insertion is used to conceal a contradictory schedule.
Commitment matching is a keyword heuristic, not proof of route feasibility.

For explicit single-day regeneration, the prompt requires all other days to
remain unchanged, and code copies unchanged days/overview/notes from the original.
Expenses and original date constraints survive refinement. Before/after
snapshots remain available for comparison.

Up to eight otherwise unresolved named stops can be geocoded after generation.
Only retrieved/geocoded coordinates enter the map; unresolved visits are
reported and break the schematic path. These lookups are additional to the
agent's tool-call budget and remain provider-rate-limited.

## Semantic retrieval

`rag.py` fetches destination-scoped Wikivoyage extracts, bounds article text at
80,000 characters, chunks into overlapping passages, and caches normalized
embeddings using a locally prepared all-MiniLM-L6-v2 model. Cosine vector search
selects up to three bounded passages, with scores and source URLs. Weights never
execute remote Python code; inference does not use OpenAI embeddings.

The optional guide tool explicitly reports missing weights/provider failure.
ADR-006 controls availability; ADR-007 defines semantic retrieval. There is no
contradiction and no hosted vector database. Model and vector caches are
process-local, not permanent user memory.

## Code organization

The `trip-planner/utils` package groups modules by responsibility:

- `core`: shared service configuration.
- `planning`: agent orchestration, Responses API function calling, prompts,
  schemas, validation, and bounded feedback review.
- `providers`: OpenAI, Nominatim, Geoapify, and Wikivoyage integrations.
- `storage`: private account access, PostgreSQL and JSON persistence, and
  credential-safe logging.
- `trips`: deterministic date/budget/map features and PDF reporting.

The root `trip-planner/app.py` remains the Streamlit entry point and composes
these modules into the user experience.

## Session controls

The legacy plan importer and itinerary save/PDF/JSON export actions are in the
sidebar. Agent execution details also render there only when enabled in visible
outputs. “Start new trip” is available above the request form and after the
current output; both controls clear trip-specific output and request/refinement
inputs while retaining account and sidebar preferences.

Feedback submissions show only a generic evaluation acknowledgement. Review
status is retained in session tracking and server logs; review rationale and
proposed guidance remain available only to configured administrators.

## Identity, persistence, and feedback

Native Streamlit OIDC proves identity; optional sign-in is not a shared-password
gate. State reads/writes use a hash of verified issuer/subject. Backend credentials
remain server-only. Supabase public browser roles have no direct table/RPC
access; the service role bypasses RLS, so server-side owner filters and trusted
backend configuration are essential.

`DATABASE_URL` chooses local PostgreSQL; otherwise Supabase configuration is
used. No automatic shared local JSON loading occurs. Legacy files are preserved;
private exports/imports bridge older plans and OIDC's new-session behavior.
Account saves are snapshots; concurrent saves for the same account are
last-write-wins. Separate accounts remain isolated.

Votes affect only returned candidate ranking: base provider order on a 0–1
scale plus +0.25/upvote or -0.35/downvote, using the latest vote per actor/POI.
Boosts are applied outside cached provider responses.

Written comments receive one bounded model review. Proposals are never activated
automatically: only verified configured administrators can approve/reject them.
Core prompts are not edited on disk. Tone alone cannot establish a complaint's
falsity. Only bounded approved guidance is included in future requests.

## UI and maps

Planning runs in a worker thread; one status element rotates twenty messages
every 2.5 seconds without recreating a spinner. The worker never calls Streamlit.
Stable plan/map keys and session state keep filters from clearing itineraries.

Map data is deduplicated; dots use meter radii with 3–12 px visibility bounds,
auto-fit view, smooth scroll configuration, and light/dark basemaps. Paths follow
ordered visits across days, not provider road-routing results. Legacy plans
fall back to textual occurrence order when structured locations are unavailable.
Day filters affect display only, not stored plans or model calls.

Manual expenses use decimal arithmetic. Model estimates remain separately
labeled, not asserted actual prices. Alternative generation requires an explicit
sidebar-enabled action and adds two planning requests. Existing-plan and
refinement comparisons do not trigger model calls.

## Modules

| Module | Responsibility |
|---|---|
| `app.py` | Native UI, session state, account actions, reports/configuration |
| `agent.py`, `openai_agent.py` | Orchestration, bounded function loop, validation/refinement |
| `tools.py`, `geocoding.py`, `poi_search.py`, `rag.py` | Tool contracts, retrieval, caching |
| `schemas.py`, `validation.py`, `output_parser.py`, `prompts.py` | Output/request contracts and prompt construction |
| `trip_features.py`, `pdf_report.py` | Dates, budgets, safe imports/links, temporal map data, export |
| `accounts.py`, `postgres_store.py` | Verified identity, server-only SQL/REST persistence |
| `feedback.py` | Untrusted-comment review into pending advisory proposals |
| `config.py`, `openai_client.py`, `logging_config.py`, `persistence.py` | Credentials, clients, legacy file helpers, bounded logs |

External requests have timeouts and bounded retries. OpenAI uses a 90-second
request timeout and one SDK retry. Logs exclude credentials/provider bodies.
Cloud top-level TOML settings become environment variables; `.env` precedence
is unchanged, and native OIDC settings alone are read through `st.secrets`.
