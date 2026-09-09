from __future__ import annotations

import sqlite3
from types import SimpleNamespace

from task_stamps.data.database import Database
from task_stamps.data.migrations.m0001_initial import SQL as M1
from task_stamps.data.migrations.m0002_rewards import SQL as M2
from task_stamps.data.migrations.m0003_task_penalties import SQL as M3
from task_stamps.data.migrations.m0004_worldhub import SQL as M4
from task_stamps.data.migrations.m0005_dark_board import SQL as M5
from task_stamps.data.migrations.m0006_daily_boss import SQL as M6
from task_stamps.domain.enums import PoolType
from task_stamps.utilities.placeholder_art import render_beep_wav, render_portrait_png
from task_stamps.views.today import TodayView
from tests.helpers import EVERY_DAY, make_character, make_task, make_world


def _boss_media(container, character_id, source_files, *, sound=False):
    image = source_files / f"{character_id}_boss.png"
    render_portrait_png(image, (30, 100, 120), width=160, height=90)
    container.library_service.import_boss_image(character_id, image)
    if sound:
        audio = source_files / f"{character_id}_boss.wav"
        render_beep_wav(audio, duration=0.02)
        container.library_service.import_boss_sound(character_id, audio)


def test_daily_boss_is_stable_and_rotates_by_elapsed_days(container, clock, source_files):
    world = make_world(container)
    characters = [make_character(container, world.id, name, source_files) for name in ("A", "B", "C")]
    for character in characters:
        _boss_media(container, character.id, source_files)
    ordered = container.characters.boss_pool()

    first = container.boss_service.daily_boss()
    assert first.character_id == ordered[0].id
    assert container.boss_service.daily_boss() == first

    clock.advance_days(2)
    third_day = container.boss_service.daily_boss()
    assert third_day.character_id == ordered[2].id
    assert third_day.day_number == clock.today().timetuple().tm_yday


def test_daily_snapshot_keeps_old_art_after_replacement(container, source_files):
    world = make_world(container)
    character = make_character(container, world.id, "Boss", source_files)
    _boss_media(container, character.id, source_files, sound=True)
    first = container.boss_service.daily_boss()

    replacement = source_files / "replacement_boss.png"
    render_portrait_png(replacement, (120, 30, 40), width=320, height=180)
    container.library_service.import_boss_image(character.id, replacement)
    assert container.boss_service.daily_boss().image_relative_path == first.image_relative_path
    assert container.assets.is_version_referenced(
        container.bosses.find(first.date).image_asset_version_id
    )


def test_boss_pool_does_not_change_assignment_eligibility(container, source_files):
    world = make_world(container)
    character = make_character(container, world.id, "Boss", source_files)
    before = container.characters.eligible_character_ids(PoolType.ALL_WORLDS, None)
    _boss_media(container, character.id, source_files)
    container.boss_service.daily_boss()
    after = container.characters.eligible_character_ids(PoolType.ALL_WORLDS, None)
    assert before == after == [character.id]


def test_boss_progress_and_defeat_transition(container, clock, source_files):
    world = make_world(container)
    character = make_character(container, world.id, "Boss", source_files)
    _boss_media(container, character.id, source_files)
    task = make_task(container, weekdays=EVERY_DAY)
    before = container.boss_service.daily_boss()
    assert (before.strikes_landed, before.strikes_target, before.defeated) == (0, 1, False)

    result = container.completion_service.complete_task(task.id)
    after = container.boss_service.daily_boss()
    assert (after.strikes_landed, after.strikes_target, after.defeated) == (1, 1, True)
    # The Boss chest is minted exactly once, so its arrival is the defeat event.
    assert result.boss_chest_granted
    assert container.chests.boss_chest_for(clock.today()) is not None


def test_boss_image_accepts_any_dimensions(container, source_files):
    world = make_world(container)
    character = make_character(container, world.id, "Boss", source_files)
    bad = source_files / "square.png"
    render_portrait_png(bad, (80, 80, 80), width=100, height=100)
    updated = container.library_service.import_boss_image(character.id, bad)
    assert updated.boss_image_asset_version_id is not None


def test_boss_banner_setting_defaults_true_and_persists(container):
    settings = container.settings_service
    assert settings.boss_banner_enabled is True
    settings.boss_banner_enabled = False
    assert settings.boss_banner_enabled is False


def test_today_board_uses_full_content_width_with_side_padding():
    app = SimpleNamespace(page=SimpleNamespace(width=1440), rail_width=178)
    width, height = TodayView(app)._board_area()
    assert width == 1440 - 178 - 112
    assert height == width * 9 / 16


def test_dark_board_and_boss_schema_migrate_from_v4(tmp_path):
    path = tmp_path / "v4.sqlite3"
    connection = sqlite3.connect(path)
    for sql in (M1, M2, M3, M4):
        connection.executescript(sql)
    connection.execute(
        "INSERT INTO app_settings(key, serialized_value, updated_at) "
        "VALUES ('board_background', '\"Paper\"', datetime('now'))"
    )
    connection.execute("PRAGMA user_version = 4")
    connection.commit()
    connection.close()

    database = Database(path)
    database.migrate()
    assert database.query_one(
        "SELECT serialized_value FROM app_settings WHERE key = 'board_background'"
    )["serialized_value"] == '"Recessed"'
    columns = {row["name"] for row in database.query_all("PRAGMA table_info(characters)")}
    assert {"boss_image_asset_version_id", "boss_sound_asset_version_id"} <= columns
    assert database.query_one(
        "SELECT name FROM sqlite_master WHERE type = 'table' AND name = 'daily_bosses'"
    )
    database.close()


def test_vice_chest_schema_migrates_from_v6_and_keeps_miss_history(tmp_path):
    path = tmp_path / "v6.sqlite3"
    connection = sqlite3.connect(path)
    for sql in (M1, M2, M3, M4, M5, M6):
        connection.executescript(sql)
    connection.execute(
        "INSERT INTO habit_tasks(id, name, description, weekday_mask, pool_type, "
        "world_id, status, weight, created_at, updated_at) "
        "VALUES ('t1', 'Old', '', 127, 'all', NULL, 'active', 'medium', "
        "datetime('now'), datetime('now'))"
    )
    connection.execute(
        "INSERT INTO task_penalties(id, task_id, penalty_date, reason, "
        "points_assessed, points_deducted, created_at) "
        "VALUES ('p1', 't1', '2026-01-06', 'missed', 3, 3, datetime('now'))"
    )
    connection.execute(
        "INSERT INTO task_penalties(id, task_id, penalty_date, reason, "
        "points_assessed, points_deducted, created_at) "
        "VALUES ('p2', 't1', '2026-01-06', 'scheduled_pause', 1, 1, datetime('now'))"
    )
    connection.execute(
        "INSERT INTO vice_offerings(id, name, description, price, quantity, "
        "created_at, updated_at) "
        "VALUES ('v1', 'Coffee', '', 5, 1, datetime('now'), datetime('now'))"
    )
    connection.execute("PRAGMA user_version = 6")
    connection.commit()
    connection.close()

    database = Database(path)
    database.migrate()

    tables = {
        row["name"]
        for row in database.query_all("SELECT name FROM sqlite_master WHERE type = 'table'")
    }
    assert {"vice_rewards", "vice_chests", "task_misses"} <= tables
    assert not tables & {"vice_offerings", "vice_claims", "task_penalties"}
    columns = {
        row["name"] for row in database.query_all("PRAGMA table_info(task_completions)")
    }
    assert "reward_points" not in columns
    # The auto-pause counter survives the upgrade, and the points-only
    # scheduled_pause record is dropped with the rest of the economy.
    carried = database.query_all("SELECT * FROM task_misses")
    assert [(row["task_id"], row["miss_date"]) for row in carried] == [
        ("t1", "2026-01-06")
    ]
    database.close()
