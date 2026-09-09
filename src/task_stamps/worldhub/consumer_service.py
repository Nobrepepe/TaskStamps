"""World Hub consumer for Task Stamps.

Installs immutable World Hub publications into the app's own data
directory, imports their content through the existing immutable
AssetVersion system, and keeps every piece of user state app-owned.
Failure at any stage leaves the previous active publication and all
user state untouched.
"""

from __future__ import annotations

import json
import os
import shutil
import tempfile
from dataclasses import dataclass, field as dataclass_field
from datetime import datetime, timezone
from pathlib import Path

from task_stamps.domain.enums import AssetType, CharacterStatus
from task_stamps.utilities.logging_setup import get_logger
from worldhub_kit import (
    PackageError,
    PackageInfo,
    extract_zip_safely,
    load_package,
    read_current_pointer,
)

logger = get_logger("worldhub")

APP_TYPE = "task-stamps.stamp-set"
STATE_ACTIVE_PUBLICATION = "worldhub_active_publication"
STATE_LINKED_FOLDER = "worldhub_linked_folder"


@dataclass
class UpdatePreview:
    publication_id: str
    production_name: str
    production_revision: int
    published_at: str
    added_worlds: list[str] = dataclass_field(default_factory=list)
    updated_worlds: list[str] = dataclass_field(default_factory=list)
    added_characters: list[str] = dataclass_field(default_factory=list)
    updated_characters: list[str] = dataclass_field(default_factory=list)
    retired_characters: list[str] = dataclass_field(default_factory=list)
    changed_assets: int = 0
    affected_assignments: list[str] = dataclass_field(default_factory=list)
    already_active: bool = False


@dataclass
class StagedPackage:
    package: PackageInfo
    staging_dir: Path
    source_type: str  # "zip" | "folder"
    source_path: str

    def cleanup(self) -> None:
        shutil.rmtree(self.staging_dir, ignore_errors=True)


class WorldHubService:
    def __init__(self, config, db, clock, worlds, characters, assets_repo,
                 asset_service, library_service, assignments) -> None:
        self.config = config
        self.db = db
        self.clock = clock
        self.worlds = worlds
        self.characters = characters
        self.assets_repo = assets_repo
        self.asset_service = asset_service
        self.library = library_service
        self.assignments = assignments

    # -- layout ------------------------------------------------------------

    @property
    def content_dir(self) -> Path:
        return self.config.data_dir / "worldhub-content"

    @property
    def publications_dir(self) -> Path:
        return self.content_dir / "publications"

    @property
    def receipts_dir(self) -> Path:
        return self.content_dir / "receipts"

    @property
    def pointer_path(self) -> Path:
        return self.content_dir / "current.json"

    # -- status ------------------------------------------------------------

    def _state_get(self, key: str) -> str | None:
        row = self.db.query_one("SELECT value FROM app_state WHERE key = ?", (key,))
        return row["value"] if row else None

    def _state_set(self, key: str, value: str | None) -> None:
        if value is None:
            self.db.execute("DELETE FROM app_state WHERE key = ?", (key,))
        else:
            self.db.execute(
                "INSERT INTO app_state(key, value, updated_at) VALUES(?, ?, ?) "
                "ON CONFLICT(key) DO UPDATE SET value = excluded.value, updated_at = excluded.updated_at",
                (key, value, self.clock.now().isoformat()),
            )

    def active_publication_id(self) -> str | None:
        return self._state_get(STATE_ACTIVE_PUBLICATION)

    def hub_mode(self) -> bool:
        return self.active_publication_id() is not None

    def linked_folder(self) -> Path | None:
        raw = self._state_get(STATE_LINKED_FOLDER)
        return Path(raw) if raw else None

    def receipt(self, publication_id: str) -> dict | None:
        path = self.receipts_dir / f"{publication_id}.json"
        try:
            return json.loads(path.read_text("utf-8"))
        except (OSError, json.JSONDecodeError):
            return None

    def status(self) -> dict:
        active = self.active_publication_id()
        receipt = self.receipt(active) if active else None
        previous = None
        pointer = read_current_pointer(self.content_dir) if self.pointer_path.exists() else None
        if pointer:
            previous = pointer.get("previousPublicationId")
        return {
            "hub_mode": active is not None,
            "publication_id": active,
            "receipt": receipt,
            "previous_publication_id": previous,
            "linked_folder": str(self.linked_folder() or ""),
        }

    # -- staging -----------------------------------------------------------

    def stage_zip(self, zip_path: Path | str) -> StagedPackage:
        zip_path = Path(zip_path)
        staging = Path(tempfile.mkdtemp(prefix="worldhub-stage-", dir=str(self._tmp_root())))
        try:
            extract_zip_safely(zip_path, staging)
            package = load_package(staging, APP_TYPE)
            self._semantic_validation(package)
            return StagedPackage(package, staging, "zip", str(zip_path))
        except Exception:
            shutil.rmtree(staging, ignore_errors=True)
            raise

    def stage_linked_folder(self, production_dir: Path | str | None = None) -> StagedPackage:
        production_dir = Path(production_dir) if production_dir else self.linked_folder()
        if production_dir is None:
            raise PackageError("No World Hub production folder is linked.")
        pointer = read_current_pointer(production_dir)
        if pointer is None:
            raise PackageError("The linked folder has no readable current.json pointer.")
        source = production_dir / "publications" / pointer["publicationId"]
        if not source.is_dir():
            raise PackageError("The linked folder's active publication is missing.")
        staging = Path(tempfile.mkdtemp(prefix="worldhub-stage-", dir=str(self._tmp_root())))
        try:
            shutil.copytree(source, staging, dirs_exist_ok=True)
            package = load_package(staging, APP_TYPE)
            self._semantic_validation(package)
            return StagedPackage(package, staging, "folder", str(production_dir))
        except Exception:
            shutil.rmtree(staging, ignore_errors=True)
            raise

    def link_folder(self, production_dir: Path | str) -> None:
        production_dir = Path(production_dir)
        if read_current_pointer(production_dir) is None:
            raise PackageError("That folder is not a World Hub production folder (no current.json).")
        with self.db.transaction():
            self._state_set(STATE_LINKED_FOLDER, str(production_dir))

    def _tmp_root(self) -> Path:
        tmp = self.content_dir / "tmp"
        tmp.mkdir(parents=True, exist_ok=True)
        return tmp

    # -- app-specific semantic validation ----------------------------------

    def _semantic_validation(self, package: PackageInfo) -> None:
        content = package.content
        selections = content.get("selections") or {}
        asset_sets = content.get("assetSets") or {}
        characters = selections.get("stamp_characters") or []
        if not characters:
            raise PackageError("The package selects no stamp characters.")
        if not selections.get("stamp_worlds"):
            raise PackageError("The package selects no worlds.")
        for character_id in characters:
            stamps = asset_sets.get(f"stamps:{character_id}") or []
            if len(stamps) != 15:
                raise PackageError(
                    "A character does not have exactly fifteen stamps; the package was refused."
                )
            if not asset_sets.get(f"portrait:{character_id}"):
                raise PackageError("A character is missing its portrait.")
            if len(asset_sets.get(f"boss_image:{character_id}") or []) > 1:
                raise PackageError("A character has more than one Boss image.")
            if len(asset_sets.get(f"boss_sound:{character_id}") or []) > 1:
                raise PackageError("A character has more than one Boss defeat sound.")
            for sound in asset_sets.get(f"stamp_sounds:{character_id}") or []:
                number = (sound.get("values") or {}).get("stamp_number")
                if not isinstance(number, int) or not 1 <= number <= 15:
                    raise PackageError("A stamp sound has an invalid stamp number.")

    # -- preview -----------------------------------------------------------

    def preview(self, staged: StagedPackage) -> UpdatePreview:
        package = staged.package
        entities = package.entities_by_id()
        preview = UpdatePreview(
            publication_id=package.publication_id,
            production_name=package.manifest["production"]["name"],
            production_revision=package.manifest["production"]["revision"],
            published_at=package.manifest["publishedAt"],
            already_active=package.publication_id == self.active_publication_id(),
        )
        selections = package.content.get("selections") or {}
        selected_world_ids = set(selections.get("stamp_worlds") or [])
        selected_character_ids = set(selections.get("stamp_characters") or [])

        for world_id in selected_world_ids:
            row = self.db.query_one("SELECT id, name FROM worlds WHERE hub_id = ?", (world_id,))
            name = entities.get(world_id, {}).get("name", world_id)
            (preview.updated_worlds if row else preview.added_worlds).append(name)
        for character_id in selected_character_ids:
            row = self.db.query_one("SELECT id FROM characters WHERE hub_id = ?", (character_id,))
            name = entities.get(character_id, {}).get("name", character_id)
            (preview.updated_characters if row else preview.added_characters).append(name)

        for row in self.db.query_all(
            "SELECT id, hub_id, name FROM characters WHERE hub_id IS NOT NULL AND is_archived = 0"
        ):
            if row["hub_id"] not in selected_character_ids:
                preview.retired_characters.append(row["name"])
                assignment = self.assignments.active_for_character(row["id"])
                if assignment is not None:
                    preview.affected_assignments.append(row["name"])

        checksums = package.checksums
        for entry in package.asset_index:
            local = self.db.query_one(
                "SELECT a.current_version_id, v.checksum FROM assets a "
                "LEFT JOIN asset_versions v ON v.id = a.current_version_id WHERE a.hub_id = ?",
                (entry["assetId"],),
            )
            if local and local["checksum"] != checksums.get(entry["path"]):
                preview.changed_assets += 1
        return preview

    # -- activation --------------------------------------------------------

    def activate(self, staged: StagedPackage) -> dict:
        """Import the staged package and make it the active publication."""
        package = staged.package
        publication_id = package.publication_id
        destination = self.publications_dir / publication_id
        previous_active = self.active_publication_id()

        try:
            with self.db.transaction():
                self._import_content(package)
                self._state_set(STATE_ACTIVE_PUBLICATION, publication_id)
                if staged.source_type == "folder":
                    self._state_set(STATE_LINKED_FOLDER, staged.source_path)
            # Database import committed; now persist the immutable copy.
            self.publications_dir.mkdir(parents=True, exist_ok=True)
            if not destination.exists():
                shutil.move(str(staged.staging_dir), str(destination))
            else:
                staged.cleanup()
            self._write_receipt(package, staged)
            self._write_pointer(publication_id, previous_active)
        except Exception:
            staged.cleanup()
            raise
        logger.info("Activated World Hub publication %s", publication_id)
        return self.status()

    def rollback(self) -> dict:
        """Reactivate the previous publication from its immutable copy."""
        pointer = read_current_pointer(self.content_dir)
        previous = pointer.get("previousPublicationId") if pointer else None
        if not previous:
            raise PackageError("There is no previous publication to roll back to.")
        source = self.publications_dir / previous
        if not source.is_dir():
            raise PackageError("The previous publication's files are no longer available.")
        staging = Path(tempfile.mkdtemp(prefix="worldhub-stage-", dir=str(self._tmp_root())))
        try:
            shutil.copytree(source, staging, dirs_exist_ok=True)
            package = load_package(staging, APP_TYPE)
            self._semantic_validation(package)
            staged = StagedPackage(package, staging, "rollback", str(source))
            return self.activate(staged)
        except Exception:
            shutil.rmtree(staging, ignore_errors=True)
            raise

    def check_for_update(self) -> UpdatePreview | None:
        """Compare the linked folder's active publication with ours."""
        staged = self.stage_linked_folder()
        try:
            return self.preview(staged)
        finally:
            staged.cleanup()

    # -- import ------------------------------------------------------------

    def _import_content(self, package: PackageInfo) -> None:
        entities = package.entities_by_id()
        content = package.content
        selections = content.get("selections") or {}
        asset_sets = content.get("assetSets") or {}
        selected_worlds = selections.get("stamp_worlds") or []
        selected_characters = selections.get("stamp_characters") or []

        for hub_world_id in selected_worlds:
            entity = entities[hub_world_id]
            local_id = self._upsert_world(hub_world_id, entity)
            cover_items = asset_sets.get(f"world_cover:{hub_world_id}") or []
            if cover_items:
                version = self._import_hub_asset(
                    package, cover_items[0]["assetId"], AssetType.WORLD_COVER,
                    package.recipes_for("world_cover"),
                )
                self.worlds.update(local_id, cover_asset_version_id=version.id)

        imported_character_hub_ids = set()
        for hub_character_id in selected_characters:
            entity = entities[hub_character_id]
            local_world_row = self.db.query_one(
                "SELECT id FROM worlds WHERE hub_id = ?", (entity.get("worldId"),)
            )
            if local_world_row is None:
                raise PackageError("A character's world is not part of the package.")
            local_id = self._upsert_character(hub_character_id, entity, local_world_row["id"])
            imported_character_hub_ids.add(hub_character_id)

            portrait_items = asset_sets.get(f"portrait:{hub_character_id}") or []
            if portrait_items:
                version = self._import_hub_asset(
                    package, portrait_items[0]["assetId"], AssetType.PORTRAIT,
                    package.recipes_for("portrait"),
                )
                self.characters.update(local_id, portrait_asset_version_id=version.id)

            boss_items = asset_sets.get(f"boss_image:{hub_character_id}") or []
            if boss_items:
                version = self._import_hub_asset(
                    package,
                    boss_items[0]["assetId"],
                    AssetType.BOSS_IMAGE,
                    package.recipes_for("boss_image"),
                )
                self.characters.update(local_id, boss_image_asset_version_id=version.id)

            boss_sound_items = asset_sets.get(f"boss_sound:{hub_character_id}") or []
            if boss_sound_items:
                version = self._import_hub_asset(
                    package, boss_sound_items[0]["assetId"], AssetType.SOUND, ["original"]
                )
                self.characters.update(local_id, boss_sound_asset_version_id=version.id)

            sound_items = asset_sets.get(f"default_sound:{hub_character_id}") or []
            if sound_items:
                version = self._import_hub_asset(
                    package, sound_items[0]["assetId"], AssetType.SOUND, ["original"],
                )
                self.characters.update(local_id, default_sound_asset_version_id=version.id)

            stamps = asset_sets.get(f"stamps:{hub_character_id}") or []
            for index, item in enumerate(stamps, start=1):
                version = self._import_hub_asset(
                    package,
                    item["assetId"],
                    AssetType.STAMP_IMAGE,
                    package.recipes_for("stamps"),
                )
                self.characters.set_stamp_image(local_id, index, version.id)

            for item in asset_sets.get(f"stamp_sounds:{hub_character_id}") or []:
                number = (item.get("values") or {}).get("stamp_number")
                version = self._import_hub_asset(
                    package, item["assetId"], AssetType.SOUND, ["original"],
                )
                self.characters.set_stamp_sound(local_id, number, version.id)

            self.characters.set_status(local_id, CharacterStatus.READY)
            if self._character_is_archived(local_id):
                self.characters.set_archived(local_id, False)

        # Retire hub characters that left the publication; existing safe
        # reassignment behavior handles their active assignments.
        for row in self.db.query_all(
            "SELECT id, hub_id FROM characters WHERE hub_id IS NOT NULL AND is_archived = 0"
        ):
            if row["hub_id"] not in imported_character_hub_ids:
                self.library.archive_character(row["id"], confirmed=True)
        selected_world_set = set(selected_worlds)
        for row in self.db.query_all(
            "SELECT id, hub_id FROM worlds WHERE hub_id IS NOT NULL AND is_archived = 0"
        ):
            if row["hub_id"] not in selected_world_set:
                self.library.archive_world(row["id"], confirmed=True)

    def _character_is_archived(self, character_id: str) -> bool:
        row = self.db.query_one("SELECT is_archived FROM characters WHERE id = ?", (character_id,))
        return bool(row and row["is_archived"])

    def _upsert_world(self, hub_id: str, entity: dict) -> str:
        row = self.db.query_one("SELECT id FROM worlds WHERE hub_id = ?", (hub_id,))
        if row:
            self.worlds.update(row["id"], name=entity["name"], description=entity.get("summary", ""))
            self.db.execute(
                "UPDATE worlds SET is_archived = 0 WHERE id = ?", (row["id"],)
            )
            return row["id"]
        world = self.worlds.create(entity["name"], entity.get("summary", ""))
        self.db.execute("UPDATE worlds SET hub_id = ? WHERE id = ?", (hub_id, world.id))
        return world.id

    def _upsert_character(self, hub_id: str, entity: dict, local_world_id: str) -> str:
        row = self.db.query_one("SELECT id FROM characters WHERE hub_id = ?", (hub_id,))
        if row:
            self.characters.update(
                row["id"], name=entity["name"], description=entity.get("summary", "")
            )
            self.db.execute(
                "UPDATE characters SET world_id = ? WHERE id = ?", (local_world_id, row["id"]),
            )
            return row["id"]
        character = self.characters.create(local_world_id, entity["name"], entity.get("summary", ""))
        self.db.execute("UPDATE characters SET hub_id = ? WHERE id = ?", (hub_id, character.id))
        return character.id

    def _import_hub_asset(self, package: PackageInfo, hub_asset_id: str,
                          asset_type: AssetType, preferred_recipes: list[str]):
        """Import a package file through the immutable AssetVersion system.

        Unchanged bytes reuse the current version; changed bytes create a
        new version so historical placements keep resolving exact bytes.
        """
        entry = package.asset_file(hub_asset_id, preferred_recipes)
        if entry is None:
            raise PackageError("A referenced asset has no packaged file.")
        source = package.absolute(entry["path"])
        file_checksum = package.checksums.get(entry["path"])

        local = self.db.query_one(
            "SELECT a.id AS asset_id, a.current_version_id, v.checksum "
            "FROM assets a LEFT JOIN asset_versions v ON v.id = a.current_version_id "
            "WHERE a.hub_id = ?",
            (hub_asset_id,),
        )
        if local is None:
            version = self.asset_service.import_file(source, asset_type)
            self.db.execute(
                "UPDATE assets SET hub_id = ? WHERE id = ?", (hub_asset_id, version.asset_id),
            )
            return version
        if local["checksum"] == file_checksum and local["current_version_id"]:
            return self.assets_repo.find_version(local["current_version_id"])
        return self.asset_service.import_file(
            source, asset_type, existing_asset_id=local["asset_id"]
        )

    # -- receipts and pointer ----------------------------------------------

    def _write_receipt(self, package: PackageInfo, staged: StagedPackage) -> None:
        self.receipts_dir.mkdir(parents=True, exist_ok=True)
        manifest = package.manifest
        receipt = {
            "sourceLibraryId": manifest["sourceLibraryId"],
            "productionId": manifest["production"]["id"],
            "productionName": manifest["production"]["name"],
            "productionRevision": manifest["production"]["revision"],
            "publicationId": manifest["publicationId"],
            "applicationType": manifest["applicationType"],
            "contractId": manifest["contract"]["id"],
            # A receipt only. Compatibility is decided by the embedded
            # contract's contractFormatVersion, which the kit reader checks.
            "contractRevision": manifest["contract"]["revision"],
            "publishedAt": manifest["publishedAt"],
            "importedAt": datetime.now(timezone.utc).isoformat(),
            "sourceType": staged.source_type,
            "sourcePath": staged.source_path,
            "packageFingerprint": package.checksums.get("manifest.json", ""),
        }
        path = self.receipts_dir / f"{package.publication_id}.json"
        self._atomic_write(path, json.dumps(receipt, indent=2))

    def _write_pointer(self, publication_id: str, previous: str | None) -> None:
        pointer = {
            "publicationId": publication_id,
            "previousPublicationId": previous if previous != publication_id else None,
            "activatedAt": datetime.now(timezone.utc).isoformat(),
        }
        self._atomic_write(self.pointer_path, json.dumps(pointer, indent=2))

    @staticmethod
    def _atomic_write(path: Path, text: str) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        handle = tempfile.NamedTemporaryFile(
            "w", dir=str(path.parent), prefix=".worldhub-tmp-", delete=False, encoding="utf-8"
        )
        try:
            handle.write(text)
            handle.flush()
            os.fsync(handle.fileno())
        finally:
            handle.close()
        os.replace(handle.name, path)
