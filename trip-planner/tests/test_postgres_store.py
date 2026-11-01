from contextlib import contextmanager

from utils.storage.accounts import Identity
from utils.storage.postgres_store import PostgresStore


def test_local_postgres_owner_filter_is_parameterized(monkeypatch):
    import psycopg

    executed = []

    class Cursor:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            pass

        def execute(self, query, parameters=None):
            executed.append((query, parameters))

        def fetchall(self):
            return []

    class Connection(Cursor):
        def cursor(self, **kwargs):
            return Cursor()

    @contextmanager
    def connect(*args, **kwargs):
        yield Connection()

    monkeypatch.setattr(psycopg, "connect", connect)
    owner = "a" * 64
    assert PostgresStore("local-test-dsn").load(Identity(owner)) == {}
    assert executed[-1][1] == [owner, 1]
