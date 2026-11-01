"""Streamlit trip planning with optional private accounts and configurable reports."""

from __future__ import annotations

import copy
import json
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
from pydeck.types import String
import streamlit as st

from utils.accounts import StorageError, auth_configured, current_identity, get_store
from utils.agent import TripPlannerAgent
from utils.feedback import review_feedback
from utils.logging_config import configure_logging
from utils.openai_agent import PlanningError
from utils.openai_client import MissingAPIKeyError, get_api_key
from utils.pdf_report import build_itinerary_pdf, day_heading
from utils.trip_features import (
    budget_totals, import_plan_json, map_data, money, poi_key, resolve_duration, safe_url, selected_days,
)

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
st.set_page_config(page_title="AI Trip Planner", page_icon=":material/travel:", layout="wide")


def _format_plan_label(plan: dict[str, Any]) -> str:
    created = str(plan.get("created_at", ""))[:16].replace("T", " ")
    variant = f" - {plan['variant']}" if plan.get("variant") else ""
    return f"{plan.get('destination', 'Trip')}{variant} ({plan.get('duration', '?')} days, {created or 'session'})"


def _plan_start_date(plan: dict[str, Any]) -> date | None:
    value = plan.get("start_date")
    return date.fromisoformat(value) if value else None


def _run_with_progress(task: Callable[[], T]) -> T:
    """Only the script thread updates the single, non-flickering status element."""
    placeholder = st.empty()
    index = random.randrange(len(PROGRESS_MESSAGES))
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
    latitudes = [point["latitude"] for point in points]
    longitudes = [point["longitude"] for point in points]
    latitude = (min(latitudes) + max(latitudes)) / 2
    longitude = (min(longitudes) + max(longitudes)) / 2
    if len(points) == 1:
        return pdk.ViewState(latitude=latitude, longitude=longitude, zoom=12)
    lon_span = max(max(longitudes) - min(longitudes), 1e-4)
    lat_span = max(max(latitudes) - min(latitudes), 1e-4)
    scale = min(600 / lon_span, 380 * max(math.cos(math.radians(latitude)), 0.1) / lat_span)
    zoom = max(1.0, min(14.0, math.log2(scale * 360 / 256)))
    return pdk.ViewState(latitude=latitude, longitude=longitude, zoom=round(zoom, 2))


def _render_map(plan: dict[str, Any], day: int | None, style: str) -> None:
    points, paths = map_data(plan, day)
    if not points:
        st.info("No verified map locations are available for this selection.")
        return
    scatter = pdk.Layer(
        "ScatterplotLayer", data=points, get_position="[longitude, latitude]",
        get_fill_color="color", get_radius="radius", radius_units=String("meters"),
        radius_min_pixels=3, radius_max_pixels=12, pickable=True,
    )
    path = pdk.Layer(
        "PathLayer", data=[{"path": segment} for segment in paths], get_path="path",
        get_color=[244, 166, 35], get_width=3, width_units=String("pixels"), width_min_pixels=2,
    )
    style_name = "dark-matter" if style == "Dark" else "positron"
    deck = pdk.Deck(
        layers=[path, scatter], initial_view_state=_map_view(points),
        views=[pdk.View("MapView", controller={"scrollZoom": {"smooth": True, "speed": 0.01}, "dragRotate": False})],
        map_style=f"https://basemaps.cartocdn.com/gl/{style_name}-gl-style/style.json",
        tooltip={"text": "{name}\n{category}"},  # pyright: ignore[reportArgumentType] -- pydeck's bool annotation omits supported dictionaries.
    )
    st.pydeck_chart(
        deck, height=460, key=f"map_{plan.get('id', 'session')}",
        alt="Verified trip locations connected in visit order",
    )
    st.caption("Lines show visit order, not road routes. Map data: OpenStreetMap contributors.")
    if plan.get("unresolved_locations"):
        st.warning("Unverified locations omitted from map: " + ", ".join(plan["unresolved_locations"]))


def _render_plan(
    plan: dict[str, Any], day: int | None, outputs: list[str], style: str, prefix: str = "",
) -> None:
    itinerary = plan.get("itinerary", {})
    st.subheader(itinerary.get("destination", plan.get("destination", "Trip")))
    st.write(itinerary.get("overview", ""))
    if "Budget" in outputs:
        spent, _, estimated = budget_totals(plan)
        st.caption(
            f"Recorded spending: {spent} {plan.get('currency', 'USD')} | "
            + (f"Estimated trip total: {estimated} (not a quote)" if estimated is not None else "Trip estimate unavailable")
        )
    for item in selected_days(plan, day):
        with st.expander(day_heading(plan, item), expanded=item.get("day") == 1):
            for activity in item.get("activities", []):
                st.markdown(f"- {activity}")
            if "Budget" in outputs and item.get("estimated_cost") is not None:
                st.caption(f"Estimated cost: {item['estimated_cost']:.2f} {plan.get('currency', 'USD')} (not a quote)")
    if "Travel notes" in outputs and itinerary.get("travel_notes"):
        with st.expander("Travel notes"):
            st.write(itinerary["travel_notes"])
    if "Nearby places" in outputs:
        st.subheader("Nearby places")
        pois = plan.get("pois", [])
        if day is not None:
            points, _ = map_data(plan, day)
            coordinates = {(point["latitude"], point["longitude"]) for point in points}
            pois = [poi for poi in pois if (poi.get("latitude"), poi.get("longitude")) in coordinates]
        rows = [
            {
                "Name": poi.get("name", ""), "Category": poi.get("category", ""),
                "Address": poi.get("address") or "Address not available",
                "More information": safe_url(poi.get("url"), poi.get("latitude"), poi.get("longitude")),
            } for poi in pois
        ]
        if rows:
            st.dataframe(
                rows, hide_index=True, alt="Places with addresses and information links",
                column_config={"More information": st.column_config.LinkColumn("More information")},
            )
            st.caption("Places powered by [Geoapify](https://www.geoapify.com/) using [OpenStreetMap](https://www.openstreetmap.org/copyright) data.")
        else:
            st.info("No retrieved places match this selection.")
    if "Map" in outputs:
        # Comparison panes use distinct plan IDs; the main map keeps a stable key.
        _render_map({**plan, "id": prefix + str(plan.get("id", "session"))}, day, style)
    if "Agent trace" in outputs:
        with st.expander("Agent execution trace"):
            for event in plan.get("trace", []):
                st.markdown(f"**{event.get('tool', 'Agent step')}**")
                if event.get("success"):
                    st.json({"arguments": event.get("arguments", {}), "result": event.get("result")})
                else:
                    st.warning(event.get("error", "The tool could not be completed."))


def _record_plan(plan: dict[str, Any]) -> None:
    plan["id"] = uuid.uuid4().hex
    plan["created_at"] = datetime.now(timezone.utc).isoformat()
    state = st.session_state["planner_state"]
    state["active_itinerary"] = plan
    session_plans = state.setdefault("session_plans", [])
    session_plans.insert(0, copy.deepcopy(plan))
    del session_plans[MAX_SAVED_ITINERARIES:]
    st.session_state["current_plan"] = plan


def _planner() -> TripPlannerAgent:
    """Use fresh approved rules and votes; never apply unreviewed feedback."""
    boosts: dict[str, float] = {}
    guidance: list[str] = []
    if store is not None:
        try:
            boosts, guidance = store.scores(), store.guidance()
        except StorageError as error:
            st.warning(f"{error} Feedback ranking and guidance are unavailable for this request.")
    return TripPlannerAgent(boosts=boosts, guidance=guidance)


def _refine_request(plan: dict[str, Any], instruction: str, target: int | None = None) -> dict[str, Any]:
    return {
        "destination": plan["destination"], "duration": int(plan["duration"]),
        "interests": plan.get("interests", ""), "budget": plan.get("budget", ""),
        "travel_style": plan.get("travel_style", ""),
        "additional_request": plan.get("additional_request", ""),
        "existing_itinerary": plan["itinerary"], "start_date": _plan_start_date(plan),
        "refinement": instruction, "target_day": target, "currency": plan.get("currency", "USD"),
    }


def _sync_date_duration() -> None:
    """Form callbacks run before widget creation, so the number can safely change."""
    st.session_state.pop("date_adjustment", None)
    if st.session_state.get("date_mode") not in ("Date range", "Both"):
        return
    start, end = st.session_state.get("start_date"), st.session_state.get("end_date")
    if start is not None and end is not None:
        try:
            days, changed = resolve_duration(int(st.session_state["duration"]), start, end)
        except ValueError:
            return  # The generation handler displays the validation error.
        if changed:
            st.session_state["date_adjustment"] = f"Duration automatically adjusted to {days} days to match the inclusive date range."
            st.session_state["duration"] = days


@st.cache_data(ttl=30)
def _feedback_stats() -> dict[str, int]:
    backend = get_store()
    if backend is None:
        raise StorageError("Feedback storage is not configured.")
    return backend.stats()


ERRORS = (MissingAPIKeyError, PlanningError, StorageError, ValueError, OSError)
st.session_state.setdefault("planner_state", {})
st.session_state.setdefault("current_plan", None)
st.session_state.setdefault("anonymous_actor", "anon-" + uuid.uuid4().hex)
st.session_state.setdefault("session_feedback", {"total": 0, "positive": 0, "negative": 0})
try:
    auth_ready = auth_configured()  # Loads root TOML environment values before backend configuration.
    identity = current_identity()
    store = get_store()
except (ValueError, StorageError) as error:
    logger.warning("Account configuration failed (%s).", type(error).__name__)
    st.error(str(error))
    identity, store, auth_ready = None, None, False
owner = identity.owner if identity else None
if "account_owner" in st.session_state and st.session_state["account_owner"] != owner:
    st.session_state["planner_state"] = {}
    st.session_state["current_plan"] = None
    st.session_state.pop("before_refinement", None)
    st.session_state.pop("selected_plan", None)
st.session_state["account_owner"] = owner

with st.sidebar:
    st.header("Configuration")
    outputs = st.multiselect(
        "Visible outputs", ["Nearby places", "Map", "Travel notes", "Agent trace", "Budget"],
        default=["Nearby places", "Map", "Travel notes", "Budget"], key="visible_outputs",
    )
    style = st.selectbox("Map style", ["Light", "Dark"], key="map_style")
    compare_enabled = st.checkbox("Enable trip comparison", key="compare_enabled")
    alternatives_enabled = st.checkbox(
        "Enable alternative generation", key="alternatives_enabled",
        help="Each alternative makes an additional planning request and may incur API charges.",
    )
    show_changes = st.checkbox("Show refinement before/after", value=True, key="show_changes")
    st.divider()
    if identity:
        st.caption("Signed in. Personal save/load is available when database storage is configured.")
        if st.button("Sign out"):
            st.logout()
        if st.button("Load my saved plans", disabled=store is None):
            try:
                if store is None:
                    raise StorageError("Configure database storage before loading plans.")
                loaded = store.load(identity)
                if loaded:
                    existing = st.session_state["planner_state"]
                    loaded["session_plans"] = copy.deepcopy(existing.get("session_plans", []))
                    st.session_state["planner_state"] = loaded
                    st.session_state["current_plan"] = loaded.get("active_itinerary")
                    st.session_state.pop("selected_plan", None)
                    st.session_state.pop("before_refinement", None)
                else:
                    st.info("No saved account plans yet. Your session plan is unchanged.")
            except StorageError as error:
                st.error(str(error))
    elif auth_ready:
        st.caption("Sign-in is optional. Use it to save/load private plans.")
        if st.button("Sign in"):
            st.login()
    else:
        st.caption("Anonymous planning enabled. Administrator OIDC setup is needed for personal accounts.")
    if not identity and st.session_state.get("current_plan"):
        st.warning("Sign-in starts a new session. Export your anonymous plan before signing in.")
    if store is None:
        st.caption("Database storage and persistent feedback are not configured.")

st.title("AI Trip Planner")
st.markdown("Create a grounded travel plan with live OpenStreetMap data and an AI planning agent.")
with st.expander("Import an exported or legacy plan"):
    upload = st.file_uploader("Plan JSON", type=["json"])
    if st.button("Import into this session", disabled=upload is None):
        try:
            if upload is None:
                raise ValueError("Select a plan JSON file first.")
            imported = import_plan_json(upload.getvalue())
            _record_plan(imported)
            st.session_state["selected_plan"] = imported["id"]
            st.success("Plan imported into this session. Use Save itinerary for your private account copy.")
        except (ValueError, TypeError, KeyError) as error:
            logger.warning("Plan import failed (%s).", type(error).__name__)
            st.error("Invalid plan JSON: verify itinerary days, dates, coordinates, and expense data.")
date_mode = st.segmented_control(
    "Trip duration input", ["Number of days", "Date range", "Both"],
    default="Number of days", key="date_mode",
)
with st.form("trip_request"):
    destination = st.text_input("Destination", placeholder="Kyoto, Japan", key="destination")
    duration = st.number_input(
        "Duration (days)", min_value=1, max_value=30, value=3, step=1,
        key="duration", disabled=date_mode == "Date range",
    )
    dates = st.columns(2)
    start_date = dates[0].date_input("Start date (optional)", value=None, key="start_date")
    end_date = dates[1].date_input(
        "End date", value=None, key="end_date", disabled=date_mode == "Number of days",
    )
    interests = st.text_input("Interests", max_chars=500, key="interests")
    budget = st.text_input("Budget preferences (optional)", max_chars=200, key="budget")
    budget_row = st.columns(2)
    budget_total = budget_row[0].number_input("Total trip budget (0 = not set)", min_value=0.0, value=0.0, key="budget_total")
    currency = budget_row[1].selectbox("Currency", ["USD", "EUR", "GBP", "CRC", "CAD", "AUD"], key="currency")
    travel_style = st.text_input("Travel style (optional)", max_chars=200, key="travel_style")
    additional_request = st.text_area("Additional request", max_chars=1000, key="additional_request")
    generate = st.form_submit_button("Generate itinerary", width="stretch", on_click=_sync_date_duration)

if generate:
    try:
        if not get_api_key():
            raise MissingAPIKeyError("Configure OPENAI_API_KEY in a .env file or process environment.")
        if date_mode not in ("Number of days", "Date range", "Both"):
            raise ValueError("Choose a duration input mode.")
        if date_mode in ("Date range", "Both") and (start_date is None or end_date is None):
            raise ValueError("Date range mode requires both start and end dates.")
        effective_end = end_date if date_mode != "Number of days" else None
        days, changed = resolve_duration(int(duration), start_date, effective_end)
        if st.session_state.get("date_adjustment"):
            st.info(st.session_state["date_adjustment"])
        if changed:
            st.info(f"Duration automatically adjusted from {duration} to {days} days to match the inclusive date range.")
        planner = _planner()
        result = _run_with_progress(partial(
            planner.generate_trip_plan, destination=destination, duration=days,
            interests=interests, budget=f"{budget}; total {budget_total:.2f} {currency}" if budget_total else budget,
            travel_style=travel_style, additional_request=additional_request,
            start_date=start_date, currency=currency,
        ))
        result.update(budget_total=str(money(budget_total)), expenses=[])
        _record_plan(result)
        st.session_state["selected_plan"] = result["id"]
        st.session_state.pop("before_refinement", None)
        st.success("Itinerary generated. Available in this session; use Save itinerary for a private cloud copy.")
    except ERRORS as error:
        logger.warning("Trip planning failed (%s).", type(error).__name__)
        st.error(str(error))

state = st.session_state["planner_state"]
plans: dict[str, dict[str, Any]] = {}
for item in [state.get("active_itinerary"), *state.get("session_plans", []), *state.get("saved_itineraries", [])]:
    if isinstance(item, dict) and item.get("itinerary"):
        key = str(item.get("id") or "legacy-session")
        plans.setdefault(key, item)
displayed_plan = None
if plans:
    if st.session_state.get("selected_plan") not in plans:
        st.session_state.pop("selected_plan", None)
    key = st.selectbox(
        "Current and saved itineraries", list(plans), format_func=lambda value: _format_plan_label(plans[value]),
        key="selected_plan",
    )
    displayed_plan = plans[key]
if displayed_plan:
    plan_id = str(displayed_plan.get("id", "session"))
    days_available = [item["day"] for item in displayed_plan["itinerary"]["daily_plan"]]
    day = st.selectbox(
        "Show itinerary day", [None, *days_available],
        format_func=lambda value: "Entire trip" if value is None else f"Day {value}",
        key=f"day_filter_{plan_id}",
    )
    _render_plan(displayed_plan, day, outputs, style)
    with st.container(horizontal=True):
        if st.button("Save itinerary", disabled=identity is None or store is None):
            try:
                if identity is None or store is None:
                    raise PermissionError("Optional sign-in and configured storage are required for private saving.")
                private_state = copy.deepcopy(state)
                saved = [item for item in private_state.get("saved_itineraries", []) if item.get("id") != plan_id]
                private_state["saved_itineraries"] = [copy.deepcopy(displayed_plan), *saved][:MAX_SAVED_ITINERARIES]
                private_state["active_itinerary"] = copy.deepcopy(displayed_plan)
                private_state.pop("session_plans", None)
                store.save(identity, private_state)
                state["saved_itineraries"] = private_state["saved_itineraries"]
                st.success("Private itinerary saved to your account.")
            except ERRORS as error:
                st.error(str(error))
        st.download_button(
            "Save as PDF", data=partial(build_itinerary_pdf, copy.deepcopy(displayed_plan)),
            file_name=_pdf_file_name(displayed_plan), mime="application/pdf", on_click="ignore",
        )
        st.download_button(
            "Export plan JSON", data=json.dumps(displayed_plan, ensure_ascii=False),
            file_name="trip-plan.json", mime="application/json", on_click="ignore",
            help="Keep this file private. Import it after sign-in to save an anonymous plan.",
        )
    if not identity:
        st.caption("You can plan and download a PDF anonymously. Optional sign-in enables private cloud save/load.")
    if "Budget" in outputs:
        with st.expander("Budget tracking"):
            try:
                spent, remaining, estimated = budget_totals(displayed_plan)
                currency_code = displayed_plan.get("currency", "USD")
                has_budget = money(displayed_plan.get("budget_total", 0)) > 0
                st.write(
                    f"Spent: {spent} {currency_code} | Remaining: {remaining} {currency_code}"
                    if has_budget else f"Spent: {spent} {currency_code} | Total budget not set"
                )
                st.caption(
                    f"Model-estimated trip cost: {estimated} {currency_code} (not actual prices)."
                    if estimated is not None else "Complete daily cost estimates are unavailable."
                )
                if has_budget and remaining < 0:
                    st.warning("Recorded expenses exceed the trip budget.")
                with st.form(f"expense_{plan_id}"):
                    category = st.selectbox("Expense category", ["Transport", "Lodging", "Food", "Activities", "Other"])
                    amount = st.number_input(f"Amount ({currency_code})", min_value=0.0, value=0.0)
                    description = st.text_input("Expense description", max_chars=200)
                    expense_day = st.selectbox("Expense day", days_available)
                    add_expense = st.form_submit_button("Add expense")
                if add_expense:
                    if money(amount) <= 0:
                        raise ValueError("Expense amount must be greater than zero.")
                    displayed_plan.setdefault("expenses", []).append({
                        "category": category, "amount": str(money(amount)),
                        "description": description, "day": expense_day,
                    })
                    st.success("Expense added in this session. Save the itinerary to persist it.")
                    st.rerun()
                if displayed_plan.get("expenses"):
                    st.dataframe(displayed_plan["expenses"], hide_index=True, alt="Recorded trip expenses")
            except ValueError as error:
                st.error(str(error))
    with st.form(f"refine_{plan_id}"):
        st.subheader("Refine this itinerary")
        target = st.selectbox(
            "Refinement scope", [None, *days_available],
            format_func=lambda value: "Whole trip" if value is None else f"Regenerate day {value} only",
        )
        instruction = st.text_area("What would you like to change?", max_chars=1000)
        refine = st.form_submit_button("Refine itinerary")
    if refine:
        try:
            if not instruction.strip():
                raise ValueError("Describe the change you want before refining.")
            before = copy.deepcopy(displayed_plan)
            result = _run_with_progress(partial(_planner().generate_trip_plan, **_refine_request(before, instruction, target)))
            result.update(expenses=copy.deepcopy(before.get("expenses", [])), budget_total=before.get("budget_total", "0"))
            _record_plan(result)
            st.session_state["before_refinement"] = {"before": before, "after": copy.deepcopy(result)}
            st.session_state.pop("selected_plan", None)
            st.rerun()
        except ERRORS as error:
            logger.warning("Refinement failed (%s).", type(error).__name__)
            st.error(str(error))
    if show_changes and st.session_state.get("before_refinement"):
        snapshots = st.session_state["before_refinement"]
        if snapshots["after"]["id"] == plan_id:
            with st.expander("Refinement before / after"):
                columns = st.columns(2)
                for column, label in zip(columns, ("before", "after")):
                    with column:
                        st.subheader(label.capitalize())
                        _render_plan(snapshots[label], day, ["Travel notes"], style)
    if alternatives_enabled and st.button("Generate two alternative plans"):
        try:
            for index, strategy in enumerate(
                ("Prefer fewer accommodation changes and low-cost activities.", "Prefer more nature and a different set of retrieved attractions."), start=1,
            ):
                result = _run_with_progress(partial(
                    _planner().generate_trip_plan,
                    **_refine_request(displayed_plan, "Create a distinct alternative. " + strategy),
                ))
                if any(
                    result["itinerary"]["daily_plan"] == candidate["itinerary"]["daily_plan"]
                    for candidate in [
                        displayed_plan, *st.session_state["planner_state"].get("session_plans", [])[:index - 1],
                    ]
                ):
                    raise PlanningError("The model returned a duplicate alternative. Please retry instead of treating it as a new option.")
                result.update(budget_total=displayed_plan.get("budget_total", "0"), expenses=[], variant=f"Alternative {index}")
                _record_plan(result)
            st.session_state.pop("selected_plan", None)
            st.success("Two alternatives generated. Enable trip comparison to view them side-by-side.")
            st.rerun()
        except ERRORS as error:
            st.error(f"{error} Any completed alternative remains available in this session.")
    if compare_enabled and len(plans) > 1:
        if "comparison_plans" in st.session_state:
            st.session_state["comparison_plans"] = [
                value for value in st.session_state["comparison_plans"] if value in plans
            ][:3]
        comparison = st.multiselect(
            "Compare trip options (up to three)", list(plans), max_selections=3,
            format_func=lambda value: _format_plan_label(plans[value]), key="comparison_plans",
        )
        if comparison:
            for column, value in zip(st.columns(len(comparison)), comparison):
                with column:
                    _render_plan(plans[value], None, ["Travel notes", "Budget"], style)
    with st.form(f"feedback_{plan_id}"):
        st.subheader("Feedback")
        poi_options = {poi_key(poi): poi for poi in displayed_plan.get("pois", [])}
        feedback_target = st.selectbox(
            "Feedback target", ["", *poi_options],
            format_func=lambda value: "Entire itinerary" if not value else poi_options[value]["name"],
        )
        rating = st.segmented_control("Was this helpful?", ["Positive", "Negative"], default="Positive")
        comment = st.text_area("Comments (optional)", max_chars=2000)
        submit_feedback = st.form_submit_button("Submit feedback", disabled=store is None)
    if submit_feedback:
        try:
            if store is None:
                raise StorageError("Configure database storage before submitting feedback.")
            if rating not in ("Positive", "Negative"):
                raise ValueError("Select a positive or negative rating.")
            if feedback_target and not identity:
                raise ValueError("Optional sign-in is needed for persistent POI votes, to prevent repeat anonymous voting.")
            feedback_id = store.feedback(
                identity.owner if identity else st.session_state["anonymous_actor"],
                plan_id, rating.lower(), comment.strip(), feedback_target,
            )
            _feedback_stats.clear()
            st.success("Feedback saved. Any proposed instruction changes require administrator approval.")
            if comment.strip():
                context = {
                    "destination": displayed_plan["destination"],
                    "days": [
                        {"day": item["day"], "title": item["title"], "activities": item.get("activities", [])[:2]}
                        for item in selected_days(displayed_plan, day)
                    ],
                    "constraints": displayed_plan.get("additional_request", ""),
                }
                review = _run_with_progress(partial(review_feedback, comment, context))
                store.propose(feedback_id, review)
                st.info(f"Review: {review['reason']} (status: {review['status']}).")
        except (*ERRORS, RuntimeError) as error:
            st.error(str(error))

if identity and identity.admin:
    with st.expander("Administrator: local semantic model"):
        if st.button("Prepare local semantic model"):
            from utils.rag import prepare_model

            try:
                _run_with_progress(prepare_model)
                st.success("Local semantic model prepared; future Wikivoyage calls use vector search.")
            except (OSError, ValueError, ImportError, RuntimeError) as error:
                logger.warning("Semantic model preparation failed (%s).", type(error).__name__)
                st.error("Could not prepare the semantic model. Check network access and available disk/memory.")
if identity and identity.admin and store is not None:
    with st.expander("Administrator: instruction proposals"):
        try:
            for proposal in store.pending(identity):
                st.write(proposal["instruction"])
                st.caption(proposal["reason"])
                row = st.columns(2)
                if row[0].button("Approve", key=f"approve_{proposal['id']}"):
                    store.decide(identity, proposal["id"], True)
                    st.rerun()
                if row[1].button("Reject", key=f"reject_{proposal['id']}"):
                    store.decide(identity, proposal["id"], False)
                    st.rerun()
        except (StorageError, PermissionError) as error:
            st.error(str(error))

st.divider()
st.caption("Feedback statistics")
if store is not None:
    try:
        stats = _feedback_stats()
        columns = st.columns(3)
        for column, key in zip(columns, ("total", "positive", "negative")):
            column.metric(key.capitalize(), stats[key])
    except StorageError:
        st.caption("Persistent feedback statistics are temporarily unavailable.")
else:
    st.caption("No persistent feedback statistics yet; configure PostgreSQL or Supabase to enable collection.")
