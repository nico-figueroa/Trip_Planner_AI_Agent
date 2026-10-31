import os

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

USER_AGENT = os.getenv(
    "USER_AGENT",
    "trip-planner-capstone/1.0"
)

NOMINATIM_URL = "https://nominatim.openstreetmap.org/search"

OVERPASS_URL = "https://overpass-api.de/api/interpreter"