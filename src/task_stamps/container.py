"""Application container: single place where everything is wired together."""

from __future__ import annotations

from pathlib import Path

from task_stamps.config import AppConfig, load_config
from task_stamps.data.database import Database
from task_stamps.data.repositories.assets import AssetRepository
from task_stamps.data.repositories.bosses import BossRepository
from task_stamps.data.repositories.assignments import AssignmentRepository
from task_stamps.data.repositories.characters import CharacterRepository
from task_stamps.data.repositories.completions import CompletionRepository
from task_stamps.data.repositories.placements import PlacementRepository
from task_stamps.data.repositories.settings import SettingsRepository
from task_stamps.data.repositories.state import AppStateRepository
from task_stamps.data.repositories.tasks import TaskRepository
from task_stamps.data.repositories.worlds import WorldRepository
from task_stamps.data.repositories.chests import ChestRepository
from task_stamps.data.repositories.misses import MissRepository
from task_stamps.services.asset_service import AssetService
from task_stamps.services.assignment_service import AssignmentService
from task_stamps.services.backup_service import BackupService
from task_stamps.services.board_service import BoardService
from task_stamps.services.boss_service import BossService
from task_stamps.services.chest_service import ChestService
from task_stamps.services.completion_service import CompletionService
from task_stamps.services.library_service import LibraryService
from task_stamps.services.schedule_service import ScheduleService
from task_stamps.services.settings_service import SettingsService
from task_stamps.services.streak_service import StreakService
from task_stamps.services.stats_service import StatsService
from task_stamps.services.task_service import TaskService
from task_stamps.worldhub.consumer_service import WorldHubService
from task_stamps.utilities.audio import AudioPlayer
from task_stamps.utilities.clock import Clock, SystemClock
from task_stamps.utilities.logging_setup import setup_logging
from task_stamps.utilities.rng import RandomProvider, SystemRandomProvider


class AppContainer:
    def __init__(
        self,
        config: AppConfig,
        clock: Clock,
        rng: RandomProvider,
    ) -> None:
        self.config = config
        self.clock = clock
        self.rng = rng
        setup_logging(config.logs_dir)

        self.db = Database(config.database_path)
        self.db.migrate()

        # Repositories
        self.worlds = WorldRepository(self.db, clock)
        self.characters = CharacterRepository(self.db, clock)
        self.tasks = TaskRepository(self.db, clock)
        self.assignments = AssignmentRepository(self.db, clock)
        self.completions = CompletionRepository(self.db, clock)
        self.placements = PlacementRepository(self.db, clock)
        self.assets = AssetRepository(self.db, clock)
        self.bosses = BossRepository(self.db, clock)
        self.settings_repo = SettingsRepository(self.db, clock)
        self.state = AppStateRepository(self.db, clock)
        self.chests = ChestRepository(self.db, clock)
        self.misses = MissRepository(self.db, clock)

        # Services
        self.settings_service = SettingsService(self.settings_repo)
        self.asset_service = AssetService(config, self.assets)
        self.asset_service.ensure_bundled_assets()
        self.board_service = BoardService(self.placements, rng)
        self.assignment_service = AssignmentService(
            self.db, clock, rng, self.characters, self.assignments, self.worlds
        )
        self.schedule_service = ScheduleService(
            self.db, clock, self.tasks, self.assignments, self.completions, self.state,
            self.misses,
        )
        self.schedule_service.assignment_service = self.assignment_service
        self.boss_service = BossService(
            self.db,
            clock,
            self.bosses,
            self.characters,
            self.worlds,
            self.assets,
            self.tasks,
            self.completions,
            self.schedule_service,
            self.board_service,
            self.settings_service,
        )
        self.chest_service = ChestService(self.db, clock, rng, self.chests)
        self.completion_service = CompletionService(
            self.db,
            clock,
            self.tasks,
            self.characters,
            self.worlds,
            self.assignments,
            self.completions,
            self.placements,
            self.schedule_service,
            self.assignment_service,
            self.board_service,
            self.boss_service,
            self.chest_service,
        )
        self.streak_service = StreakService(self.assignments, self.completions)
        self.stats_service = StatsService(
            clock, self.completions, self.tasks, self.chests
        )
        self.library_service = LibraryService(
            self.db,
            clock,
            self.worlds,
            self.characters,
            self.tasks,
            self.assignments,
            self.asset_service,
            self.assignment_service,
        )
        self.task_service = TaskService(
            self.db,
            clock,
            self.tasks,
            self.assignments,
            self.assignment_service,
            self.schedule_service,
        )
        self.backup_service = BackupService(config, self.db, clock)
        self.worldhub = WorldHubService(
            config,
            self.db,
            clock,
            self.worlds,
            self.characters,
            self.assets,
            self.asset_service,
            self.library_service,
            self.assignments,
        )
        self.audio = AudioPlayer()

    def close(self) -> None:
        self.db.close()


def build_container(
    data_dir: Path | None = None,
    clock: Clock | None = None,
    rng: RandomProvider | None = None,
) -> AppContainer:
    config = load_config(data_dir)
    return AppContainer(
        config=config,
        clock=clock or SystemClock(),
        rng=rng or SystemRandomProvider(),
    )
