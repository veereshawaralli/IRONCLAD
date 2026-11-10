"""PostgreSQL compatibility adapter for the event-store SQL surface."""

from threading import Lock
from typing import Any, Self

_migration_lock = Lock()
_migrated: set[str] = set()

SCHEMA = """
CREATE TABLE IF NOT EXISTS runs(id TEXT PRIMARY KEY,input TEXT NOT NULL,ordinal BIGSERIAL);
CREATE TABLE IF NOT EXISTS events(run_id TEXT,seq INTEGER,message TEXT NOT NULL,PRIMARY KEY(run_id,seq));
CREATE TABLE IF NOT EXISTS workers(id TEXT PRIMARY KEY,seen DOUBLE PRECISION NOT NULL,sandbox INTEGER NOT NULL);
        CREATE TABLE IF NOT EXISTS sessions(digest TEXT PRIMARY KEY,expires DOUBLE PRECISION NOT NULL);
        CREATE TABLE IF NOT EXISTS charges(run_id TEXT,amount DOUBLE PRECISION NOT NULL);
CREATE TABLE IF NOT EXISTS jobs(id TEXT PRIMARY KEY,status TEXT NOT NULL,ordinal BIGSERIAL);
ALTER TABLE jobs ADD COLUMN IF NOT EXISTS owner TEXT;
ALTER TABLE jobs ADD COLUMN IF NOT EXISTS lease_until DOUBLE PRECISION;
CREATE TABLE IF NOT EXISTS settings(id INTEGER PRIMARY KEY,value TEXT NOT NULL);
CREATE OR REPLACE FUNCTION ironclad_immutable_events() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN RAISE EXCEPTION 'append-only'; END $$;
DROP TRIGGER IF EXISTS immutable_events_update ON events;
CREATE TRIGGER immutable_events_update BEFORE UPDATE OR DELETE ON events FOR EACH ROW EXECUTE FUNCTION ironclad_immutable_events();
"""


class PostgresConnection:
    def __init__(self, dsn: str):
        import psycopg

        self.connection = psycopg.connect(dsn, autocommit=True, connect_timeout=5)
        with _migration_lock:
            if dsn not in _migrated:
                self.connection.execute("SELECT pg_advisory_lock(710413)")
                try:
                    self.connection.execute(SCHEMA)
                    _migrated.add(dsn)
                finally:
                    self.connection.execute("SELECT pg_advisory_unlock(710413)")
        self.context: Any = None

    def execute(self, sql: str, args: tuple[Any, ...] = ()) -> Any:
        if sql == "BEGIN IMMEDIATE":
            self.connection.execute("BEGIN")
            # Single installation-level advisory lock for budget and queue claims.
            return self.connection.execute("SELECT pg_advisory_xact_lock(710412)")
        if sql.startswith("SELECT owner,lease_until,status FROM jobs"):
            sql += " FOR UPDATE"
        sql = sql.replace("ORDER BY rowid", "ORDER BY ordinal")
        sql = sql.replace(
            "INSERT OR IGNORE INTO runs VALUES (?,?)",
            "INSERT INTO runs(id,input) VALUES (?,?) ON CONFLICT(id) DO NOTHING",
        )
        sql = sql.replace(
            "INSERT INTO jobs VALUES (?, 'queued')",
            "INSERT INTO jobs(id,status) VALUES (?, 'queued')",
        )
        sql = sql.replace(
            "INSERT INTO jobs VALUES(?,'queued')",
            "INSERT INTO jobs(id,status) VALUES(?,'queued')",
        )
        return self.connection.execute(sql.replace("?", "%s"), args)

    def __enter__(self) -> Self:
        self.context = self.connection.transaction()
        self.context.__enter__()
        return self

    def __exit__(self, *args: object) -> Any:
        return self.context.__exit__(*args)

    def commit(self) -> None:
        self.connection.execute("COMMIT")

    def rollback(self) -> None:
        self.connection.execute("ROLLBACK")

    def close(self) -> None:
        self.connection.close()
