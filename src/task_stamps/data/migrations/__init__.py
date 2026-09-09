"""Ordered schema migrations. Each entry is (version, sql_script)."""

from task_stamps.data.migrations.m0001_initial import SQL as M0001
from task_stamps.data.migrations.m0002_rewards import SQL as M0002
from task_stamps.data.migrations.m0003_task_penalties import SQL as M0003
from task_stamps.data.migrations.m0004_worldhub import SQL as M0004
from task_stamps.data.migrations.m0005_dark_board import SQL as M0005
from task_stamps.data.migrations.m0006_daily_boss import SQL as M0006
from task_stamps.data.migrations.m0007_vice_chests import SQL as M0007

MIGRATIONS: list[tuple[int, str]] = [
    (1, M0001),
    (2, M0002),
    (3, M0003),
    (4, M0004),
    (5, M0005),
    (6, M0006),
    (7, M0007),
]

SCHEMA_VERSION: int = MIGRATIONS[-1][0]
