"""Local PostgreSQL backend with the same contract as server-side Supabase."""

from __future__ import annotations

import json
import logging
from typing import Any

from utils.storage.accounts import CloudStore, StorageError

logger = logging.getLogger(__name__)
TABLES = {
    "planner_accounts": {"owner", "state"},
    "planner_feedback": {"actor", "plan_id", "poi_id", "rating", "comment", "created_at"},
    "planner_guidance": {"feedback_id", "instruction", "reason", "status", "reviewer"},
}


class PostgresStore(CloudStore):
    """Trusted server-only database access; never take a DSN from a UI widget."""

    def __init__(self, dsn: str):
        self.dsn = dsn

    def request(self, method: str, resource: str, **kwargs: Any) -> Any:
        import psycopg
        from psycopg import sql
        from psycopg.rows import dict_row
        from psycopg.types.json import Jsonb

        params = kwargs.get("params", {})
        payload = kwargs.get("json", {})
        values: list[Any] = []
        if resource.startswith("rpc/"):
            function = resource.removeprefix("rpc/")
            if function not in ("planner_poi_scores", "planner_feedback_stats"):
                raise ValueError("Unknown database function.")
            query = sql.SQL("select * from public.{}()").format(sql.Identifier(function))
        elif resource in TABLES:
            table = sql.Identifier("public", resource)
            fields = TABLES[resource] | {"id", "created_at"}
            predicates = []
            for field, value in params.items():
                if field in fields:
                    if not isinstance(value, str) or not value.startswith("eq."):
                        raise ValueError("Only equality filters are supported.")
                    predicates.append(sql.SQL("{} = %s").format(sql.Identifier(field)))
                    values.append(value[3:])
            where = sql.SQL(" where {}").format(sql.SQL(" and ").join(predicates)) if predicates else sql.SQL("")
            if method == "GET":
                query = sql.SQL("select * from {}").format(table) + where
                ordering = params.get("order", "")
                if ordering:
                    if ordering not in ("created_at", "created_at.desc"):
                        raise ValueError("Invalid ordering.")
                    query += sql.SQL(" order by created_at ") + sql.SQL("desc" if ordering.endswith(".desc") else "asc")
                limit = min(int(params.get("limit", 20)), 20)
                query += sql.SQL(" limit %s")
                values.append(limit)
            elif method == "POST":
                if not payload or set(payload) - TABLES[resource]:
                    raise ValueError("Invalid database record fields.")
                columns = list(payload)
                values = [Jsonb(value) if isinstance(value, dict) else value for value in payload.values()]
                conflict = {
                    "planner_accounts": ["owner"],
                    "planner_feedback": ["actor", "plan_id", "poi_id"],
                    "planner_guidance": ["feedback_id"],
                }[resource]
                update_columns = [column for column in columns if column not in conflict]
                updates = sql.SQL(", ").join(
                    sql.SQL("{} = excluded.{}").format(sql.Identifier(column), sql.Identifier(column))
                    for column in update_columns
                )
                query = sql.SQL(
                    "insert into {} ({}) values ({}) on conflict ({}) do update set {} returning *"
                ).format(
                    table, sql.SQL(", ").join(map(sql.Identifier, columns)),
                    sql.SQL(", ").join(sql.Placeholder() for _ in columns),
                    sql.SQL(", ").join(map(sql.Identifier, conflict)), updates,
                )
            elif method == "PATCH":
                if not predicates or not payload or set(payload) - TABLES[resource]:
                    raise ValueError("A filtered, valid update is required.")
                assignments = sql.SQL(", ").join(
                    sql.SQL("{} = %s").format(sql.Identifier(column)) for column in payload
                )
                values = list(payload.values()) + values
                query = sql.SQL("update {} set {}").format(table, assignments) + where + sql.SQL(" returning *")
            else:
                raise ValueError("Unsupported storage method.")
        else:
            raise ValueError("Unknown database table.")
        try:
            with psycopg.connect(self.dsn, connect_timeout=5) as connection:
                with connection.cursor(row_factory=dict_row) as cursor:
                    cursor.execute("set statement_timeout = '15s'")
                    cursor.execute(query, values)
                    rows = cursor.fetchall()
            return json.loads(json.dumps(rows, default=str))
        except psycopg.Error as error:
            logger.warning("Local PostgreSQL operation failed (%s).", type(error).__name__)
            raise StorageError("Local PostgreSQL is unavailable. Check DATABASE_URL and apply the schema.") from None
