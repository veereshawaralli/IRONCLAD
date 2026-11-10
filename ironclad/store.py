import json
import sqlite3
from pathlib import Path

from .schema import Message


class Store:
    def __init__(self, path: Path):
        path.parent.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(path)
        self.db.execute("PRAGMA journal_mode=WAL")
        self.db.executescript("""
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
