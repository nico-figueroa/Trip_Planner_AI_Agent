"""Verified OIDC identities and optional server-side Supabase persistence."""

from __future__ import annotations

import hashlib
import json
import logging
from dataclasses import dataclass
from typing import Any, Mapping
from urllib.parse import urlparse
from datetime import datetime, timezone

import requests
import streamlit as st
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_fixed

from utils.core.config import resolve_secret

logger = logging.getLogger(__name__)


class StorageError(RuntimeError):
    """A credential-safe cloud storage error."""


@dataclass(frozen=True)
class Identity:
    """An identity derived exclusively from a verified OIDC session."""

    owner: str
    admin: bool = False


def identity_from_claims(claims: Mapping[str, Any]) -> Identity | None:
    """Use issuer and subject, never email or a browser-provided account ID."""
    if not claims.get("is_logged_in"):
        return None
    issuer, subject = claims.get("iss"), claims.get("sub")
    if not isinstance(issuer, str) or not isinstance(subject, str) or not issuer or not subject:
        raise ValueError("The identity provider must expose issuer and subject claims.")
    principal = json.dumps([issuer, subject], separators=(",", ":"))
    owner = hashlib.sha256(principal.encode()).hexdigest()
    configured = resolve_secret("ADMIN_PRINCIPALS")[0] or "[]"
    try:
        admins = json.loads(configured)
    except json.JSONDecodeError as error:
        raise ValueError("ADMIN_PRINCIPALS must be a JSON list of [issuer, subject] pairs.") from error
    if not isinstance(admins, list):
        raise ValueError("ADMIN_PRINCIPALS must be a JSON list.")
    return Identity(owner, [issuer, subject] in admins)


def current_identity() -> Identity | None:
    """Read verified claims on the Streamlit script thread only."""
    return identity_from_claims(dict(st.user))


def auth_configured() -> bool:
    """OIDC is the only configuration read from Streamlit secrets."""
    from streamlit.errors import StreamlitSecretNotFoundError

    try:
        return "auth" in st.secrets
    except StreamlitSecretNotFoundError:
        return False


class CloudStore:
    """A server-only REST adapter; owner filters are mandatory for private state.

    The service-role key never reaches the browser. SQL denies direct public
    table/RPC access; authorization is enforced using verified OIDC identities.
    """

    def __init__(self, url: str, key: str):
        parsed = urlparse(url)
        if parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password:
            raise ValueError("SUPABASE_URL must be an HTTPS project URL.")
        self.url = url.rstrip("/") + "/rest/v1"
        self.key = key

    @retry(
        retry=retry_if_exception_type((requests.ConnectionError, requests.Timeout)),
        stop=stop_after_attempt(2),
        wait=wait_fixed(1),
        reraise=True,
    )
    def _send(self, method: str, resource: str, **kwargs: Any) -> requests.Response:
        return requests.request(
            method,
            f"{self.url}/{resource}",
            headers={
                "apikey": self.key,
                "Authorization": f"Bearer {self.key}",
                "Prefer": "resolution=merge-duplicates,return=representation",
            },
            timeout=(5, 15),
            **kwargs,
        )

    def request(self, method: str, resource: str, **kwargs: Any) -> Any:
        """Never expose provider bodies, URLs, or headers in errors."""
        try:
            response = self._send(method, resource, **kwargs)
            response.raise_for_status()
            return response.json() if response.content else None
        except (requests.RequestException, ValueError) as error:
            logger.warning("Cloud storage operation failed (%s).", type(error).__name__)
            raise StorageError("Cloud storage is unavailable. Your session plan remains available.") from None

    def load(self, identity: Identity) -> dict[str, Any]:
        rows = self.request(
            "GET", "planner_accounts",
            params={"owner": f"eq.{identity.owner}", "select": "state", "limit": 1},
        )
        if not isinstance(rows, list):
            raise StorageError("Cloud storage returned invalid account data.")
        if rows and (not isinstance(rows[0], dict) or not isinstance(rows[0].get("state"), dict)):
            raise StorageError("Stored account data has an invalid format.")
        return rows[0]["state"] if rows else {}

    def save(self, identity: Identity, state: dict[str, Any]) -> None:
        rows = self.request("POST", "planner_accounts", json={"owner": identity.owner, "state": state})
        if (
            not isinstance(rows, list) or len(rows) != 1
            or not isinstance(rows[0], dict) or rows[0].get("owner") != identity.owner
        ):
            raise StorageError("Storage did not confirm the save. Your session plan remains available.")

    def feedback(
        self, actor: str, plan_id: str, rating: str, comment: str, poi_id: str = "",
    ) -> str:
        rows = self.request(
            "POST", "planner_feedback",
            params={"on_conflict": "actor,plan_id,poi_id"},
            json={
                "actor": actor, "plan_id": plan_id, "rating": rating,
                "comment": comment, "poi_id": poi_id,
                "created_at": datetime.now(timezone.utc).isoformat(),
            },
        )
        return rows[0]["id"]

    def scores(self) -> dict[str, float]:
        rows = self.request("POST", "rpc/planner_poi_scores", json={})
        return {row["poi_id"]: float(row["boost"]) for row in rows}

    def stats(self) -> dict[str, int]:
        rows = self.request("POST", "rpc/planner_feedback_stats", json={})
        return rows[0]

    def propose(self, feedback_id: str, review: dict[str, Any]) -> None:
        self.request(
            "POST", "planner_guidance", params={"on_conflict": "feedback_id"},
            json={"feedback_id": feedback_id, "reviewer": None, **review},
        )

    def guidance(self) -> list[str]:
        rows = self.request(
            "GET", "planner_guidance",
            params={"status": "eq.approved", "select": "instruction", "order": "created_at.desc", "limit": 8},
        )
        return [row["instruction"] for row in rows if row["instruction"]]

    def pending(self, identity: Identity) -> list[dict[str, Any]]:
        if not identity.admin:
            raise PermissionError("Administrator access is required.")
        return self.request(
            "GET", "planner_guidance",
            params={"status": "eq.pending", "select": "*", "order": "created_at", "limit": 20},
        )

    def decide(self, identity: Identity, proposal_id: str, approve: bool) -> None:
        if not identity.admin:
            raise PermissionError("Administrator access is required.")
        rows = self.request(
            "PATCH", "planner_guidance", params={"id": f"eq.{proposal_id}", "status": "eq.pending"},
            json={"status": "approved" if approve else "rejected", "reviewer": identity.owner},
        )
        if not rows:
            raise StorageError("The proposal is no longer pending. Reload it before deciding.")


def get_store() -> CloudStore | None:
    """Disable cloud actions until both environment/.env settings are available."""
    dsn = resolve_secret("DATABASE_URL")[0]
    if dsn:
        from utils.storage.postgres_store import PostgresStore

        return PostgresStore(dsn)
    url = resolve_secret("SUPABASE_URL")[0]
    key = resolve_secret("SUPABASE_SERVICE_ROLE_KEY")[0]
    if not url and not key:
        return None
    if not url or not key:
        raise ValueError("Configure both SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY.")
    return CloudStore(url, key)
