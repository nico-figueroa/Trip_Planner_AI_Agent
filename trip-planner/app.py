import streamlit as st

st.set_page_config(
    page_title="Trip Planner AI Agent",
    page_icon="🌍",
    layout="wide"
)

st.title("🌍 Trip Planner AI Agent")

st.markdown("""
Generate personalized travel itineraries using AI,
real-time geographic data, and interactive maps.
""")

destination = st.text_input("Destination")

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

if st.button("Generate Itinerary"):
    st.success("Trip request submitted.")

    st.write({
        "destination": destination,
        "duration": duration,
        "interests": interests
    })

st.divider()

st.caption("Codecademy AI Engineer Capstone Project")