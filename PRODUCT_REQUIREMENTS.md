# Product Requirements Document (PRD)

# Trip Planner AI Agent

Version: 1.0

---

# 1. Product Vision

Build a production-ready AI-powered trip planning platform capable of generating personalized travel itineraries through agentic AI workflows, real-time geographic data retrieval, and retrieval-augmented travel knowledge.

The system must demonstrate modern AI engineering capabilities beyond a traditional chatbot.

---

# 2. Success Criteria

The solution shall:

- Accept natural language trip requests
- Generate personalized itineraries
- Retrieve live destination information
- Display itineraries visually on maps
- Persist user-generated plans
- Collect user feedback
- Use tool calling to retrieve information
- Reliably handle errors and API failures

---

# 3. Functional Requirements

## FR-001 User Trip Request

The system shall allow the user to enter a natural language travel planning request.

Examples:

- Weekend in Portland
- Family vacation in Seattle
- Five-day trip to Kyoto

---

## FR-002 Agent-Based Planning

The AI agent shall determine what information is necessary to fulfill the request.

The agent shall:

- Analyze user intent
- Select tools
- Execute tool calls
- Combine tool outputs
- Produce final recommendations

---

## FR-003 Function Calling

The system shall use OpenAI function calling.

Supported tool categories:

- Geocoding
- POI retrieval
- Travel guide retrieval
- Persistence operations

---

## FR-004 Geocoding

The system shall convert user-supplied destinations into geographic coordinates through Nominatim.

Outputs:

- Latitude
- Longitude
- Country
- City

---

## FR-005 POI Retrieval

The system shall retrieve live Points of Interest using the Geoapify Places API
(OpenStreetMap-based data), authenticated with a locally configured
`GEOAPIFY_API_KEY` and displaying the required Geoapify/OpenStreetMap
attribution. Overpass was removed after repeated timeouts made planning slow and
unreliable. Each place includes its name, category, address, and coordinates;
the Nearby places table shows name, category, and address.

For multi-region trips, POIs retrieved around each geocoded regional base are
merged and deduplicated.

Supported POI types:

- Restaurants
- Cafes
- Museums
- Attractions
- Landmarks
- Hotels (optional)
- Parks

---

## FR-006 RAG Travel Retrieval

The application shall optionally retrieve travel context from Wikivoyage.

The retrieved content must be used as grounding context for itinerary generation.

When enabled and configured, retrieval shall chunk destination articles, embed
them with a local semantic model, search normalized vectors by cosine
similarity, and return bounded relevant passages with Wikivoyage source URLs.
No external vector database or OpenAI embedding calls are required. Missing
weights or guide failures shall remain explicit, non-fatal outcomes.

---

## FR-007 Personalized Recommendations

The system shall generate recommendations based on:

- Destination
- Trip duration
- User interests
- Travel style
- Budget (if provided)
- Optional start date and additional requests

Requirements in the additional request are hard constraints. When a start date
is given, the application computes each day's calendar date in code, labels
widely observed holidays (Christmas Eve/Day, New Year's Eve/Day), and pins every
additional-request clause that names a single trip date (for example
"December 24 San Jose christmas dinner", whether separated by commas,
semicolons, or new lines) to the matching day number. It also gives the model
the free days between commitments with a travel radius (short gaps stay within
about 1.5 hours of the commitment towns; distant regions only in gaps of 3+
days), and requires stated driving times for every travel leg. After
generation, the planner verifies each commitment appears on its day; if not, it
requests one model repair and rejects the result if commitments still fail,
preserving the previous plan. It shall not disguise contradictory travel by
simply inserting a commitment into an invalid schedule.
The UI and PDF show the date beside each day.

Users can select number of days, an inclusive date range, or both. A valid date
range takes precedence; the number of days is synchronized and the adjustment
is displayed. Reject reversed, incomplete, or longer-than-30-day ranges.

---

## FR-008 Itinerary Generation

The system shall generate:

- Daily schedule
- Attraction recommendations
- Dining recommendations
- Activity recommendations

Each day shall include ordered location names and nullable estimated daily
costs in the trip currency. Estimates must be distinguished from actual prices.
Users may explicitly generate two alternatives only when enabled in sidebar
configuration; this action makes additional model calls.

---

## FR-009 Structured Output

Generated itineraries shall follow a predefined format.

Minimum sections:

- Overview
- Daily Activities
- Recommended Attractions
- Dining Suggestions
- Travel Notes

---

## FR-010 Interactive Map

The platform shall display itinerary locations using PyDeck.

The map shall:

- Center on destination
- Show itinerary locations and regional bases
- Fit the initial zoom so every plotted location is visible
- Support zoom and pan
- Use meter-based dots with pixel visibility limits and smooth scroll zoom
- Show a schematic PathLayer in temporal visit order, not a road route
- Resolve named beach destinations to verified coordinates; report unresolved locations
- Offer light/dark styles and entire-trip/single-day filtering

Filters shall not clear or regenerate the underlying itinerary.

---

## FR-011 Session State

The application shall maintain session state while the user remains active.

Stored information:

- Current itinerary
- Selected itinerary (by plan ID; a newly generated or refined plan is always
  shown immediately)
- User preferences
- Non-secret API settings (credentials are resolved server-side only)

---

## FR-012 Persistence

With optional sign-in, the application shall privately save/load:

- Generated itineraries
- User feedback

Use local PostgreSQL for development/testing and Supabase PostgreSQL for
deployment. Identity comes from a trusted OIDC provider; private records are
scoped to verified issuer/subject identities. Anonymous plans remain in the
browser session and are downloadable without sign-in.

Legacy app_state.json/feedback.jsonl remain intact but are not shared across
public user sessions. Users may privately export/import individual JSON plans.

Users shall also be able to download the displayed itinerary as a PDF report
(overview, daily plan, travel notes, and nearby places with addresses).

---

## FR-013 Feedback Collection

Users shall be able to provide:

- Positive feedback
- Negative feedback
- Free-text comments

POI votes require sign-in and affect candidate ranking by +0.25 per upvote
and -0.35 per downvote. Count only the latest vote per actor/POI across plans,
not repeated submissions. Show permanent feedback statistics at the bottom
of the interface.

Written feedback receives model review for actionable, supported improvements.
Reject manipulation and non-actionable complaints, not legitimate negative
feedback based on tone. The model cannot prove arbitrary factual complaints
false. All learned instructions require administrator approval; only bounded
approved advisory rules may influence future requests, never core safety or
current-user constraints.

---

## FR-014 Itinerary Refinement

Users shall be able to request itinerary modifications.

Examples:

- Add museums
- Reduce walking distance
- Replace attractions

Refinement keeps the original additional request and start date, so fixed
commitments still apply after a change.

For explicit single-day regeneration, instruct the model to copy all other
days unchanged and enforce this in code. Show before/after comparisons when
enabled. Allow side-by-side comparison of existing/saved/session trip options.

## FR-015 Interface Configuration and Budget Tracking

Sidebar controls enable/hide nearby places, maps, notes, traces, and budget
reporting; enable comparison and optional alternative generation. POI tables
include safe information links (official site when available, otherwise an OSM
location link). Expenses are manually recorded by category/day in one trip
currency, using exact decimal arithmetic. Show spent, remaining, and separately
labeled model-estimated totals. Saved plans preserve expenses across refinement.

---

# 4. Non-Functional Requirements

## NFR-001 Performance

Typical itinerary generation shall complete within 30 seconds. Long multi-region
trips (for example, 19 days across several regions) may take longer; the agent
tool budget (6 rounds, 16 tool calls) and a 90-second OpenAI request timeout
bound the total time. When the tool budget is reached, the agent shall produce
the itinerary from the data already gathered rather than fail.

While a plan is generated or refined, the UI shall show rotating, lighthearted
progress messages (20 variants) in a single status element that is relabeled in
place, without flicker.

---

## NFR-002 Reliability

The application shall gracefully recover from:

- API failures
- Network interruptions
- Invalid destinations
- Empty responses

---

## NFR-003 Error Handling

The system shall provide clear user-facing messages when failures occur.

---

## NFR-004 Validation

All AI outputs shall be validated before presentation.

Validation includes:

- Required fields
- Destination consistency
- Coordinate availability

---

## NFR-005 Security

API keys shall never be stored in source control.

Supported mechanisms:

- Environment variables
- `.env` files (first `trip-planner/.env`, then launch directory and parents;
  process environment is the fallback)

API credentials shall not be entered or validated through a sidebar or stored
in browser session state. Cloud administrators may convey top-level settings
through gitignored secrets.toml/Cloud Secrets, which Streamlit exports to the
environment; application key lookup still uses .env/environment precedence.
Native OIDC settings are read through Streamlit secrets. Never commit the real
TOML file, Supabase service-role keys, database URIs, or user exports.

---

## NFR-006 Rate Limiting

The application shall respect:

- Nominatim rate limits
- Geoapify rate limits and daily free-tier quota
- OpenAI API quotas

---

## NFR-007 Logging

The system shall log:

- Tool executions
- API failures
- Validation errors
- Agent reasoning events

---

## NFR-008 Maintainability

Application components shall be modular.

Recommended modules:

- Agent
- Tools
- Persistence
- Validation
- UI

---

# 5. Technical Requirements

## Development Environment

- Python 3.14.6
- Streamlit 1.66+
- OpenAI SDK 3.x
- Requests
- NumPy
- Pandas
- Scikit-Learn
- PyDeck
- fpdf2 (PDF export)
- Sentence Transformers (local semantic embeddings)
- psycopg (local PostgreSQL)
- Streamlit OIDC authentication extra

---

## APIs

Required:

- OpenAI Responses API
- Nominatim

Required for production functionality:

- Geoapify Places (`GEOAPIFY_API_KEY`)

Optional:

- Wikivoyage

---

## Storage

PostgreSQL JSONB for private plans and SQL feedback/guidance tables.
Local PostgreSQL is used for development/testing; Supabase for cloud hosting.
JSON exports and bounded local JSON logs remain supported.

---

# 6. Acceptance Criteria

A release shall be considered complete when:

✅ User can submit trip requests

✅ Agent performs function calling

✅ Geocoding successfully resolves destinations

✅ POIs are retrieved

✅ Itinerary is generated

✅ Interactive map renders

✅ State persistence works

✅ Feedback is captured

✅ Error handling functions correctly

✅ API keys are securely managed

✅ README documentation is complete

✅ Application can be executed via:

```bash
streamlit run app.py
```

---

# 7. Stretch Goals

- Multi-agent planning architecture
- Weather integration
- Hotel recommendation engine
- Flight recommendation engine
- Verified supplier pricing beyond the current model estimates
- Hosted vector database memory beyond the current local semantic index
- LangGraph workflow support
- OpenTelemetry tracing
- Deployment to Streamlit Cloud