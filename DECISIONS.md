# Engineering Decision Log

# Trip Planner AI Agent

Version: 1.0

---

# Purpose

This document captures the major architectural and engineering decisions made during the design and implementation of the Trip Planner AI Agent.

The goal is to explain not only what choices were made, but why they were made, including tradeoffs and future alternatives.

---

# ADR-001

## Use OpenAI Responses API Instead of Traditional Chat Completions

### Status

Accepted

### Context

The project requires:

- Tool calling
- Multi-step reasoning
- Structured outputs
- Agentic workflows

Traditional prompt-response interactions do not provide sufficient support for production agent behavior.

### Decision

Use the OpenAI Responses API as the primary model interface.

### Rationale

Benefits:

- Native function calling
- Better support for agents
- Easier tool orchestration
- Future compatibility with evolving OpenAI platform capabilities

### Tradeoffs

Cons:

- Slightly more complexity
- Additional learning curve

### Alternatives Considered

- Chat Completions API
- Pure prompt engineering without tools

### Outcome

Provides a stronger demonstration of modern AI engineering practices.

---

# ADR-002

## Use Function Calling Instead of Prompt-Based Tool Simulation

### Status

Accepted

### Context

Many chatbot implementations ask the model to pretend to use tools.

This approach is unreliable and difficult to validate.

### Decision

Use actual function calling.

### Rationale

Benefits:

- Deterministic tool execution
- Easier debugging
- Greater reliability
- Better production realism

### Alternatives Considered

- Prompt-only tool usage
- Manual tool selection

### Outcome

Real-world agent architecture.

---

# ADR-003

## Use Streamlit as User Interface Framework

### Status

Accepted

### Context

The project requires a web-based interface but does not require enterprise-scale frontend development.

### Decision

Use Streamlit.

### Rationale

Benefits:

- Rapid development
- Simple deployment
- Native Python workflow
- Strong support for data applications

### Alternatives Considered

- React
- Vue
- Flask templates
- FastAPI frontend

### Outcome

Faster delivery with less engineering overhead.

---

# ADR-004

## Use OpenStreetMap Instead of Commercial Mapping APIs

### Status

Accepted

### Context

The application requires:

- Geocoding
- Location data
- Points of Interest

### Decision

Use OpenStreetMap services.

Components:

- Nominatim
- Overpass

### Rationale

Benefits:

- No API costs
- No vendor lock-in
- Open ecosystem
- Educational value

### Alternatives Considered

- Google Maps API
- Mapbox
- Yelp API

### Outcome

Reduced operating costs and simpler deployment.

---

# ADR-005

## Use Overpass API for Points of Interest Retrieval

### Status

Accepted

### Context

The AI requires live location information to ground itinerary generation.

### Decision

Use Overpass API.

### Rationale

Benefits:

- Direct access to OpenStreetMap data
- No API key required
- Flexible query language

### Tradeoffs

- Slower than commercial providers
- Rate limits must be respected

### Outcome

Provides live attraction data without additional costs.

---

# ADR-006

## Make Wikivoyage Retrieval Optional

### Status

Accepted

### Context

Travel context improves itinerary quality but must not become a single point of failure.

### Decision

Use Wikivoyage as an optional enhancement.

### Rationale

Benefits:

- Improved recommendations
- Better contextual grounding
- Reduced hallucinations

If unavailable:

- System still functions

### Alternatives Considered

- Mandatory Wikivoyage retrieval
- No RAG component

### Outcome

More resilient architecture.

---

# ADR-007

## Use Retrieval-Augmented Generation

### Status

Accepted

### Context

Travel recommendations should be grounded in real source material whenever possible.

### Decision

Implement a lightweight RAG pipeline.

### Rationale

Benefits:

- Better accuracy
- Better destination awareness
- Reduced hallucinations

### Outcome

Improved recommendation quality.

---

# ADR-008

## Use Local JSON Storage Instead of a Database

### Status

Accepted

### Context

The project requires persistence but is intended as a portfolio-scale application.

### Decision

Store application state locally.

Files:

- app_state.json
- feedback.jsonl

### Rationale

Benefits:

- Simplicity
- Minimal infrastructure
- Easier development

### Alternatives Considered

- PostgreSQL
- Supabase
- MongoDB

### Outcome

Lower complexity while meeting requirements.

---

# ADR-009

## Validate AI Outputs Before Rendering

### Status

Accepted

### Context

LLM outputs may contain:

- Missing fields
- Invalid structure
- Hallucinated content

### Decision

Introduce output validation layer.

### Validation Rules

- Required sections present
- Coordinates valid
- Destination consistency
- Tool outputs available

### Outcome

Improved reliability and user trust.

---

# ADR-010

## Collect User Feedback Explicitly

### Status

Accepted

### Context

Travel quality is subjective.

The system requires a mechanism for measuring recommendation quality.

### Decision

Implement structured user feedback collection.

Feedback Types:

- Rating
- Positive feedback
- Negative feedback
- Free text comments

### Outcome

Improved evaluation capability.

---

# ADR-011

## Use PyDeck for Geographic Visualization

### Status

Accepted

### Context

Generated itineraries should include visual exploration of locations.

### Decision

Implement map-based visualization using PyDeck.

### Rationale

Benefits:

- Streamlit compatibility
- Interactive maps
- Geographic context

### Alternatives Considered

- Folium
- Leaflet
- Mapbox SDK

### Outcome

Improved user experience.

---

# ADR-012

## Design for Future LangGraph Migration

### Status

Accepted

### Context

Current project complexity does not require graph orchestration.

Future versions may include:

- Multiple agents
- Complex workflows
- Long-running planning sessions

### Decision

Keep agent orchestration modular.

### Outcome

Future migration path remains open.

---

# ADR-013

## Prioritize Explainability Over Maximum Automation

### Status

Accepted

### Context

Educational and portfolio projects benefit from transparent behavior.

### Decision

Expose:

- Tool execution
- Retrieved POIs
- Agent decisions
- Validation results

### Outcome

Improved debugging and demonstration value.

---

# Future Reconsiderations

The following decisions may change in future releases:

| Current | Future Candidate |
|----------|------------------|
| JSON Storage | PostgreSQL