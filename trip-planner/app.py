"""Streamlit interface for the AI Trip Planner."""

from __future__ import annotations

import copy
import logging
import math
import random
import re
import uuid
from concurrent.futures import ThreadPoolExecutor, wait
from datetime import date, datetime, timezone
from functools import partial
from typing import Any, Callable, TypeVar

import pydeck as pdk
import streamlit as st

from utils.agent import TripPlannerAgent
from utils.logging_config import configure_logging
from utils.openai_agent import PlanningError
from utils.openai_client import (
    MissingAPIKeyError,
    get_api_key,
)
from utils.pdf_report import build_itinerary_pdf, day_heading
from utils.persistence import append_feedback, load_state, save_state

configure_logging()
logger = logging.getLogger("utils.app")
MAX_SAVED_ITINERARIES = 20
PROGRESS_INTERVAL_SECONDS = 2.5
PROGRESS_MESSAGES = (
    "Calculating distances between gelato stops...",
    "Checking the weather (and packing an umbrella, just in case)...",
    "Asking for directions. We are definitely not lost...",
    "Consulting with the local tour guides...",
    "Folding the map the wrong way, twice...",
    "Negotiating with the hotel breakfast buffet...",
    "Teaching the GPS some local slang...",
    "Counting the steps to the nearest viewpoint...",
    "Bribing the pigeons for insider tips...",
    "Taste-testing the street food, purely for research...",
    "Double-checking the time zones...",
    "Practicing how to ask where the restroom is...",
    "Rolling socks to save suitcase space...",
    "Checking whether the museums have air conditioning...",
    "Looking for the shortcut the locals use...",
    "Comparing sunset spots with a very serious face...",
    "Reading every travel blog on the internet...",
    "Charging the camera batteries...",
    "Arguing with the itinerary about nap time...",
    "Convincing the souvenir shops to stay open late...",
)
T = TypeVar("T")

st.set_page_config(
    page_title="AI Trip Planner",
    page_icon="🌍",
    layout="wide",
)


def _format_plan_label(plan: dict[str, Any]) -> str:
    destination = str(plan.get("destination") or "Trip")
    duration = plan.get("duration")
    days = f"{duration} days, " if duration else ""
    created = str(plan.get("created_at", ""))[:16].replace("T", " ")
    return f"{destination} ({days}{created or 'saved plan'})"


def _plan_key(plan: dict[str, Any], position: int) -> str:
    """Return a stable selector value so a stale selection never shows another plan."""
    return str(plan.get("id") or f"plan-{position}")


def _plan_start_date(plan: dict[str, Any]) -> date | None:
    try:
        return date.fromisoformat(str(plan.get("start_date")))
    except ValueError:
        return None


def _run_with_progress(task: Callable[[], T]) -> T:
    """Run a blocking task in a worker thread while rotating playful status messages.

    The worker never calls Streamlit; only this script thread updates the page.
    """
    placeholder = st.empty()
    index = random.randrange(len(PROGRESS_MESSAGES))
    # One status element is relabeled in place; recreating spinners caused flicker.
    status = placeholder.status(PROGRESS_MESSAGES[index], state="running")
    try:
        with ThreadPoolExecutor(max_workers=1) as executor:
            future = executor.submit(task)
            while True:
                done, _ = wait([future], timeout=PROGRESS_INTERVAL_SECONDS)
                if done:
                    return future.result()
                index = (index + 1) % len(PROGRESS_MESSAGES)
                status.update(label=PROGRESS_MESSAGES[index])
    finally:
        placeholder.empty()


def _pdf_file_name(plan: dict[str, Any]) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", str(plan.get("destination", "")).casefold())
    return f"{slug.strip('-') or 'trip'}-itinerary.pdf"


def _map_view(points: list[dict[str, Any]]) -> pdk.ViewState:
    """Center the map and choose the closest zoom that keeps every point visible."""
    latitudes = [point["latitude"] for point in points]
    longitudes = [point["longitude"] for point in points]
    center_latitude = (min(latitudes) + max(latitudes)) / 2
    center_longitude = (min(longitudes) + max(longitudes)) / 2
    if len(points) == 1:
        return pdk.ViewState(latitude=center_latitude, longitude=center_longitude, zoom=12)
    # Web Mercator: one 256 px world tile spans 360 degrees at zoom 0. Fit the
    # bounding box inside roughly 600 x 380 px so markers are not on the edge.
    longitude_span = max(max(longitudes) - min(longitudes), 1e-4)
    latitude_span = max(max(latitudes) - min(latitudes), 1e-4)
    cos_latitude = max(math.cos(math.radians(center_latitude)), 0.1)
    scale = min(600 / longitude_span, 380 * cos_latitude / latitude_span)
    zoom = max(1.0, min(14.0, math.log2(scale * 360 / 256)))
    return pdk.ViewState(
        latitude=center_latitude,
        longitude=center_longitude,
        zoom=round(zoom, 2),
    )


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
    stops = plan.get("stops")
    for stop in stops if isinstance(stops, list) else []:
        if not isinstance(stop, dict):
            continue
        try:
            stop_latitude = float(stop.get("latitude"))
            stop_longitude = float(stop.get("longitude"))
        except (TypeError, ValueError):
            continue
        if -90 <= stop_latitude <= 90 and -180 <= stop_longitude <= 180:
            points.append(
                {
                    "name": str(stop.get("name") or "Regional base"),
                    "category": "Regional base",
                    "latitude": stop_latitude,
                    "longitude": stop_longitude,
                    "radius": 180,
                    "color": [176, 58, 146],
                }
            )
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
        initial_view_state=_map_view(points),
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
            day_heading(plan, day),
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
    places = [
        {
            "Name": poi.get("name", ""),
            "Category": poi.get("category", ""),
            "Address": poi.get("address") or "Address not available",
        }
        for poi in pois
        if isinstance(poi, dict)
    ]
    if places:
        st.dataframe(
            places,
            hide_index=True,
            alt="Retrieved points of interest with their addresses",
        )
        st.caption(
            "Places powered by [Geoapify](https://www.geoapify.com/) using "
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
    first_row = st.columns([2, 1, 1])
    destination = first_row[0].text_input("Destination", placeholder="Kyoto, Japan")
    duration = first_row[1].number_input(
        "Duration (days)",
        min_value=1,
        max_value=30,
        value=3,
        step=1,
    )
    start_date = first_row[2].date_input(
        "Start date (optional)",
        value=None,
        help="Lets the planner place date-specific plans on the right day.",
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
        placeholder="Dec 22: birthday party in San Jose; avoid long walks...",
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
            result = _run_with_progress(
                partial(
                    TripPlannerAgent().generate_trip_plan,
                    destination=destination,
                    duration=int(duration),
                    interests=interests,
                    budget=budget,
                    travel_style=travel_style,
                    additional_request=additional_request,
                    start_date=start_date,
                )
            )
            result["id"] = uuid.uuid4().hex
            result["created_at"] = datetime.now(timezone.utc).isoformat()
            state = copy.deepcopy(st.session_state["planner_state"])
            state["active_itinerary"] = result
            st.session_state["planner_state"] = state
            st.session_state["current_plan"] = result
            # Show the new plan even if the selector previously pointed at a saved one.
            st.session_state["selected_plan"] = result["id"]
            save_state(state)
            st.success("Itinerary generated and saved as the active plan.")
        except (MissingAPIKeyError, PlanningError, ValueError, OSError) as error:
            logger.warning(
                "Trip planning request could not be completed (%s): %s",
                type(error).__name__,
                error,
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
    plans_by_key = {
        _plan_key(plan, position): plan for position, plan in enumerate(plan_options)
    }
    if st.session_state.get("selected_plan") not in plans_by_key:
        st.session_state.pop("selected_plan", None)
    selected_key = st.selectbox(
        "Current and saved itineraries",
        options=list(plans_by_key),
        index=0,
        format_func=lambda key: _format_plan_label(plans_by_key[key]),
        key="selected_plan",
    )
    displayed_plan = plans_by_key[selected_key]

if displayed_plan:
    st.divider()
    _render_plan(displayed_plan)

    with st.container(horizontal=True):
        save_clicked = st.button(
            "Save itinerary",
            key="save_itinerary",
            icon=":material/bookmark_add:",
        )
        st.download_button(
            "Save as PDF",
            data=partial(build_itinerary_pdf, copy.deepcopy(displayed_plan)),
            file_name=_pdf_file_name(displayed_plan),
            mime="application/pdf",
            key="save_itinerary_pdf",
            icon=":material/picture_as_pdf:",
            on_click="ignore",
        )

    if save_clicked:
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
                result = _run_with_progress(
                    partial(
                        TripPlannerAgent().generate_trip_plan,
                        destination=displayed_plan.get("destination", destination),
                        duration=int(displayed_plan.get("duration", duration)),
                        interests=displayed_plan.get("interests", interests),
                        budget=displayed_plan.get("budget", budget),
                        travel_style=displayed_plan.get("travel_style", travel_style),
                        additional_request=displayed_plan.get("additional_request", ""),
                        existing_itinerary=current,
                        start_date=_plan_start_date(displayed_plan),
                        refinement=refinement,
                    )
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
                logger.warning(
                    "Itinerary refinement failed (%s): %s", type(error).__name__, error
                )
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
