"""Backup archive creation, validated restore, and JSON export."""

from __future__ import annotations

import json
import shutil
import sqlite3
import tempfile
import zipfile
from pathlib import Path

from task_stamps import __version__
from task_stamps.config import DB_FILE_NAME, AppConfig
from task_stamps.data.database import Database
from task_stamps.data.migrations import SCHEMA_VERSION
from task_stamps.domain.exceptions import BackupError
from task_stamps.utilities.clock import Clock
from task_stamps.utilities.logging_setup import get_logger

logger = get_logger("backup")

MANIFEST_NAME = "manifest.json"
DB_ARCHIVE_PATH = f"database/{DB_FILE_NAME}"

_EXPORT_TABLES = (
    "worlds",
    "characters",
    "character_stamps",
    "habit_tasks",
    "character_assignments",
    "task_completions",
    "stamp_placements",
    "daily_bosses",
    "pause_periods",
    "assets",
    "asset_versions",
    "app_settings",
    "vice_rewards",
    "vice_chests",
    "task_misses",
)


class BackupService:
    def __init__(self, config: AppConfig, db: Database, clock: Clock) -> None:
        self.config = config
        self.db = db
        self.clock = clock

    # -- backup -------------------------------------------------------------

    def create_backup(self, tag: str = "backup") -> Path:
        """Write a single archive with the database, all managed assets,
        settings (stored inside the database) and schema metadata."""
        stamp = self.clock.now().strftime("%Y%m%d_%H%M%S")
        target = self.config.backups_dir / f"task_stamps_{tag}_{stamp}.zip"
        manifest = {
            "app": "task-stamps",
            "app_version": __version__,
            "schema_version": SCHEMA_VERSION,
            "created_at": self.clock.now().isoformat(),
        }
        try:
            with tempfile.TemporaryDirectory() as temp_dir:
                snapshot = Path(temp_dir) / DB_FILE_NAME
                self._snapshot_database(snapshot)
                with zipfile.ZipFile(target, "w", zipfile.ZIP_DEFLATED) as archive:
                    archive.writestr(MANIFEST_NAME, json.dumps(manifest, indent=2))
                    archive.write(snapshot, DB_ARCHIVE_PATH)
                    for file in sorted(self.config.assets_dir.rglob("*")):
                        if file.is_file():
                            archive.write(
                                file, file.relative_to(self.config.data_dir).as_posix()
                            )
                    # World Hub provenance (pointer + receipts) is user-relevant
                    # metadata; installed publication caches are recoverable
                    # from the Hub and deliberately excluded.
                    worldhub_dir = self.config.data_dir / "worldhub-content"
                    for name in ["current.json", *(
                        f"receipts/{p.name}" for p in sorted((worldhub_dir / "receipts").glob("*.json"))
                        if (worldhub_dir / "receipts").is_dir()
                    )]:
                        candidate = worldhub_dir / name
                        if candidate.is_file():
                            archive.write(
                                candidate,
                                candidate.relative_to(self.config.data_dir).as_posix(),
                            )
        except OSError as error:
            logger.exception("Backup failed")
            raise BackupError("Creating the backup archive failed.") from error
        logger.info("Backup created at %s", target)
        return target

    def _snapshot_database(self, destination: Path) -> None:
        """Consistent copy via the SQLite online backup API."""
        with sqlite3.connect(destination) as copy:
            self.db.connection.backup(copy)

    # -- restore -----------------------------------------------------------

    def validate_archive(self, archive_path: Path) -> dict[str, object]:
        if not archive_path.is_file() or not zipfile.is_zipfile(archive_path):
            raise BackupError("The selected file is not a valid backup archive.")
        try:
            with zipfile.ZipFile(archive_path) as archive:
                names = set(archive.namelist())
                if MANIFEST_NAME not in names or DB_ARCHIVE_PATH not in names:
                    raise BackupError(
                        "The archive is missing required backup contents."
                    )
                manifest = json.loads(archive.read(MANIFEST_NAME))
        except (zipfile.BadZipFile, json.JSONDecodeError, KeyError) as error:
            raise BackupError("The backup archive is corrupt.") from error
        if manifest.get("app") != "task-stamps":
            raise BackupError("This archive was not created by Task Stamps.")
        schema = manifest.get("schema_version")
        if not isinstance(schema, int) or schema > SCHEMA_VERSION:
            raise BackupError(
                "This backup was made by a newer version of the app and "
                "cannot be restored here."
            )
        return manifest

    def restore_backup(self, archive_path: Path) -> None:
        """Validate, protect current data with a safety backup, then swap in
        the archived database and assets together."""
        self.validate_archive(archive_path)
        self.create_backup(tag="pre_restore")

        with tempfile.TemporaryDirectory() as temp_dir:
            staging = Path(temp_dir)
            with zipfile.ZipFile(archive_path) as archive:
                for member in archive.namelist():
                    target = (staging / member).resolve()
                    if staging.resolve() not in target.parents:
                        raise BackupError("The archive contains unsafe paths.")
                archive.extractall(staging)
            staged_db = staging / DB_ARCHIVE_PATH
            try:
                probe = sqlite3.connect(staged_db)
                probe.execute("SELECT count(*) FROM sqlite_master")
                probe.close()
            except sqlite3.Error as error:
                raise BackupError("The archived database is unreadable.") from error

            self.db.close()
            try:
                shutil.copy2(staged_db, self.config.database_path)
                staged_assets = staging / "assets"
                if self.config.assets_dir.exists():
                    shutil.rmtree(self.config.assets_dir)
                if staged_assets.exists():
                    shutil.copytree(staged_assets, self.config.assets_dir)
                else:
                    self.config.assets_dir.mkdir(parents=True, exist_ok=True)
            finally:
                self.config.ensure_directories()
                self.db.reconnect()
        self.db.migrate()
        logger.info("Restore completed from %s", archive_path)

    def factory_reset(self) -> None:
        """Delete all game data and assets, then create a fresh empty store.

        Backups and logs are deliberately retained so a reset does not remove
        the user's recovery options or diagnostics.
        """
        self.db.close()
        try:
            for suffix in ("", "-wal", "-shm"):
                Path(f"{self.config.database_path}{suffix}").unlink(missing_ok=True)
            if self.config.assets_dir.exists():
                shutil.rmtree(self.config.assets_dir)
            self.config.ensure_directories()
            self.db.reconnect()
            self.db.migrate()
        except OSError as error:
            logger.exception("Factory reset failed")
            self.config.ensure_directories()
            self.db.reconnect()
            self.db.migrate()
            raise BackupError(
                "Resetting the app data failed. See the log for details."
            ) from error
        logger.info("Factory reset completed")

    # -- export -------------------------------------------------------------

    def export_json(self, target: Path | None = None) -> Path:
        """Human-readable JSON export (metadata only, no binary payloads)."""
        stamp = self.clock.now().strftime("%Y%m%d_%H%M%S")
        target = target or self.config.backups_dir / f"task_stamps_export_{stamp}.json"
        payload: dict[str, object] = {
            "app": "task-stamps",
            "app_version": __version__,
            "schema_version": SCHEMA_VERSION,
            "exported_at": self.clock.now().isoformat(),
        }
        for table in _EXPORT_TABLES:
            rows = self.db.query_all(f"SELECT * FROM {table}")
            payload[table] = [dict(row) for row in rows]
        target.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        logger.info("Exported data to %s", target)
        return target
