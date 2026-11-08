import json
import sqlite3
import time
from contextlib import contextmanager
from datetime import UTC, datetime
from uuid import uuid4


class BudgetExceeded(Exception):
    pass


class SearchInProgress(Exception):
    pass


class Store:
    """Single-host storage. Atomic reservations prevent concurrent budget overshoot."""

    def __init__(self, path):
        self.path = path
        path.parent.mkdir(parents=True, exist_ok=True)
        with self.connection() as db:
            db.execute("PRAGMA journal_mode=WAL")
            db.executescript("""
                CREATE TABLE IF NOT EXISTS trips (
                    id TEXT PRIMARY KEY, brief TEXT NOT NULL, created_at REAL NOT NULL
                );
                CREATE TABLE IF NOT EXISTS calls (
                    id TEXT PRIMARY KEY, trip_id TEXT NOT NULL, provider TEXT NOT NULL,
                    operation TEXT NOT NULL, started_at REAL NOT NULL,
                    status TEXT NOT NULL, request_id TEXT
                );
                CREATE INDEX IF NOT EXISTS calls_trip ON calls(trip_id);
                CREATE INDEX IF NOT EXISTS calls_time ON calls(started_at);
                CREATE TABLE IF NOT EXISTS search_cache (
                    key TEXT PRIMARY KEY, payload TEXT, expires_at REAL NOT NULL DEFAULT 0,
                    lease_id TEXT, locked_until REAL NOT NULL DEFAULT 0
                );
            """)

    @contextmanager
    def connection(self):
        db = sqlite3.connect(self.path, timeout=10)
        db.row_factory = sqlite3.Row
        try:
            with db:
                yield db
        finally:
            db.close()

    def create_trip(self, brief):
        trip_id = str(uuid4())
        with self.connection() as db:
            db.execute(
                "INSERT INTO trips VALUES (?, ?, ?)", (trip_id, json.dumps(brief), time.time())
            )
        return trip_id

    def get_trip(self, trip_id):
        with self.connection() as db:
            row = db.execute("SELECT brief FROM trips WHERE id=?", (trip_id,)).fetchone()
        return json.loads(row["brief"]) if row else None

    @staticmethod
    def day_start():
        return datetime.now(UTC).replace(hour=0, minute=0, second=0, microsecond=0).timestamp()

    def claim(self, key, trip_id, settings, operation):
        now = time.time()
        with self.connection() as db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute("SELECT * FROM search_cache WHERE key=?", (key,)).fetchone()
            cache_allowed = settings.provider == "mock" or settings.supplier_cache
            if row and cache_allowed and row["payload"] and row["expires_at"] > now:
                return None, json.loads(row["payload"])
            if row and row["locked_until"] > now:
                raise SearchInProgress("Identical search is already running")
            trip_count = db.execute(
                "SELECT COUNT(*) FROM calls WHERE trip_id=?", (trip_id,)
            ).fetchone()[0]
            day_count = db.execute(
                "SELECT COUNT(*) FROM calls WHERE started_at>=?", (self.day_start(),)
            ).fetchone()[0]
            if trip_count >= settings.trip_limit:
                raise BudgetExceeded("Trip provider-call limit reached")
            if day_count >= settings.daily_limit:
                raise BudgetExceeded("Application daily provider-call limit reached")
            call_id = str(uuid4())
            db.execute(
                "INSERT INTO calls VALUES (?, ?, ?, ?, ?, 'reserved', NULL)",
                (call_id, trip_id, settings.provider, operation, now),
            )
            db.execute(
                """INSERT INTO search_cache (key, lease_id, locked_until) VALUES (?, ?, ?)
                          ON CONFLICT(key) DO UPDATE SET lease_id=excluded.lease_id,
                          locked_until=excluded.locked_until, payload=NULL, expires_at=0""",
                (key, call_id, now + settings.timeout + 15),
            )
            return call_id, None

    def finish(self, key, call_id, payload, ttl, status, request_id=None):
        now = time.time()
        expiry = min(now + ttl, payload.get("valid_until", now + ttl)) if payload else 0
        cached = json.dumps(payload) if payload is not None and ttl > 0 else None
        with self.connection() as db:
            db.execute(
                "UPDATE calls SET status=?, request_id=? WHERE id=?", (status, request_id, call_id)
            )
            # A late worker cannot overwrite a newer search's lease or result.
            db.execute(
                """UPDATE search_cache SET payload=?, expires_at=?, locked_until=0,
                          lease_id=NULL WHERE key=? AND lease_id=?""",
                (cached, expiry, key, call_id),
            )

    def attempts(self, trip_id):
        # Operational evidence only; no inventory, prices, request bodies or credentials.
        with self.connection() as db:
            rows = db.execute(
                """SELECT id, provider, operation, started_at, status, request_id
                   FROM calls WHERE trip_id=? ORDER BY started_at, id""",
                (trip_id,),
            ).fetchall()
        return [dict(row) for row in rows]

    def usage(self, trip_id, settings):
        with self.connection() as db:
            rows = db.execute(
                """SELECT provider, operation, status, COUNT(*) AS count
                                 FROM calls WHERE trip_id=?
                                 GROUP BY provider, operation, status""",
                (trip_id,),
            ).fetchall()
            day_count = db.execute(
                "SELECT COUNT(*) FROM calls WHERE started_at>=?", (self.day_start(),)
            ).fetchone()[0]
        return {
            "trip_calls_reserved": sum(row["count"] for row in rows),
            "trip_call_limit": settings.trip_limit,
            "application_calls_reserved_today": day_count,
            "application_daily_call_limit": settings.daily_limit,
            "by_operation": [dict(row) for row in rows],
            "llm_calls": 0,
            "billing_note": "Local call allowances, not supplier billing or a dollar guarantee.",
        }
