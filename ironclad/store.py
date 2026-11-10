import json
import os
import sqlite3
from pathlib import Path

from .postgres import PostgresConnection
from .schema import Message


class Store:
    def __init__(self, path: Path):
        path.parent.mkdir(parents=True, exist_ok=True)
        self.db: sqlite3.Connection | PostgresConnection
        dsn = os.environ.get("IRONCLAD_DATABASE_URL")
        if dsn:
            self.db = PostgresConnection(dsn)
            return
        self.db = sqlite3.connect(path)
        self.db.execute("PRAGMA journal_mode=WAL")
        self.db.executescript("""
        CREATE TABLE IF NOT EXISTS jobs(id TEXT PRIMARY KEY, status TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS settings(id INTEGER PRIMARY KEY, value TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS charges(run_id TEXT, amount REAL NOT NULL);
        CREATE TABLE IF NOT EXISTS runs(id TEXT PRIMARY KEY, input TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS events(run_id TEXT, seq INTEGER, message TEXT NOT NULL,
          PRIMARY KEY(run_id, seq));
        CREATE TRIGGER IF NOT EXISTS immutable_events_update BEFORE UPDATE ON events
          BEGIN SELECT RAISE(ABORT, 'append-only'); END;
        CREATE TRIGGER IF NOT EXISTS immutable_events_delete BEFORE DELETE ON events
          BEGIN SELECT RAISE(ABORT, 'append-only'); END;
        """)

    def begin(self, run_id: str, data: dict[str, object]) -> dict[str, object]:
        with self.db:
            self.db.execute(
                "INSERT OR IGNORE INTO runs VALUES (?,?)", (run_id, json.dumps(data))
            )
        row = self.db.execute("SELECT input FROM runs WHERE id=?", (run_id,)).fetchone()
        return dict(json.loads(row[0]))

    def append(self, event: Message) -> None:
        with self.db:
            self.db.execute(
                "INSERT INTO events VALUES (?,?,?)",
                (event.run_id, event.seq, event.model_dump_json()),
            )

        import logging

        logging.getLogger("ironclad.events").info(
            json.dumps(
                {
                    "run_id": event.run_id,
                    "seq": event.seq,
                    "agent": event.agent,
                    "kind": event.kind,
                    "duration_ms": event.duration_ms,
                }
            )
        )

        from .telemetry import record

        record(event)
        redis_url = os.environ.get("IRONCLAD_REDIS_URL")
        if redis_url:
            import redis

            from .bus import RedisBus

            try:
                client = redis.Redis.from_url(
                    redis_url, socket_timeout=2, socket_connect_timeout=2
                )
                bus = RedisBus(client)
                for prior in self.events(event.run_id):
                    bus.publish(prior)
                client.close()
            except redis.RedisError:
                logging.getLogger("ironclad.events").warning(
                    "Redis relay unavailable; durable event log retained"
                )

    def events(self, run_id: str) -> list[Message]:
        return [
            Message.model_validate_json(r[0])
            for r in self.db.execute(
                "SELECT message FROM events WHERE run_id=? ORDER BY seq", (run_id,)
            )
        ]

    def input(self, run_id: str) -> dict[str, object]:
        row = self.db.execute("SELECT input FROM runs WHERE id=?", (run_id,)).fetchone()
        if not row:
            raise ValueError("Unknown run")
        return dict(json.loads(row[0]))

    def reserve(self, run_id: str, amount: float, cap: float, calls: int) -> None:
        self.db.execute("BEGIN IMMEDIATE")
        try:
            spent, used = self.db.execute(
                "SELECT COALESCE(SUM(amount),0),COUNT(*) FROM charges WHERE run_id=?",
                (run_id,),
            ).fetchone()
            if spent + amount > cap or used >= calls:
                raise ValueError("Durable model budget exhausted")
            self.db.execute("INSERT INTO charges VALUES (?,?)", (run_id, amount))
            self.db.commit()
        except BaseException:
            self.db.rollback()
            raise

    def list_runs(self) -> list[dict[str, object]]:
        result: list[dict[str, object]] = []
        for rid, raw in self.db.execute(
            "SELECT id,input FROM runs ORDER BY rowid DESC LIMIT 1000"
        ):
            data = json.loads(raw)
            events = self.events(rid)
            job = self.db.execute(
                "SELECT status FROM jobs WHERE id=?", (rid,)
            ).fetchone()
            amount = self.db.execute(
                "SELECT COALESCE(SUM(amount),0) FROM charges WHERE run_id=?", (rid,)
            ).fetchone()[0]
            result.append(
                {
                    "id": rid,
                    "mode": data.get("mode", "demo"),
                    "summary": str(data.get("log", "")).splitlines()[-1]
                    if data.get("log")
                    else "Incident",
                    "status": events[-1].kind
                    if events
                    else (job[0] if job else "queued"),
                    "steps": len(events),
                    "reserved_usd": amount,
                    "created_at": events[0].timestamp if events else "",
                }
            )
        return result

    def queue(self, rid: str) -> None:
        with self.db:
            self.db.execute("INSERT INTO jobs VALUES (?, 'queued')", (rid,))

    def claim(self) -> str | None:
        self.db.execute("BEGIN IMMEDIATE")
        row = self.db.execute(
            "SELECT id FROM jobs WHERE status='queued' ORDER BY rowid LIMIT 1"
        ).fetchone()
        if row:
            self.db.execute("UPDATE jobs SET status='running' WHERE id=?", (row[0],))
        self.db.commit()
        return str(row[0]) if row else None

    def finish(self, rid: str) -> None:
        with self.db:
            self.db.execute("UPDATE jobs SET status='finished' WHERE id=?", (rid,))

    def settings(self) -> dict[str, object]:
        row = self.db.execute("SELECT value FROM settings WHERE id=1").fetchone()
        return dict(json.loads(row[0])) if row else {}

    def save_settings(self, data: dict[str, object]) -> None:
        with self.db:
            self.db.execute(
                "INSERT INTO settings VALUES(1,?) ON CONFLICT(id) DO UPDATE SET value=excluded.value",
                (json.dumps(data),),
            )
