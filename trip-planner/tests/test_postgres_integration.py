"""Opt-in tests use only the explicitly configured dedicated test database."""

import hashlib
import uuid

import pytest

from utils.accounts import Identity
from utils.config import resolve_secret
from utils.postgres_store import PostgresStore


def test_local_postgres_private_storage_votes_and_admin_approval():
    dsn = resolve_secret("TEST_DATABASE_URL")[0]
    if not dsn:
        pytest.skip("Configure TEST_DATABASE_URL for a dedicated trip_planner_test database.")
    import psycopg

    with psycopg.connect(dsn) as connection:
        if connection.info.dbname != "trip_planner_test":
            pytest.fail("Integration tests require the dedicated trip_planner_test database.")
    store = PostgresStore(dsn)
    marker = uuid.uuid4().hex
    owner = Identity(hashlib.sha256(marker.encode()).hexdigest(), admin=True)
    other = Identity(hashlib.sha256((marker + "other").encode()).hexdigest())
    poi = "test-" + marker
    try:
        store.save(owner, {"saved_itineraries": [{"id": marker}]})
        assert store.load(owner)["saved_itineraries"][0]["id"] == marker
        assert store.load(other) == {}
        feedback_id = store.feedback(owner.owner, marker, "positive", "", poi)
        assert store.scores()[poi] == pytest.approx(0.25)
        store.feedback(other.owner, marker, "negative", "", poi)
        assert store.scores()[poi] == pytest.approx(-0.10)
        store.feedback(owner.owner, marker, "positive", "", poi)
        assert store.scores()[poi] == pytest.approx(-0.10)  # Repeat votes don't accumulate.
        store.propose(feedback_id, {
            "status": "pending", "instruction": "Verify holiday opening times.", "reason": "Actionable",
        })
        proposal = next(row for row in store.pending(owner) if row["feedback_id"] == feedback_id)
        store.decide(owner, proposal["id"], True)
        assert "Verify holiday opening times." in store.guidance()
    finally:
        # Delete only this test's unique rows, never other account data or tables.
        with psycopg.connect(dsn) as connection:
            connection.execute(
                "delete from planner_guidance where feedback_id in "
                "(select id from planner_feedback where plan_id = %s)", [marker],
            )
            connection.execute("delete from planner_feedback where plan_id = %s", [marker])
            connection.execute("delete from planner_accounts where owner = %s", [owner.owner])
