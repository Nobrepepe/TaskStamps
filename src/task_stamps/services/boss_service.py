"""Persistent daily Boss rotation and progress read model."""

from __future__ import annotations

from datetime import date

from task_stamps.data.database import Database
from task_stamps.data.repositories.assets import AssetRepository
from task_stamps.data.repositories.bosses import BossRepository, DailyBossRecord
from task_stamps.data.repositories.characters import CharacterRepository
from task_stamps.data.repositories.completions import CompletionRepository
from task_stamps.data.repositories.tasks import TaskRepository
from task_stamps.data.repositories.worlds import WorldRepository
from task_stamps.domain.enums import TaskStatus
from task_stamps.domain.models import Character, DailyBoss
from task_stamps.services.board_service import BoardService
from task_stamps.services.schedule_service import ScheduleService
from task_stamps.services.settings_service import SettingsService
from task_stamps.utilities.clock import Clock


class BossService:
    def __init__(
        self,
        db: Database,
        clock: Clock,
        bosses: BossRepository,
        characters: CharacterRepository,
        worlds: WorldRepository,
        assets: AssetRepository,
        tasks: TaskRepository,
        completions: CompletionRepository,
        schedule: ScheduleService,
        board: BoardService,
        settings: SettingsService,
    ) -> None:
        self.db = db
        self.clock = clock
        self.bosses = bosses
        self.characters = characters
        self.worlds = worlds
        self.assets = assets
        self.tasks = tasks
        self.completions = completions
        self.schedule = schedule
        self.board = board
        self.settings = settings

    def daily_boss(self, day: date | None = None) -> DailyBoss | None:
        day = day or self.clock.today()
        with self.db.transaction():
            record = self.bosses.find(day)
            if record is None:
                record = self._select_and_store(day)
        return self._read_model(record, day) if record else None

    def _select_and_store(self, day: date) -> DailyBossRecord | None:
        pool = self.characters.boss_pool()
        if not pool:
            return None
        previous = self.bosses.latest_before(day)
        if previous is None:
            selected = pool[0]
        else:
            elapsed = (day - previous.boss_date).days
            selected = self._advance(pool, previous.character_id, elapsed)
        assert selected.boss_image_asset_version_id is not None
        return self.bosses.create(
            day,
            selected.id,
            selected.boss_image_asset_version_id,
            selected.boss_sound_asset_version_id,
        )

    def _advance(
        self, pool: list[Character], previous_character_id: str, elapsed: int
    ) -> Character:
        for index, character in enumerate(pool):
            if character.id == previous_character_id:
                return pool[(index + elapsed) % len(pool)]
        previous = self.characters.get(previous_character_id)
        previous_key = (previous.created_at, previous.id)
        first_after = next(
            (index for index, character in enumerate(pool)
             if (character.created_at, character.id) > previous_key),
            0,
        )
        return pool[(first_after + max(0, elapsed - 1)) % len(pool)]

    def _read_model(self, record: DailyBossRecord, day: date) -> DailyBoss:
        character = self.characters.get(record.character_id)
        world = self.worlds.get(character.world_id)
        image = self.assets.get_version(record.image_asset_version_id)
        # The character's own defeat sound is frozen into the daily record; the
        # global Boss sound is a live setting standing in when it has none.
        sound = self.assets.find_version(record.sound_asset_version_id)
        if sound is None:
            sound = self.assets.find_version(
                self.settings.boss_fallback_sound_version_id
            )
        landed, target = self.progress(day)
        return DailyBoss(
            date=day,
            character_id=character.id,
            name=character.name,
            world_name=world.name,
            day_number=day.timetuple().tm_yday,
            image_relative_path=image.relative_path,
            sound_relative_path=sound.relative_path if sound else None,
            strikes_landed=landed,
            strikes_target=target,
        )

    def progress(self, day: date) -> tuple[int, int]:
        completions = self.completions.list_between(day, day)
        completed_ids = {completion.task_id for completion in completions}
        scheduled_ids = {
            task.id
            for task in self.tasks.list(status=TaskStatus.ACTIVE)
            if self.schedule.is_scheduled_on(task, day)
        }
        return self.board.stamp_count(day), len(completed_ids | scheduled_ids)
