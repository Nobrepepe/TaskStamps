"""Asset versioning: history keeps old versions; imports are validated."""

from __future__ import annotations

import pytest

from task_stamps.domain.enums import AssetType
from task_stamps.domain.exceptions import AssetImportError
from task_stamps.utilities.placeholder_art import render_stamp_png
from tests.helpers import EVERY_DAY, make_character, make_task, make_world


def test_history_keeps_old_asset_version_after_replacement(
    container, clock, source_files
):
    world = make_world(container)
    character = make_character(container, world.id, "Alpha", source_files)
    task = make_task(container, weekdays=EVERY_DAY)
    result = container.completion_service.complete_task(task.id)
    old_version_id = result.placement.image_asset_version_id
    old_file = container.config.data_dir / container.assets.get_version(
        old_version_id
    ).relative_path
    assert old_file.is_file()

    # Replace stamp #1's artwork.
    replacement = source_files / "replacement.png"
    render_stamp_png(replacement, 1, (90, 90, 200), width=32, height=24)
    container.library_service.import_stamp_image(character.id, 1, replacement)

    new_stamp = container.characters.stamp_by_sequence(character.id, 1)
    assert new_stamp.image_asset_version_id != old_version_id
    # The historical placement still points at the untouched old version.
    placement = container.placements.get_for_completion(result.completion.id)
    assert placement.image_asset_version_id == old_version_id
    assert old_file.is_file()
    # Board rendering resolves the old bytes, not the new ones.
    board = container.board_service.load_board(clock.today())
    assert board[0].image_relative_path == container.assets.get_version(
        old_version_id
    ).relative_path


def test_import_rejects_unsupported_and_invalid_files(container, source_files):
    text_file = source_files / "notes.txt"
    text_file.write_text("not an image")
    with pytest.raises(AssetImportError):
        container.asset_service.import_file(text_file, AssetType.STAMP_IMAGE)

    fake_png = source_files / "fake.png"
    fake_png.write_bytes(b"this is not a png at all")
    with pytest.raises(AssetImportError):
        container.asset_service.import_file(fake_png, AssetType.STAMP_IMAGE)

    missing = source_files / "missing.png"
    with pytest.raises(AssetImportError):
        container.asset_service.import_file(missing, AssetType.STAMP_IMAGE)


def test_import_copies_into_managed_storage(container, source_files):
    source = source_files / "art.png"
    render_stamp_png(source, 7, (50, 120, 90), width=32, height=24)
    version = container.asset_service.import_file(source, AssetType.STAMP_IMAGE)
    stored = container.config.data_dir / version.relative_path
    assert stored.is_file()
    assert stored.read_bytes() == source.read_bytes()
    # Managed copy is independent of the source path.
    source.unlink()
    assert stored.is_file()


def test_cleanup_only_removes_unreferenced_versions(container, clock, source_files):
    world = make_world(container)
    character = make_character(container, world.id, "Alpha", source_files)
    task = make_task(container, weekdays=EVERY_DAY)
    result = container.completion_service.complete_task(task.id)
    referenced_version = result.placement.image_asset_version_id

    # Replace stamp 1 twice: the middle version is referenced by nothing.
    for index in range(2):
        art = source_files / f"art{index}.png"
        render_stamp_png(art, 1, (60 + index, 60, 60), width=32, height=24)
        container.library_service.import_stamp_image(character.id, 1, art)

    removed = container.asset_service.cleanup_unreferenced_versions()
    assert removed == 1
    # The historical version and its file both survive.
    assert container.assets.get_version(referenced_version) is not None
    path = container.config.data_dir / container.assets.get_version(
        referenced_version
    ).relative_path
    assert path.is_file()
