"""Worlds and characters: CRUD, readiness validation, safe archiving."""

from __future__ import annotations

from pathlib import Path

from task_stamps.data.database import Database
from task_stamps.data.repositories.assignments import AssignmentRepository
from task_stamps.data.repositories.characters import CharacterRepository
from task_stamps.data.repositories.tasks import TaskRepository
from task_stamps.data.repositories.worlds import WorldRepository
from task_stamps.domain.enums import (
    STAMPS_PER_CHARACTER,
    AssetType,
    AssignmentEndReason,
    CharacterStatus,
    TaskStatus,
)
from task_stamps.domain.exceptions import (
    CharacterEditError,
    NoEligibleCharacterError,
    ValidationError,
    WorldArchiveError,
)
from task_stamps.domain.models import Character, World
from task_stamps.services.asset_service import AssetService
from task_stamps.services.assignment_service import AssignmentService
from task_stamps.utilities.clock import Clock
from task_stamps.utilities.logging_setup import get_logger

logger = get_logger("library")


class LibraryService:
    def __init__(
        self,
        db: Database,
        clock: Clock,
        worlds: WorldRepository,
        characters: CharacterRepository,
        tasks: TaskRepository,
        assignments: AssignmentRepository,
        assets: AssetService,
        assignment_service: AssignmentService,
    ) -> None:
        self.db = db
        self.clock = clock
        self.worlds = worlds
        self.characters = characters
        self.tasks = tasks
        self.assignments = assignments
        self.assets = assets
        self.assignment_service = assignment_service

    # -- worlds ------------------------------------------------------------

    def create_world(self, name: str, description: str = "") -> World:
        if not name.strip():
            raise ValidationError("A world needs a name.")
        return self.worlds.create(name.strip(), description.strip())

    def update_world(self, world_id: str, name: str, description: str) -> World:
        if not name.strip():
            raise ValidationError("A world needs a name.")
        return self.worlds.update(
            world_id, name=name.strip(), description=description.strip()
        )

    def import_world_cover(self, world_id: str, source: Path | str) -> World:
        world = self.worlds.get(world_id)
        version = self.assets.replace_version(
            world.cover_asset_version_id, source, AssetType.WORLD_COVER
        )
        return self.worlds.update(world_id, cover_asset_version_id=version.id)

    def world_has_active_assignments(self, world_id: str) -> bool:
        for character in self.characters.list(world_id=world_id, include_archived=True):
            if self.assignments.active_for_character(character.id) is not None:
                return True
        return False

    def archive_world(self, world_id: str, confirmed: bool = False) -> None:
        """Archive a world. When characters are actively assigned this
        requires explicit confirmation; affected tasks get a replacement
        character where possible, otherwise they fall back to draft."""
        with self.db.transaction():
            if self.world_has_active_assignments(world_id):
                if not confirmed:
                    raise WorldArchiveError(
                        "This world has characters assigned to active tasks. "
                        "Confirm to archive it and reassign those tasks."
                    )
            self.worlds.set_archived(world_id, True)
            for character in self.characters.list(world_id=world_id):
                assignment = self.assignments.active_for_character(character.id)
                if assignment is None:
                    continue
                self._end_and_replace(
                    assignment.task_id,
                    assignment.id,
                    assignment.character_id,
                    AssignmentEndReason.CHARACTER_UNAVAILABLE,
                )

    # -- characters ----------------------------------------------------------

    def create_character(
        self, world_id: str, name: str, description: str = ""
    ) -> Character:
        if not name.strip():
            raise ValidationError("A character needs a name.")
        self.worlds.get(world_id)  # must exist
        return self.characters.create(world_id, name.strip(), description.strip())

    def update_character(
        self,
        character_id: str,
        *,
        name: str | None = None,
        description: str | None = None,
        world_id: str | None = None,
    ) -> Character:
        if name is not None and not name.strip():
            raise ValidationError("A character needs a name.")
        with self.db.transaction():
            character = self.characters.update(
                character_id,
                name=name.strip() if name is not None else None,
                description=description,
                world_id=world_id,
            )
            return self.refresh_readiness(character.id)

    def import_portrait(self, character_id: str, source: Path | str) -> Character:
        character = self.characters.get(character_id)
        version = self.assets.replace_version(
            character.portrait_asset_version_id, source, AssetType.PORTRAIT
        )
        return self.characters.update(
            character_id, portrait_asset_version_id=version.id
        )

    def import_default_sound(self, character_id: str, source: Path | str) -> Character:
        character = self.characters.get(character_id)
        version = self.assets.replace_version(
            character.default_sound_asset_version_id, source, AssetType.SOUND
        )
        return self.characters.update(
            character_id, default_sound_asset_version_id=version.id
        )

    def remove_default_sound(self, character_id: str) -> Character:
        return self.characters.update(
            character_id, default_sound_asset_version_id=None
        )

    def import_stamp_image(
        self, character_id: str, sequence: int, source: Path | str
    ) -> None:
        with self.db.transaction():
            stamp = self.characters.stamp_by_sequence(character_id, sequence)
            if stamp is None:
                raise ValidationError(f"Stamp slot {sequence} does not exist.")
            version = self.assets.replace_version(
                stamp.image_asset_version_id, source, AssetType.STAMP_IMAGE
            )
            self.characters.set_stamp_image(character_id, sequence, version.id)
            self.refresh_readiness(character_id)

    def clear_stamp_image(self, character_id: str, sequence: int) -> None:
        """Blocked while the character is actively assigned — removing a
        required stamp image would break the running streak."""
        with self.db.transaction():
            if self.assignments.active_for_character(character_id) is not None:
                raise CharacterEditError(
                    "This character is assigned to an active task. Its stamp "
                    "images cannot be removed (replacing them is allowed)."
                )
            self.characters.set_stamp_image(character_id, sequence, None)
            self.refresh_readiness(character_id)

    def import_stamp_sound(
        self, character_id: str, sequence: int, source: Path | str
    ) -> None:
        stamp = self.characters.stamp_by_sequence(character_id, sequence)
        if stamp is None:
            raise ValidationError(f"Stamp slot {sequence} does not exist.")
        version = self.assets.replace_version(
            stamp.sound_asset_version_id, source, AssetType.SOUND
        )
        self.characters.set_stamp_sound(character_id, sequence, version.id)

    def remove_stamp_sound(self, character_id: str, sequence: int) -> None:
        self.characters.set_stamp_sound(character_id, sequence, None)

    def refresh_readiness(self, character_id: str) -> Character:
        """Ready = named, valid world, all 15 stamp images present."""
        character = self.characters.get(character_id)
        world = self.worlds.find(character.world_id)
        ready = (
            bool(character.name.strip())
            and world is not None
            and not world.is_archived
            and self.characters.stamp_image_count(character_id) == STAMPS_PER_CHARACTER
        )
        status = CharacterStatus.READY if ready else CharacterStatus.DRAFT
        if status != character.status:
            self.characters.set_status(character_id, status)
        return self.characters.get(character_id)

    def archive_character(self, character_id: str, confirmed: bool = False) -> None:
        """Archiving an actively assigned character requires confirmation and
        explicitly ends the assignment, replacing it where possible."""
        with self.db.transaction():
            assignment = self.assignments.active_for_character(character_id)
            if assignment is not None and not confirmed:
                raise CharacterEditError(
                    "This character is assigned to an active task. Confirm to "
                    "archive it and reassign the task."
                )
            self.characters.set_archived(character_id, True)
            if assignment is not None:
                self._end_and_replace(
                    assignment.task_id,
                    assignment.id,
                    character_id,
                    AssignmentEndReason.CHARACTER_UNAVAILABLE,
                )

    def _end_and_replace(
        self,
        task_id: str,
        assignment_id: str,
        previous_character_id: str,
        reason: AssignmentEndReason,
    ) -> None:
        self.assignments.end(assignment_id, reason, ended_on=self.clock.today())
        task = self.tasks.get(task_id)
        if task.status not in (TaskStatus.ACTIVE, TaskStatus.PAUSED):
            return
        try:
            self.assignment_service.assign_character(
                task, exclude_character_id=previous_character_id
            )
        except NoEligibleCharacterError:
            self.tasks.set_status(task_id, TaskStatus.DRAFT)
            logger.warning(
                "Task %s lost its character with no replacement; moved to draft",
                task.name,
            )
