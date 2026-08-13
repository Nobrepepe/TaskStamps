"""SQLite access with a re-entrant transaction context and migration runner."""

from __future__ import annotations

import sqlite3
import threading
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator, Sequence

from task_stamps.data.migrations import MIGRATIONS, SCHEMA_VERSION
from task_stamps.domain.exceptions import DataAccessError
from task_stamps.utilities.logging_setup import get_logger

logger = get_logger("database")


class Database:
    """One shared connection guarded by an RLock.

    Flet event handlers may run on worker threads, so every statement goes
    through the lock. ``transaction()`` nests: only the outermost level
    commits or rolls back, which lets services compose atomically.
    """

    def __init__(self, path: Path) -> None:
        self.path = path
        self._lock = threading.RLock()
        self._depth = 0
        self._conn: sqlite3.Connection | None = None
        self._connect()

    def _connect(self) -> None:
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            conn = sqlite3.connect(
                self.path, check_same_thread=False, isolation_level=None
            )
            conn.row_factory = sqlite3.Row
            conn.execute("PRAGMA foreign_keys = ON")
            conn.execute("PRAGMA journal_mode = WAL")
            self._conn = conn
        except sqlite3.Error as error:
            logger.exception("Cannot open database at %s", self.path)
            raise DataAccessError(
                "The local database could not be opened. See the log for details."
            ) from error

    @property
    def connection(self) -> sqlite3.Connection:
        if self._conn is None:
            raise DataAccessError("The database connection is closed.")
        return self._conn

    def close(self) -> None:
        with self._lock:
            if self._conn is not None:
                self._conn.close()
                self._conn = None

    def reconnect(self) -> None:
        with self._lock:
            self.close()
            self._connect()

    @contextmanager
    def transaction(self) -> Iterator[sqlite3.Connection]:
        with self._lock:
            outermost = self._depth == 0
            if outermost:
                self.connection.execute("BEGIN IMMEDIATE")
            self._depth += 1
            try:
                yield self.connection
            except Exception:
                self._depth -= 1
                if outermost:
                    self.connection.execute("ROLLBACK")
                raise
            else:
                self._depth -= 1
                if outermost:
                    self.connection.execute("COMMIT")

    def execute(self, sql: str, params: Sequence[Any] = ()) -> sqlite3.Cursor:
        with self._lock:
            return self.connection.execute(sql, params)

    def query_one(self, sql: str, params: Sequence[Any] = ()) -> sqlite3.Row | None:
        with self._lock:
            return self.connection.execute(sql, params).fetchone()

    def query_all(self, sql: str, params: Sequence[Any] = ()) -> list[sqlite3.Row]:
        with self._lock:
            return self.connection.execute(sql, params).fetchall()

    def migrate(self) -> None:
        """Apply pending migrations. Called automatically at startup."""
        with self._lock:
            current = self.connection.execute("PRAGMA user_version").fetchone()[0]
            for version, statements in MIGRATIONS:
                if version <= current:
                    continue
                logger.info("Applying migration %s", version)
                try:
                    with self.transaction():
                        # executescript() would implicitly COMMIT the open
                        # transaction, so statements are executed one by one.
                        for statement in statements.split(";"):
                            if statement.strip():
                                self.connection.execute(statement)
                        self.connection.execute(f"PRAGMA user_version = {version}")
                except sqlite3.Error as error:
                    logger.exception("Migration %s failed", version)
                    raise DataAccessError(
                        "A database migration failed; your data was left unchanged. "
                        "See the log for details."
                    ) from error
            self.connection.execute(
                "INSERT INTO app_state(key, value, updated_at) VALUES('schema_version', ?, datetime('now')) "
                "ON CONFLICT(key) DO UPDATE SET value = excluded.value, updated_at = excluded.updated_at",
                (str(SCHEMA_VERSION),),
            )
