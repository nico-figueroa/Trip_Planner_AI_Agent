import streamlit as st

from utils.agent import (
    TripPlannerAgent
)

from utils.validation import (
    validate_trip_request
)

from utils.persistence import (
    save_state
)

st.set_page_config(
    page_title="Trip Planner AI Agent",
    page_icon="🌍",
    layout="wide"
)

agent = TripPlannerAgent()

st.title("🌍 Trip Planner AI Agent")

st.markdown(
    """
    Build personalized itineraries using
    AI and live travel data.
    """
)

destination = st.text_input(
    "Destination"
)

duration = st.number_input(
    "Trip Duration (days)",
    min_value=1,
    max_value=30,
    value=3
)

interests = st.text_input(
    "Interests",
    placeholder="Food, museums, parks..."
)

if st.button(
    "Generate Itinerary"
):

    errors = validate_trip_request(
        destination,
        duration
    )

    if errors:

        for error in errors:
            st.error(error)

    else:

        try:

            with st.spinner(
                "Planning trip..."
            ):

                result = (
                    agent.generate_trip_plan(
                        destination,
                        duration,
                        interests
                    )
                )

                save_state(result)

            st.success(
                "Itinerary Created"
            )

            st.subheader(
                "Destination"
            )

            st.write(
                result["location"][
                    "display_name"
                ]
            )

            st.subheader(
                "Travel Context"
            )

            st.write(
                result[
                    "travel_context"
                ]
            )

            st.subheader(
                "Points of Interest"
            )

            if result["pois"]:

                for poi in result[
                    "pois"
                ]:

                    st.write(
                        f"• {poi['name']}"
                    )

            else:

                st.info(
                    "No POIs found."
                )

            st.subheader(
                "Itinerary"
            )

            for day in result[
                "itinerary"
            ]:

                with st.expander(
                    day["title"]
                ):

                    for activity in day[
                        "activities"
                    ]:

                        st.write(
                            f"- {activity}"
                        )

        except Exception as error:

            st.error(
                str(error)
            )

st.divider()

st.caption(
    "Codecademy AI Engineer Capstone Project"
)