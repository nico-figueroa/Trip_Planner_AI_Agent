"""OpenAI client configuration and secret resolution."""

from __future__ import annotations

import logging

from openai import (
    APIError,
    AuthenticationError,
    BadRequestError,
    OpenAI,
    PermissionDeniedError,
    RateLimitError,
)

from utils.core.config import resolve_secret

logger = logging.getLogger(__name__)
OPENAI_TIMEOUT_SECONDS = 90.0 # Timeout for OpenAI requests in seconds
# Long itineraries (for example, 19+ days) can take over 30 seconds to generate, hence the 90-second timeout (3x the typical duration)

class MissingAPIKeyError(RuntimeError):
    """Raised when no supported OpenAI API key source is configured."""


def get_api_key() -> str | None:
    """Return the selected key without displaying or persisting its value."""
    return resolve_secret("OPENAI_API_KEY")[0]


def describe_openai_error(error: APIError) -> str:
    """Log safe error metadata and return actionable, credential-free guidance."""
    logger.error(
        "OpenAI request failed: error_type=%s http_status=%s.",
        type(error).__name__,
        getattr(error, "status_code", None),
    )
    if isinstance(error, AuthenticationError):
        return (
            "OpenAI rejected the configured API key (HTTP 401). Configure a valid "
            "OpenAI API key "
            "as OPENAI_API_KEY in your .env file or process environment. "
            ".env values take priority over the process environment. "
            "Restart Streamlit after changing an environment variable."
        )
    if isinstance(error, RateLimitError):
        return (
            "OpenAI quota or rate limit reached (HTTP 429). Check your API "
            "project's billing and quota; if quota is available, wait and retry."
        )
    if isinstance(error, PermissionDeniedError):
        return (
            "The OpenAI API key does not have permission for this request "
            "(HTTP 403). Check the key's project and model permissions."
        )
    if isinstance(error, BadRequestError):
        return (
            "OpenAI rejected the request format (HTTP 400). Check the application "
            "logs and the installed OpenAI SDK before retrying."
        )
    return "The AI planner is temporarily unavailable. Please try again."


def get_client() -> OpenAI:
    """Construct an OpenAI client without logging or persisting credentials."""
    api_key = get_api_key()
    if not api_key:
        raise MissingAPIKeyError(
            "Configure OPENAI_API_KEY in a .env file or the process environment."
        )
    
    return OpenAI(api_key=api_key, timeout=OPENAI_TIMEOUT_SECONDS, max_retries=1)
