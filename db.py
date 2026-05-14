import os
import sqlite3
from datetime import datetime


class DB:
    def __init__(self, db_path: str):
        os.makedirs(os.path.dirname(db_path), exist_ok=True)
        self.conn = sqlite3.connect(db_path)
        self.conn.row_factory = sqlite3.Row
        self._setup()

    def _setup(self):
        cursor = self.conn.cursor()

        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS sessions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                started_at TEXT NOT NULL,
                ended_at TEXT
            )
            """
        )

        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id INTEGER NOT NULL,
                person_name TEXT NOT NULL,
                event_type TEXT NOT NULL,
                ts TEXT NOT NULL,
                confidence REAL,
                liveness_passed INTEGER DEFAULT 1
            )
            """
        )

        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS unknown_events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id INTEGER NOT NULL,
                image_path TEXT NOT NULL,
                ts TEXT NOT NULL
            )
            """
        )

        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS alerts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id INTEGER NOT NULL,
                alert_type TEXT NOT NULL,
                message TEXT NOT NULL,
                ts TEXT NOT NULL
            )
            """
        )

        self.conn.commit()
        self._ensure_column("events", "liveness_passed", "INTEGER DEFAULT 1")

    def _ensure_column(self, table_name: str, column_name: str, column_def: str):
        cursor = self.conn.cursor()
        cursor.execute(f"PRAGMA table_info({table_name})")
        columns = [row[1] for row in cursor.fetchall()]
        if column_name not in columns:
            cursor.execute(f"ALTER TABLE {table_name} ADD COLUMN {column_name} {column_def}")
            self.conn.commit()

    def start_session(self) -> int:
        cursor = self.conn.cursor()
        now = datetime.now().isoformat(timespec="seconds")
        cursor.execute(
            "INSERT INTO sessions (started_at) VALUES (?)",
            (now,),
        )
        self.conn.commit()
        return cursor.lastrowid

    def end_session(self, session_id: int):
        cursor = self.conn.cursor()
        now = datetime.now().isoformat(timespec="seconds")
        cursor.execute(
            "UPDATE sessions SET ended_at = ? WHERE id = ?",
            (now, session_id),
        )
        self.conn.commit()

    def add_event(
        self,
        session_id: int,
        person_name: str,
        event_type: str,
        confidence: float = None,
        liveness_passed: bool = True,
    ):
        cursor = self.conn.cursor()
        now = datetime.now().isoformat(timespec="seconds")
        cursor.execute(
            """
            INSERT INTO events (session_id, person_name, event_type, ts, confidence, liveness_passed)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                session_id,
                person_name,
                event_type,
                now,
                confidence,
                1 if liveness_passed else 0,
            ),
        )
        self.conn.commit()

    def add_unknown_event(self, session_id: int, image_path: str):
        cursor = self.conn.cursor()
        now = datetime.now().isoformat(timespec="seconds")
        cursor.execute(
            """
            INSERT INTO unknown_events (session_id, image_path, ts)
            VALUES (?, ?, ?)
            """,
            (session_id, image_path, now),
        )
        self.conn.commit()

    def add_alert(self, session_id: int, alert_type: str, message: str):
        cursor = self.conn.cursor()
        now = datetime.now().isoformat(timespec="seconds")
        cursor.execute(
            """
            INSERT INTO alerts (session_id, alert_type, message, ts)
            VALUES (?, ?, ?, ?)
            """,
            (session_id, alert_type, message, now),
        )
        self.conn.commit()

    def fetch_events(self, session_id: int):
        cursor = self.conn.cursor()
        cursor.execute(
            """
            SELECT session_id, person_name, event_type, ts, confidence, liveness_passed
            FROM events
            WHERE session_id = ?
            ORDER BY id ASC
            """,
            (session_id,),
        )
        return [dict(row) for row in cursor.fetchall()]

    def fetch_unknown_events(self, session_id: int):
        cursor = self.conn.cursor()
        cursor.execute(
            """
            SELECT session_id, image_path, ts
            FROM unknown_events
            WHERE session_id = ?
            ORDER BY id ASC
            """,
            (session_id,),
        )
        return [dict(row) for row in cursor.fetchall()]

    def fetch_alerts(self, session_id: int):
        cursor = self.conn.cursor()
        cursor.execute(
            """
            SELECT session_id, alert_type, message, ts
            FROM alerts
            WHERE session_id = ?
            ORDER BY id ASC
            """,
            (session_id,),
        )
        return [dict(row) for row in cursor.fetchall()]

    def get_last_event(self, session_id: int, person_name: str):
        cursor = self.conn.cursor()
        cursor.execute(
            """
            SELECT session_id, person_name, event_type, ts, confidence, liveness_passed
            FROM events
            WHERE session_id = ? AND person_name = ?
            ORDER BY id DESC
            LIMIT 1
            """,
            (session_id, person_name),
        )
        row = cursor.fetchone()
        return dict(row) if row else None

    def can_mark_out(self, session_id: int, person_name: str, min_minutes: int = 10) -> bool:
        cursor = self.conn.cursor()
        cursor.execute(
            """
            SELECT ts
            FROM events
            WHERE session_id = ? AND person_name = ? AND event_type = 'IN'
            ORDER BY id DESC
            LIMIT 1
            """,
            (session_id, person_name),
        )
        row = cursor.fetchone()
        if not row:
            return False

        try:
            last_in_time = datetime.fromisoformat(row["ts"])
        except Exception:
            return False

        now = datetime.now()
        diff_seconds = (now - last_in_time).total_seconds()
        return diff_seconds >= (min_minutes * 60)

    def close(self):
        self.conn.close()