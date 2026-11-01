import pytest
import requests

from utils.storage import accounts
from utils.storage.accounts import CloudStore, Identity, StorageError, identity_from_claims


def test_verified_identity_is_scoped_by_issuer_not_email(monkeypatch):
    monkeypatch.setattr(accounts, "resolve_secret", lambda name: ('[["issuer-one","subject"]]', ".env"))
    first = identity_from_claims({"is_logged_in": True, "iss": "issuer-one", "sub": "subject"})
    second = identity_from_claims({"is_logged_in": True, "iss": "issuer-two", "sub": "subject"})
    assert first.owner != second.owner
    assert first.admin and not second.admin
    assert identity_from_claims({"email": "not-verified@example.com"}) is None


def test_cloud_load_always_filters_by_verified_owner(monkeypatch):
    calls = []
    store = CloudStore("https://example.supabase.co", "server-key")
    monkeypatch.setattr(store, "request", lambda *args, **kwargs: calls.append(kwargs) or [])
    assert store.load(Identity("a" * 64)) == {}
    assert calls[0]["params"]["owner"] == "eq." + "a" * 64


def test_only_admin_can_approve_or_read_proposals():
    store = CloudStore("https://example.supabase.co", "server-key")
    with pytest.raises(PermissionError):
        store.decide(Identity("a" * 64), "proposal", True)
    with pytest.raises(PermissionError):
        store.pending(Identity("a" * 64))


def test_cloud_error_does_not_expose_provider_secrets(monkeypatch):
    store = CloudStore("https://example.supabase.co", "sensitive-key")

    def fail(*args, **kwargs):
        raise requests.HTTPError("sensitive provider details")

    monkeypatch.setattr(store, "_send", fail)
    with pytest.raises(StorageError) as caught:
        store.load(Identity("a" * 64))
    assert "sensitive" not in str(caught.value)


def test_postgres_is_preferred_when_database_url_is_configured(monkeypatch):
    monkeypatch.setattr(accounts, "resolve_secret", lambda name: (
        "postgresql://localhost/trip_planner" if name == "DATABASE_URL" else None, ".env",
    ))
    from utils.storage.postgres_store import PostgresStore

    assert isinstance(accounts.get_store(), PostgresStore)


@pytest.mark.parametrize("rows", [["invalid"], [{"state": []}]])
def test_invalid_stored_account_data_is_rejected(monkeypatch, rows):
    store = CloudStore("https://example.supabase.co", "server-key")
    monkeypatch.setattr(store, "request", lambda *args, **kwargs: rows)
    with pytest.raises(StorageError, match="invalid format"):
        store.load(Identity("a" * 64))


@pytest.mark.parametrize("rows", [[], ["invalid"], [{"owner": "another-owner"}]])
def test_unconfirmed_save_is_not_reported_as_success(monkeypatch, rows):
    store = CloudStore("https://example.supabase.co", "server-key")
    monkeypatch.setattr(store, "request", lambda *args, **kwargs: rows)
    with pytest.raises(StorageError, match="did not confirm"):
        store.save(Identity("a" * 64), {})


def test_stale_proposal_decision_is_reported(monkeypatch):
    store = CloudStore("https://example.supabase.co", "server-key")
    monkeypatch.setattr(store, "request", lambda *args, **kwargs: [])
    with pytest.raises(StorageError, match="no longer pending"):
        store.decide(Identity("a" * 64, admin=True), "proposal", True)
