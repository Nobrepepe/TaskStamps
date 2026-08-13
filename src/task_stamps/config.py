"""Application configuration and data-directory resolution."""

from __future__ import annotations

import os
import sys
from dataclasses import dataclass
from pathlib import Path

APP_DIR_NAME = "task-stamps"
DATA_DIR_ENV = "TASK_STAMPS_DATA_DIR"
DB_FILE_NAME = "tasks_app.sqlite3"


@dataclass(frozen=True)
class AppConfig:
    """Resolved filesystem layout for one application instance."""

    data_dir: Path

    @property
    def database_dir(self) -> Path:
        return self.data_dir / "database"

    @property
    def database_path(self) -> Path:
        return self.database_dir / DB_FILE_NAME

    @property
    def assets_dir(self) -> Path:
        return self.data_dir / "assets"

    @property
    def backups_dir(self) -> Path:
        return self.data_dir / "backups"

    @property
    def logs_dir(self) -> Path:
        return self.data_dir / "logs"

    def asset_subdir(self, name: str) -> Path:
        return self.assets_dir / name

    def ensure_directories(self) -> None:
        for path in (
            self.data_dir,
            self.database_dir,
            self.assets_dir,
            self.assets_dir / "worlds",
            self.assets_dir / "characters",
            self.assets_dir / "stamps",
            self.assets_dir / "sounds",
            self.backups_dir,
            self.logs_dir,
        ):
            path.mkdir(parents=True, exist_ok=True)


def default_data_dir() -> Path:
    """Per-user application data directory.

    Override with the TASK_STAMPS_DATA_DIR environment variable
    (used for development / local data mode).
    """
    override = os.environ.get(DATA_DIR_ENV)
    if override:
        return Path(override).expanduser()
    if sys.platform == "win32":
        base = Path(os.environ.get("APPDATA", Path.home() / "AppData" / "Roaming"))
        return base / APP_DIR_NAME / "app_data"
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Application Support" / APP_DIR_NAME / "app_data"
    xdg = os.environ.get("XDG_DATA_HOME")
    base = Path(xdg).expanduser() if xdg else Path.home() / ".local" / "share"
    return base / APP_DIR_NAME / "app_data"


def load_config(data_dir: Path | None = None) -> AppConfig:
    config = AppConfig(data_dir=data_dir or default_data_dir())
    config.ensure_directories()
    return config
