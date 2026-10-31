# 🌍 Trip Planner AI Agent

An intelligent travel planning application that combines large language models, real-time geographic data, Retrieval-Augmented Generation (RAG), and agentic workflows to generate personalized travel itineraries.

Built as the capstone project for the Codecademy AI Engineer Certification, this application demonstrates production-focused AI engineering practices including tool calling, external API integration, state persistence, interactive visualizations, feedback collection, and reliable AI output validation.

---

## 🚀 Project Overview

Trip Planner AI Agent helps travelers create customized itineraries by combining:

- OpenAI Responses API with function calling
- OpenStreetMap geospatial services
- Overpass live Points of Interest (POI) retrieval
- Optional Wikivoyage Retrieval-Augmented Generation (RAG)
- Interactive map visualization with PyDeck
- Streamlit-based user interface
- Persistent session and itinerary storage
- User feedback collection and recommendation refinement

Unlike simple chatbot applications, this project implements a true agent architecture capable of reasoning, selecting tools, gathering information, validating results, and generating structured travel recommendations.

---

## 🎯 Project Objectives

This project was designed to demonstrate the following AI Engineering competencies:

### Agentic AI Systems

- OpenAI Responses API integration
- Function calling and tool orchestration
- Multi-step reasoning workflows
- Agent execution tracing and debugging

### Real-Time Data Integration

- Nominatim geocoding
- Overpass POI retrieval
- Optional Wikivoyage RAG pipeline
- API reliability and error recovery

### Product Engineering

- Streamlit web application
- User session management
- Persistent state storage
- Feedback-driven recommendation improvements

### Data Visualization

- Interactive maps
- POI plotting
- Geographic itinerary visualization
- Travel route exploration

---

## 🏗️ System Architecture

```text
┌─────────────────────┐
│     Streamlit UI    │
└──────────┬──────────┘
           │
           ▼
┌─────────────────────┐
│   AI Travel Agent   │
│ OpenAI Responses API│
└──────────┬──────────┘
           │
           ▼
 ┌─────────┼─────────┐
 ▼         ▼         ▼

Geocoder   POI Tool   Travel Guide Tool
(Nominatim)(Overpass) (Wikivoyage RAG)

 └─────────┼─────────┘
           ▼
   Structured Itinerary
           ▼
      PyDeck Maps
           ▼
 Persistent Storage
```

---

## ✨ Core Features

### AI Agent

- Natural language trip planning
- Tool selection through function calling
- Multi-step travel reasoning
- Structured itinerary generation

### Location Intelligence

- Geocoding cities and destinations
- Discovering nearby attractions
- Retrieving restaurants and landmarks
- Real-time POI recommendations

### RAG Enhancement

- Wikivoyage content retrieval
- Travel-specific contextual grounding
- Reduced hallucinations
- Better destination awareness

### Interactive Visualization

- PyDeck-powered maps
- Destination markers
- Attraction plotting
- Geographic itinerary display

### Persistence

- Session state management
- Saved itineraries
- User preference retention
- Feedback history

### Reliability

- API request retries
- Rate limiting protection
- Structured validation
- Graceful error handling

---

## 🛠️ Technology Stack

### AI & Machine Learning

- OpenAI Responses API
- Function Calling
- Retrieval-Augmented Generation (RAG)
- Prompt Engineering

### Backend

- Python 3.14
- Requests
- JSON Persistence

### Frontend

- Streamlit
- PyDeck

### Data Sources

- Nominatim API
- Overpass API
- Wikivoyage API (Optional)

### Data Processing

- NumPy
- Pandas
- Scikit-Learn

---

## 📂 Project Structure

```text
trip-planner/
│
├── app.py
│
├── data/
│   ├── app_state.json
│   └── feedback.jsonl
│
├── utils/
│   ├── geocoding.py
│   ├── poi_search.py
│   ├── rag.py
│   ├── persistence.py
│   └── validation.py
│
├── README.md
├── PRODUCT_REQUIREMENTS.md
├── requirements.txt
└── .env
```

---

## ⚙️ Installation

### Clone Repository

```bash
git clone https://github.com/yourusername/trip-planner-ai-agent.git

cd trip-planner-ai-agent
```

### Create Virtual Environment

```bash
python -m venv .venv
```

Windows:

```bash
source .venv/Scripts/activate
```

Linux/Mac:

```bash
source .venv/bin/activate
```

### Install Dependencies

```bash
pip install streamlit openai pydeck requests scikit-learn numpy pandas
```

---

## 🔑 API Configuration

### Environment Variables

Create a `.env` file:

```env
OPENAI_API_KEY=your_openai_api_key
```

Never commit secrets to source control.

Add the following to `.gitignore`:

```gitignore
.env
.streamlit/secrets.toml
```

---

## ▶️ Running the Application

```bash
streamlit run app.py
```

The application will launch in your browser by default.

---

## 📸 Example Use Cases

### Family Vacation

> Plan a 4-day family trip to Seattle focused on museums, parks, and kid-friendly attractions.

### Cultural Exploration

> Create a 3-day itinerary for Kyoto emphasizing temples, traditional architecture, and local cuisine.

### Food Tourism

> Build a weekend itinerary around highly-rated restaurants and food markets in Portland.

---

## 🧠 AI Engineering Concepts Demonstrated

This project showcases:

- Agentic workflows
- OpenAI function calling
- Tool orchestration
- Retrieval-Augmented Generation
- External API integration
- Geospatial data processing
- State management
- User feedback loops
- Output validation
- Error handling and retry logic
- Production AI architecture

---

## 📈 Future Enhancements

- Multi-agent itinerary planning
- Hotel integration
- Flight search integration
- Cost optimization recommendations
- Personalized recommendation learning
- Weather-aware itinerary generation
- Vector database powered travel memory
- LangGraph workflow orchestration
- Multi-user authentication

---

## 👨‍💻 Author

Nicolas Figueroa (Nomadant)

AI Engineer Certification Capstone Project

Focused on demonstrating practical AI engineering skills through the design and implementation of a production-oriented intelligent travel planning platform.

---