"""World Hub consumer acceptance tests, driven by the shared fixtures."""

from __future__ import annotations

import json
from datetime import timedelta
from pathlib import Path

import pytest

from task_stamps.domain.enums import CharacterStatus, TaskStatus
from task_stamps.worldhub.package_reader import PackageError

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures" / "worldhub"
EXPECTED = json.loads((FIXTURES / "expected.json").read_text())


def install(container, name: str):
    staged = container.worldhub.stage_zip(FIXTURES / name)
    return container.worldhub.activate(staged)


def snapshot_user_state(container) -> dict:
    rows = lambda sql: [dict(r) for r in container.db.query_all(sql)]
    return {
        "tasks": rows("SELECT id, name, status FROM habit_tasks ORDER BY id"),
        "completions": rows("SELECT id, task_id FROM task_completions ORDER BY id"),
        "placements": rows(
            "SELECT id, completion_id, image_asset_version_id FROM stamp_placements ORDER BY id"
        ),
    }


class TestInstall:
    def test_valid_package_creates_ready_characters_with_15_stamps(self, container):
        status = install(container, "valid-v1.zip")
        assert status["hub_mode"] is True
        assert status["publication_id"] == EXPECTED["publicationV1"]

        characters = container.characters.list()
        assert len(characters) == len(EXPECTED["characterIds"])
        for character in characters:
            assert character.status == CharacterStatus.READY
            stamps = container.characters.stamps_for(character.id)
            assert len(stamps) == 15
            assert all(stamp.image_asset_version_id for stamp in stamps)
            assert character.portrait_asset_version_id

        receipt = status["receipt"]
        assert receipt["applicationType"] == "task-stamps.stamp-set"
        assert receipt["productionId"] == EXPECTED["productionId"]
        assert receipt["sourceLibraryId"] == EXPECTED["libraryId"]

    def test_reinstalling_same_package_is_idempotent(self, container):
        install(container, "valid-v1.zip")
        first = {c.id for c in container.characters.list()}
        install(container, "valid-v1.zip")
        assert {c.id for c in container.characters.list()} == first
        # unchanged bytes must not create new asset versions
        versions = container.db.query_one("SELECT COUNT(*) AS n FROM asset_versions")
        install(container, "valid-v1.zip")
        assert container.db.query_one("SELECT COUNT(*) AS n FROM asset_versions")["n"] == versions["n"]


class TestUpdate:
    def test_update_preserves_history_and_retires_characters(self, container, clock):
        install(container, "valid-v1.zip")

        # Build real user state: a task assigned to the character that v2 retires.
        retired_hub_id = EXPECTED["retiredCharacterIds"][0]
        retired = container.db.query_one(
            "SELECT id FROM characters WHERE hub_id = ?", (retired_hub_id,)
        )["id"]
        kept = container.db.query_one(
            "SELECT id FROM characters WHERE hub_id = ?", (EXPECTED["characterIds"][0],)
        )["id"]

        from task_stamps.domain.enums import PoolType
        task = container.task_service.create_draft("Water the plants", "", 127, PoolType.ALL_WORLDS, None)
        container.task_service.activate(task.id)
        # Force the assignment onto the character that will be retired.
        assignment = container.assignments.active_for_task(task.id)
        container.db.execute(
            "UPDATE character_assignments SET character_id = ? WHERE id = ?",
            (retired, assignment.id),
        )
        container.completion_service.complete_task(task.id)
        placements_before = [
            dict(r) for r in container.db.query_all(
                "SELECT image_asset_version_id FROM stamp_placements"
            )
        ]
        assert placements_before, "completion placed a stamp"
        before = snapshot_user_state(container)

        install(container, "valid-v2.zip")

        # Retired character is archived, its assignment safely ended/replaced.
        row = container.db.query_one("SELECT is_archived FROM characters WHERE id = ?", (retired,))
        assert row["is_archived"] == 1
        active = container.assignments.active_for_character(retired)
        assert active is None
        replacement = container.assignments.active_for_task(task.id)
        assert replacement is not None and replacement.character_id != retired

        # The renamed character keeps its identity and shows the new name.
        renamed = container.db.query_one(
            "SELECT id, name FROM characters WHERE hub_id = ?", (EXPECTED["renamedCharacterId"],)
        )
        assert renamed["id"] == kept
        assert "Rekindled" in renamed["name"]

        # Historical placements resolve the exact old bytes: version rows intact.
        for placement in placements_before:
            version = container.assets.find_version(placement["image_asset_version_id"])
            assert version is not None
            assert container.asset_service.absolute_path(version).exists()

        # Tasks, completions, and placements are untouched.
        after = snapshot_user_state(container)
        assert after == before

    def test_updated_art_creates_new_version_and_keeps_old(self, container):
        install(container, "valid-v1.zip")
        versions_before = container.db.query_one("SELECT COUNT(*) AS n FROM asset_versions")["n"]
        install(container, "valid-v2.zip")
        versions_after = container.db.query_one("SELECT COUNT(*) AS n FROM asset_versions")["n"]
        assert versions_after > versions_before, "changed art creates a new immutable version"
        # No version rows were deleted.
        assert container.db.query_one(
            "SELECT COUNT(*) AS n FROM asset_versions"
        )["n"] >= versions_before


class TestRollback:
    def test_rollback_restores_previous_publication(self, container):
        install(container, "valid-v1.zip")
        install(container, "valid-v2.zip")
        status = container.worldhub.rollback()
        assert status["publication_id"] == EXPECTED["publicationV1"]
        # The v1 selection is live again: both original characters active.
        active = [c for c in container.characters.list() if not c.is_archived]
        assert len(active) == len(EXPECTED["characterIds"])


class TestRejection:
    @pytest.mark.parametrize("fixture,fragment", [
        ("corrupt-checksum.zip", "checksum"),
        ("unlisted-file.zip", "unlisted"),
        ("missing-asset.zip", "missing"),
        ("wrong-apptype.zip", "not for this app"),
        ("unsupported-protocol.zip", "newer World Hub protocol"),
        ("traversal.zip", "unsafe|not a World Hub package|missing"),
    ])
    def test_bad_packages_change_nothing(self, container, fixture, fragment):
        install(container, "valid-v1.zip")
        world_count = len(container.worlds.list())
        version_count = container.db.query_one("SELECT COUNT(*) AS n FROM asset_versions")["n"]

        import re
        with pytest.raises(PackageError) as excinfo:
            install(container, fixture)
        assert re.search(fragment, str(excinfo.value), re.IGNORECASE)

        assert container.worldhub.active_publication_id() == EXPECTED["publicationV1"]
        assert len(container.worlds.list()) == world_count
        assert container.db.query_one("SELECT COUNT(*) AS n FROM asset_versions")["n"] == version_count


class TestLinkedFolder:
    def test_link_and_check_for_update(self, container, tmp_path):
        # Simulate a linked World Hub production folder holding v2.
        import zipfile
        production_dir = tmp_path / "production"
        pub_dir = production_dir / "publications"
        with zipfile.ZipFile(FIXTURES / "valid-v2.zip") as archive:
            archive.extractall(pub_dir / EXPECTED["publicationV2"])
        (production_dir / "current.json").write_text(json.dumps({
            "publicationId": EXPECTED["publicationV2"],
            "manifestPath": f"publications/{EXPECTED['publicationV2']}/manifest.json",
        }))

        install(container, "valid-v1.zip")
        container.worldhub.link_folder(production_dir)
        preview = container.worldhub.check_for_update()
        assert preview.publication_id == EXPECTED["publicationV2"]
        assert preview.already_active is False
        assert preview.retired_characters, "the preview names characters that would retire"

        staged = container.worldhub.stage_linked_folder()
        status = container.worldhub.activate(staged)
        assert status["publication_id"] == EXPECTED["publicationV2"]

        # The app keeps working when the linked folder disappears.
        import shutil
        shutil.rmtree(production_dir)
        assert container.worldhub.status()["hub_mode"] is True
        assert (container.worldhub.publications_dir / EXPECTED["publicationV2"]).is_dir()
