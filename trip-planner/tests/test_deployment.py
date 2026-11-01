from pathlib import Path
import runpy

import psycopg
from psycopg import sql

from utils.core import config


def test_local_setup_creates_only_dedicated_databases_without_role_changes(monkeypatch):
    connections = []
    statements = []

    class Connection:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            pass

        def execute(self, query, parameters=None, **kwargs):
            statements.append((query, parameters, kwargs))
            return self

        def fetchone(self):
            return None

    def connect(dsn, **kwargs):
        connections.append((dsn, kwargs))
        return Connection()

    monkeypatch.setattr(config, "resolve_secret", lambda name: ("postgresql://admin@localhost/postgres", ".env"))
    monkeypatch.setattr(psycopg, "connect", connect)
    script = Path(__file__).resolve().parents[2] / "deploy" / "init_local_db.py"
    runpy.run_path(str(script))["initialize"]()
    assert len(connections) == 3
    assert connections[0][1]["autocommit"] is True
    assert [item[1] for item in statements if item[1]] == [["trip_planner"], ["trip_planner_test"]]
    creation = [
        query.as_string() for query, _, _ in statements
        if isinstance(query, sql.Composed)
    ]
    assert creation == ['create database "trip_planner"', 'create database "trip_planner_test"']
    assert len([query for query, _, options in statements if options.get("prepare") is False]) == 2
    assert not any("role" in query.lower() for query in creation)
