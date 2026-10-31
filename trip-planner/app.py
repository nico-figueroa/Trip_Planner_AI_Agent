"""Streamlit interface for the AI Trip Planner."""

from __future__ import annotations

import copy
import logging
import uuid
from datetime import datetime, timezone
from typing import Any

import pydeck as pdk
import streamlit as st

from utils.agent import TripPlannerAgent
from utils.logging_config import configure_logging
from utils.openai_agent import PlanningError
from utils.openai_client import (
    MissingAPIKeyError,
    get_api_key,
)
from utils.persistence import append_feedback, load_state, save_state

configure_logging()
logger = logging.getLogger("utils.app")
MAX_SAVED_ITINERARIES = 20

st.set_page_config(
    page_title="AI Trip Planner",
    page_icon="🌍",
    layout="wide",
)


def _format_plan_label(plan: dict[str, Any]) -> str:
    destination = str(plan.get("destination") or "Trip")
    created = str(plan.get("created_at", ""))[:10]
    return f"{destination} — {created or 'saved plan'}"


def _render_map(plan: dict[str, Any]) -> None:
    location = plan.get("location")
    if not isinstance(location, dict):
        location = {}
    latitude = location.get("latitude")
    longitude = location.get("longitude")
    try:
        latitude = float(latitude)
        longitude = float(longitude)
    except (TypeError, ValueError):
        st.info("Map coordinates are not available for this itinerary.")
        return
    if not -90 <= latitude <= 90 or not -180 <= longitude <= 180:
        st.info("Map coordinates are not available for this itinerary.")
        return

    itinerary = plan.get("itinerary")
    if not isinstance(itinerary, dict):
        itinerary = {}
    daily_plan = itinerary.get("daily_plan", [])
    if not isinstance(daily_plan, list):
        daily_plan = []
    activity_text = " ".join(
        activity
        for day in daily_plan
        if isinstance(day, dict)
        for activity in day.get("activities", [])
        if isinstance(activity, str)
    ).casefold()
    points = [
        {
            "name": location.get("city") or plan.get("destination", "Destination"),
            "category": "Destination",
            "latitude": latitude,
            "longitude": longitude,
            "radius": 220,
            "color": [230, 82, 70],
        }
    ]
    for poi in plan.get("pois", []):
        if not isinstance(poi, dict):
            continue
        poi_name = str(poi.get("name") or "")
        is_itinerary_stop = bool(poi_name and poi_name.casefold() in activity_text)
        try:
            poi_latitude = float(poi.get("latitude"))
            poi_longitude = float(poi.get("longitude"))
        except (TypeError, ValueError):
            continue
        if not -90 <= poi_latitude <= 90 or not -180 <= poi_longitude <= 180:
            continue
        points.append(
            {
                "name": poi_name or "Point of interest",
                "category": (
                    "Itinerary stop"
                    if is_itinerary_stop
                    else poi.get("category", "Point of interest")
                ),
                "latitude": poi_latitude,
                "longitude": poi_longitude,
                "radius": 130 if is_itinerary_stop else 90,
                "color": [244, 166, 35] if is_itinerary_stop else [38, 133, 153],
            }
        )

    points = [
        point
        for point in points
        if point["latitude"] is not None and point["longitude"] is not None
    ]
    layer = pdk.Layer(
        "ScatterplotLayer",
        data=points,
        get_position="[longitude, latitude]",
        get_fill_color="color",
        get_radius="radius",
        radius_min_pixels=6,
        radius_max_pixels=16,
        pickable=True,
    )
    deck = pdk.Deck(
        layers=[layer],
        initial_view_state=pdk.ViewState(
            latitude=latitude,
            longitude=longitude,
            zoom=12,
            pitch=20,
        ),
        map_style="https://basemaps.cartocdn.com/gl/positron-gl-style/style.json",
        tooltip={"text": "{name}\n{category}"},
    )
    st.pydeck_chart(deck, height=460, alt="Map of the destination and itinerary places")


def _render_plan(plan: dict[str, Any]) -> None:
    itinerary = plan.get("itinerary", {})
    if not isinstance(itinerary, dict):
        st.warning("This saved itinerary has an unsupported format.")
        return
    st.subheader(itinerary.get("destination", plan.get("destination", "Itinerary")))
    st.write(itinerary.get("overview", ""))

    daily_plan = itinerary.get("daily_plan", [])
    if not isinstance(daily_plan, list):
        daily_plan = []
    for day in daily_plan:
        if not isinstance(day, dict):
            continue
        with st.expander(
            f"Day {day.get('day', '?')}: {day.get('title', 'Activities')}",
            expanded=day.get("day") == 1,
        ):
            activities = day.get("activities", [])
            if not isinstance(activities, list):
                activities = []
            for activity in activities:
                if not isinstance(activity, str):
                    continue
                st.markdown(f"- {activity}")

    travel_notes = itinerary.get("travel_notes")
    if travel_notes:
        with st.expander("Travel notes"):
            st.write(travel_notes)

    pois = plan.get("pois", [])
    if not isinstance(pois, list):
        pois = []
    st.subheader("Nearby places")
    if pois:
        st.dataframe(
            pois,
            hide_index=True,
            alt="Retrieved points of interest near the destination",
        )
        if any(isinstance(poi, dict) and poi.get("source") == "Geoapify" for poi in pois):
            st.caption(
                "Overpass was unavailable. Powered by "
                "[Geoapify](https://www.geoapify.com/) using "
                "[OpenStreetMap](https://www.openstreetmap.org/copyright) data."
            )
    else:
        st.info("No nearby places were returned. The map still shows the destination.")

    st.subheader("Map")
    _render_map(plan)
    st.caption(
        "Map data: [OpenStreetMap contributors](https://www.openstreetmap.org/copyright)."
    )

    trace = plan.get("trace", [])
    if not isinstance(trace, list):
        trace = []
    with st.expander("Agent execution trace"):
        if not trace:
            st.caption("No tool calls were recorded for this saved itinerary.")
        for index, event in enumerate(trace, start=1):
            if not isinstance(event, dict):
                continue
            outcome = "completed" if event.get("success") else "unavailable"
            st.markdown(f"**{index}. {event.get('tool', 'Agent step')}** — {outcome}")
            if event.get("arguments"):
                st.json({"arguments": event["arguments"]})
            if event.get("success"):
                st.json({"result": event.get("result")})
            else:
                st.warning(event.get("error", "The tool could not be completed."))


if "planner_state" not in st.session_state:
    st.session_state["planner_state"] = load_state()
if "current_plan" not in st.session_state:
    active_plan = st.session_state["planner_state"].get("active_itinerary")
    st.session_state["current_plan"] = (
        active_plan if isinstance(active_plan, dict) else None
    )

st.title("AI Trip Planner")
st.markdown(
    "Create a grounded travel plan with live OpenStreetMap data and an AI planning agent."
)

with st.form("trip_request"):
    st.subheader("Plan a trip")
    first_row = st.columns([2, 1])
    destination = first_row[0].text_input("Destination", placeholder="Kyoto, Japan")
    duration = first_row[1].number_input(
        "Duration (days)",
        min_value=1,
        max_value=30,
        value=3,
        step=1,
    )
    interests = st.text_input(
        "Interests",
        placeholder="Food, museums, parks, architecture",
        max_chars=500,
    )
    second_row = st.columns(2)
    budget = second_row[0].text_input(
        "Budget (optional)",
        placeholder="Moderate, or $150 per day",
        max_chars=200,
    )
    travel_style = second_row[1].text_input(
        "Travel style (optional)",
        placeholder="Family-friendly, relaxed pace",
        max_chars=200,
    )
    additional_request = st.text_area(
        "Additional request",
        placeholder="Plan a weekend, avoid long walks, include local food...",
        height=90,
        max_chars=1000,
    )
    generate = st.form_submit_button("Generate itinerary", width="stretch")

if generate:
    if not get_api_key():
        logger.warning("Trip generation blocked: OPENAI_API_KEY is not configured.")
        st.error(
            "Configure OPENAI_API_KEY in a .env file or the process environment "
            "before generating a plan."
        )
    else:
        try:
            with st.spinner("Checking the destination and planning your trip..."):
                result = TripPlannerAgent().generate_trip_plan(
                    destination=destination,
                    duration=int(duration),
                    interests=interests,
                    budget=budget,
                    travel_style=travel_style,
                    additional_request=additional_request,
                )
                result["id"] = uuid.uuid4().hex
                result["created_at"] = datetime.now(timezone.utc).isoformat()
                state = copy.deepcopy(st.session_state["planner_state"])
                state["active_itinerary"] = result
                st.session_state["planner_state"] = state
                st.session_state["current_plan"] = result
                save_state(state)
            st.success("Itinerary generated and saved as the active plan.")
        except (MissingAPIKeyError, PlanningError, ValueError, OSError) as error:
            logger.warning(
                "Trip planning request could not be completed (%s).",
                type(error).__name__,
            )
            st.error(str(error))

state = st.session_state["planner_state"]
saved_plans = state.get("saved_itineraries", [])
if not isinstance(saved_plans, list):
    saved_plans = []
plan_options: list[dict[str, Any]] = []
active_plan = state.get("active_itinerary")
if isinstance(active_plan, dict) and active_plan.get("itinerary"):
    plan_options.append(active_plan)
plan_options.extend(
    plan for plan in saved_plans if isinstance(plan, dict) and plan.get("itinerary")
)

displayed_plan: dict[str, Any] | None = st.session_state.get("current_plan")
if plan_options:
    selected_index = st.selectbox(
        "Current and saved itineraries",
        options=list(range(len(plan_options))),
        index=0,
        format_func=lambda index: _format_plan_label(plan_options[index]),
        key="selected_plan",
    )
    displayed_plan = plan_options[selected_index]

if displayed_plan:
    st.divider()
    _render_plan(displayed_plan)

    if st.button(
        "Save itinerary",
        key="save_itinerary",
        icon=":material/bookmark_add:",
    ):
        state = copy.deepcopy(st.session_state["planner_state"])
        saved = state.setdefault("saved_itineraries", [])
        if not isinstance(saved, list):
            saved = []
            state["saved_itineraries"] = saved
        saved = [item for item in saved if isinstance(item, dict)]
        state["saved_itineraries"] = saved
        plan_id = displayed_plan.get("id")
        if not any(item.get("id") == plan_id for item in saved):
            saved.insert(0, copy.deepcopy(displayed_plan))
            del saved[MAX_SAVED_ITINERARIES:]
            st.session_state["planner_state"] = state
            try:
                save_state(state)
                st.success("Itinerary added to saved plans.")
            except (OSError, ValueError):
                st.error(
                    "The itinerary could not be saved. "
                    "It remains available for this session."
                )
        else:
            st.info("This itinerary is already saved.")

    with st.form("refine_itinerary"):
        st.subheader("Refine this itinerary")
        refinement = st.text_area(
            "What would you like to change?",
            placeholder="Add more museums, reduce walking, or replace day two...",
            height=90,
        )
        refine = st.form_submit_button("Refine itinerary", width="stretch")

    if refine:
        if not refinement.strip():
            st.warning("Describe the change you want before refining.")
        elif not get_api_key():
            logger.warning("Itinerary refinement blocked: OPENAI_API_KEY is not configured.")
            st.error(
                "Configure OPENAI_API_KEY in a .env file or the process environment "
                "before refining."
            )
        else:
            try:
                current = displayed_plan.get("itinerary", {})
                with st.spinner("Updating your itinerary..."):
                    result = TripPlannerAgent().generate_trip_plan(
                        destination=displayed_plan.get("destination", destination),
                        duration=int(displayed_plan.get("duration", duration)),
                        interests=displayed_plan.get("interests", interests),
                        budget=displayed_plan.get("budget", budget),
                        travel_style=displayed_plan.get("travel_style", travel_style),
                        additional_request=refinement,
                        existing_itinerary=current,
                    )
                    result["id"] = uuid.uuid4().hex
                    result["created_at"] = datetime.now(timezone.utc).isoformat()
                    state = copy.deepcopy(st.session_state["planner_state"])
                    state["active_itinerary"] = result
                    st.session_state["planner_state"] = state
                    st.session_state["current_plan"] = result
                    save_state(state)
                    st.session_state.pop("selected_plan", None)
                st.success("Itinerary refined and saved as the active plan.")
                st.rerun()
            except (MissingAPIKeyError, PlanningError, ValueError, OSError) as error:
                logger.warning("Itinerary refinement failed (%s).", type(error).__name__)
                st.error(str(error))

    with st.form("trip_feedback"):
        st.subheader("Feedback")
        rating = st.radio(
            "Was this itinerary helpful?",
            options=["Positive", "Negative"],
            horizontal=True,
        )
        comment = st.text_area(
            "Comments (optional)",
            max_chars=2000,
            placeholder="What worked well or should improve?",
        )
        submit_feedback = st.form_submit_button("Submit feedback")

    if submit_feedback:
        try:
            append_feedback(
                {
                    "created_at": datetime.now(timezone.utc).isoformat(),
                    "destination": displayed_plan.get("destination", ""),
                    "rating": rating.lower(),
                    "comment": comment.strip(),
                }
            )
            st.success("Thank you. Your feedback was saved.")
        except OSError:
            st.error("Feedback could not be saved. Please try again.")

legacy_state = state.get("destination")
if legacy_state and not plan_options:
    with st.expander("Previous itinerary data"):
        st.caption("This plan uses the earlier saved format.")
        st.json(state)
