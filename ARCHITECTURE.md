# Architecture Document

# Trip Planner AI Agent

Version: 1.0

---

# 1. Purpose

The Trip Planner AI Agent is a production-oriented AI application that generates personalized travel itineraries using an agentic workflow built on OpenAI function calling, real-time geospatial APIs, Retrieval-Augmented Generation (RAG), and persistent application state.

The system combines AI reasoning, external tools, live travel data, and user feedback into a unified travel planning experience.

---

# 2. Architectural Goals

The architecture is designed to satisfy the following goals:

- Modular and maintainable
- Production-ready
- Extensible tool framework
- Reliable external API integrations
- Safe and validated AI outputs
- Persistent user experience
- Observable agent behavior

---

# 3. High-Level Architecture

```text
┌─────────────────────────────────────────┐
│               Streamlit UI              │
└─────────────────┬───────────────────────┘
                  │
                  ▼
┌─────────────────────────────────────────┐
│            AI Agent Controller          │
│      OpenAI Responses API Client        │
└─────────────────┬───────────────────────┘
                  │
       Function Calling Layer
                  │
       ┌──────────┼──────────┐
       ▼          ▼          ▼

┌──────────┐ ┌──────────┐ ┌──────────────┐
│Geocoding │ │POI Search│ │Travel Guide │
│  Tool    │ │   Tool   │ │  RAG Tool   │
└────┬─────┘ └────┬─────┘ └──────┬──────┘
     │            │              │
     ▼            ▼              ▼

 Nominatim    Overpass API   Wikivoyage

       └──────────┼───────────┘
                  ▼

       Structured Travel Context

                  ▼

┌─────────────────────────────────────────┐
│      Validation & Post Processing       │
└─────────────────┬───────────────────────┘
                  ▼

┌─────────────────────────────────────────┐
│         Itinerary Generation            │
└─────────────────┬───────────────────────┘
                  ▼

┌─────────────────────────────────────────┐
│      Visualization Layer (PyDeck)       │
└─────────────────┬───────────────────────┘
                  ▼

┌─────────────────────────────────────────┐
│           Persistence Layer             │
│ app_state.json / feedback.jsonl         │
└─────────────────────────────────────────┘
```

---

# 4. Component Architecture

## 4.1 Streamlit UI Layer

Responsibilities:

- Collect user inputs
- Display itineraries
- Visualize maps
- Manage session state
- Capture feedback

Inputs:

- Destination
- Duration
- Interests
- Budget
- User refinements

Outputs:

- Travel itinerary
- Interactive map
- Feedback collection interface

---

## 4.2 Agent Controller

Responsibilities:

- Manage conversations
- Build prompts
- Call OpenAI Responses API
- Execute tool calls
- Merge results

Key Features:

- Function calling
- Multi-step reasoning
- Tool orchestration
- Error management

---

## 4.3 Tool Layer

The agent accesses external systems through tools.

### Geocoding Tool

Purpose:

Convert destination names into coordinates.

Service:

- OpenStreetMap Nominatim

Input:

```json
{
  "city": "Seattle"
}
```

Output:

```json
{
  "latitude": 47.6062,
  "longitude": -122.3321
}
```

---

### POI Search Tool

Purpose:

Retrieve nearby attractions.

Service:

- Overpass API

Categories:

- Museum
- Restaurant
- Park
- Cafe
- Landmark

---

### Travel Guide RAG Tool

Purpose:

Retrieve travel-specific context.

Source:

- Wikivoyage

Function:

Provides destination background information used to ground itinerary generation.

---

# 5. Data Flow

## Initial Request

```text
User Request
      ↓
Agent Analysis
      ↓
Destination Extraction
      ↓
Geocode Destination
      ↓
Search POIs
      ↓
Retrieve Wikivoyage Context
      ↓
Validate Tool Outputs
      ↓
Generate Itinerary
      ↓
Render Results
```

---

# 6. Agent Reasoning Workflow

Example:

User:

"Plan a 3-day family-friendly trip to Seattle."

Workflow:

1. Parse intent
2. Detect destination
3. Detect family preference
4. Call geocoding function
5. Retrieve attractions
6. Filter family-friendly locations
7. Generate itinerary
8. Display itinerary
9. Save session data

---

# 7. State Management

## Session State

Stored in Streamlit Session State:

```python
st.session_state
```

Tracked Values:

- Chat history
- Current itinerary
- User preferences
- Map settings
- API configuration

---

## Persistent State

Stored locally:

### app_state.json

Contains:

- Active itinerary
- User preferences
- Saved destinations

### feedback.jsonl

Contains:

- Ratings
- Comments
- Timestamps

---

# 8. Output Validation Strategy

AI-generated outputs must be validated before rendering.

Checks:

- Destination exists
- Coordinates available
- POIs returned correctly
- Required itinerary sections present

Required Sections:

- Overview
- Daily Schedule
- Attractions
- Dining
- Notes

---

# 9. Error Handling

## Geocoding Failure

Response:

- Display user-friendly error
- Suggest destination correction

## Overpass Timeout

Response:

- Retry with exponential backoff
- Fall back gracefully

## Wikivoyage Failure

Response:

- Continue itinerary generation
- Disable RAG contribution

## OpenAI Failure

Response:

- Surface meaningful error message
- Preserve application state

---

# 10. Security Architecture

## API Credentials

Supported Sources:

- Environment variables
- Streamlit Secrets
- User session input

Never:

- Store in source control
- Hardcode in source files

---

# 11. Logging Strategy

Events Logged:

- Tool execution
- API failures
- User feedback
- Validation failures

Potential Future Upgrade:

- Structured logging
- OpenTelemetry
- LangSmith Tracing

---

# 12. Future Architecture Enhancements

## Multi-Agent Architecture

Potential Agents:

- Destination Planner
- Dining Specialist
- Budget Planner
- Logistics Planner

## Vector Database

Potential Storage:

- Chroma
- Pinecone
- Weaviate

Purpose:

Long-term travel memory.

## LangGraph

Future migration of orchestration layer to graph-based workflows.

---

# 13. Deployment Architecture

Initial Deployment:

```text
Local Machine
      ↓
Streamlit Application
      ↓
External APIs
```

Future Deployment:

```text
Streamlit Cloud
      ↓
OpenAI API
Overpass API
Nominatim
Wikivoyage
```

---

# 14. Design Principles

- Simplicity over complexity
- Real-world API integrations
- Observable agent behavior
- Reusable tooling
- Reliable outputs
- User-centric experience
- Production-oriented engineering practices