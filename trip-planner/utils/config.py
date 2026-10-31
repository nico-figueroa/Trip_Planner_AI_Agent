"""Shared configuration for external services."""

import os
from pathlib import Path

from dotenv import dotenv_values

DOTENV_FILE = Path(__file__).resolve().parents[1] / ".env"

USER_AGENT = "TripPlannerAI/1.0 (https://github.com/nico-figueroa/Trip_Planner_AI_Agent)"
NOMINATIM_URL = "https://nominatim.openstreetmap.org/search"
GEOAPIFY_URL = "https://api.geoapify.com/v2/places"
WIKIVOYAGE_API_URL = "https://en.wikivoyage.org/w/api.php"
OPENAI_MODEL = "gpt-4.1-mini"


def resolve_secret(name: str) -> tuple[str | None, str | None]:
    """Read .env files first, then the environment, without mutating either."""
    launch_directory = Path.cwd()
    candidates = dict.fromkeys(
        [DOTENV_FILE]
        + [directory / ".env" for directory in (launch_directory, *launch_directory.parents)]
    )
    for path in candidates:
        dotenv_value = dotenv_values(path).get(name)
        if dotenv_value and dotenv_value.strip():
            return dotenv_value.strip(), str(path)

    environment_value = os.getenv(name)
    if environment_value and environment_value.strip():
        return environment_value.strip(), "environment variable"

    return None, None
