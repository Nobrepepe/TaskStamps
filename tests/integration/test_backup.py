"""Backup, restore validation, and JSON export."""

from __future__ import annotations

import json
import zipfile

import pytest

from task_stamps.domain.exceptions import BackupError
from tests.helpers import EVERY_DAY, make_character, make_task, make_world


def _seed(container, clock, source_files) -> None:
    world = make_world(container)
    make_character(container, world.id, "Alpha", source_files)
    task = make_task(container, weekdays=EVERY_DAY)
    container.completion_service.complete_task(task.id)


def test_backup_includes_database_and_assets(container, clock, source_files):
    _seed(container, clock, source_files)
    archive_path = container.backup_service.create_backup()
    assert archive_path.is_file()
    with zipfile.ZipFile(archive_path) as archive:
        names = archive.namelist()
        assert "manifest.json" in names
        assert "database/tasks_app.sqlite3" in names
        asset_entries = [name for name in names if name.startswith("assets/")]
        assert len(asset_entries) >= 16  # portrait + 15 stamps
        manifest = json.loads(archive.read("manifest.json"))
        assert manifest["app"] == "task-stamps"
        assert isinstance(manifest["schema_version"], int)


def test_restore_rejects_invalid_archives(container, tmp_path):
    not_a_zip = tmp_path / "junk.zip"
    not_a_zip.write_text("garbage")
    with pytest.raises(BackupError):
        container.backup_service.restore_backup(not_a_zip)

    missing = tmp_path / "nowhere.zip"
    with pytest.raises(BackupError):
        container.backup_service.restore_backup(missing)

    empty_zip = tmp_path / "empty.zip"
    with zipfile.ZipFile(empty_zip, "w") as archive:
        archive.writestr("hello.txt", "hi")
    with pytest.raises(BackupError):
        container.backup_service.restore_backup(empty_zip)

    foreign = tmp_path / "foreign.zip"
    with zipfile.ZipFile(foreign, "w") as archive:
        archive.writestr("manifest.json", json.dumps({"app": "other", "schema_version": 1}))
        archive.writestr("database/tasks_app.sqlite3", b"")
    with pytest.raises(BackupError):
        container.backup_service.restore_backup(foreign)


def test_backup_restore_roundtrip(container, clock, source_files):
    _seed(container, clock, source_files)
    board_before = container.board_service.load_board(clock.today())
    archive_path = container.backup_service.create_backup()

    # Wreck the live data, then restore.
    container.db.execute("DELETE FROM stamp_placements")
    assert container.board_service.load_board(clock.today()) == []
    container.backup_service.restore_backup(archive_path)

    board_after = container.board_service.load_board(clock.today())
    assert len(board_after) == len(board_before) == 1
    restored = board_after[0]
    assert restored.placement.x_normalized == board_before[0].placement.x_normalized
    asset_file = container.config.data_dir / restored.image_relative_path
    assert asset_file.is_file()
    # A safety backup of the pre-restore state was created automatically.
    safety = list(container.config.backups_dir.glob("*pre_restore*.zip"))
    assert safety


def test_json_export_contains_all_entities(container, clock, source_files):
    _seed(container, clock, source_files)
    export_path = container.backup_service.export_json()
    payload = json.loads(export_path.read_text(encoding="utf-8"))
    for table in (
        "worlds",
        "characters",
        "character_stamps",
        "habit_tasks",
        "character_assignments",
        "task_completions",
        "stamp_placements",
    ):
        assert table in payload
    assert len(payload["worlds"]) == 1
    assert len(payload["character_stamps"]) == 15
    assert len(payload["task_completions"]) == 1
    assert len(payload["stamp_placements"]) == 1


def test_factory_reset_removes_game_data_assets_and_settings(
    container, clock, source_files
):
    _seed(container, clock, source_files)
    container.settings_service.sound_enabled = False
    backup = container.backup_service.create_backup()
    assert any(path.is_file() for path in container.config.assets_dir.rglob("*"))

    container.backup_service.factory_reset()

    assert container.worlds.list() == []
    assert container.tasks.list() == []
    assert container.board_service.load_board(clock.today()) == []
    assert container.settings_service.sound_enabled is True
    assert not any(path.is_file() for path in container.config.assets_dir.rglob("*"))
    assert backup.is_file()
