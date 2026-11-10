"""Random, expiring and revocable installation sessions; tokens are never stored raw."""

import hashlib
import hmac
import secrets
import time
from pathlib import Path

from .store import Store


class Sessions:
    def __init__(self, path: Path, key: str):
        self.path, self.key = path, key

    def digest(self, token: str) -> str:
        return hmac.new(self.key.encode(), token.encode(), hashlib.sha256).hexdigest()

    def issue(self, lifetime: float = 28800) -> str:
        token = secrets.token_urlsafe(32)
        store = Store(self.path)
        try:
            with store.db:
                store.db.execute("DELETE FROM sessions WHERE expires<?", (time.time(),))
                store.db.execute(
                    "INSERT INTO sessions VALUES(?,?)",
                    (self.digest(token), time.time() + lifetime),
                )
            return token
        finally:
            store.db.close()

    def valid(self, token: str) -> bool:
        if len(token) > 100 or not token:
            return False
        store = Store(self.path)
        try:
            row = store.db.execute(
                "SELECT expires FROM sessions WHERE digest=?", (self.digest(token),)
            ).fetchone()
            return bool(row and float(row[0]) > time.time())
        finally:
            store.db.close()

    def revoke(self, token: str) -> None:
        store = Store(self.path)
        try:
            with store.db:
                store.db.execute(
                    "DELETE FROM sessions WHERE digest=?", (self.digest(token),)
                )
        finally:
            store.db.close()
