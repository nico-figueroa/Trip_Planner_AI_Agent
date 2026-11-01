"""Create dedicated development/test databases and apply only application schema.

No roles are created or altered. Administrator credentials stay in .env/pgpass.
"""

from pathlib import Path
import sys

import psycopg
from psycopg import sql
from psycopg.conninfo import make_conninfo

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "trip-planner"))
from utils.core.config import resolve_secret


def initialize() -> None:
    administrator = resolve_secret("POSTGRES_ADMIN_URL")[0] or "postgresql://postgres@localhost:5432/postgres"
    databases = ("trip_planner", "trip_planner_test")
    schema = Path(__file__).with_name("schema.sql").read_bytes()
    try:
        with psycopg.connect(administrator, autocommit=True, connect_timeout=5) as connection:
            for database in databases:
                exists = connection.execute(
                    "select 1 from pg_database where datname = %s", [database],
                ).fetchone()
                if not exists:
                    connection.execute(sql.SQL("create database {}").format(sql.Identifier(database)))
        for database in databases:
            with psycopg.connect(make_conninfo(administrator, dbname=database), connect_timeout=5) as connection:
                connection.execute(schema, prepare=False)
            print(f"Application schema ready in {database}; no role changes made.")
    except psycopg.Error:
        raise SystemExit(
            "Database setup failed. Configure PostgreSQL administrator credentials in "
            "POSTGRES_ADMIN_URL or pgpass and verify CREATE DATABASE permission. "
            "No credentials or server error details are displayed."
        ) from None


if __name__ == "__main__":
    initialize()
