"""Ordered schema migrations. Each entry is (version, sql_script)."""

from task_stamps.data.migrations.m0001_initial import SQL as M0001
from task_stamps.data.migrations.m0002_rewards import SQL as M0002
from task_stamps.data.migrations.m0003_task_penalties import SQL as M0003
from task_stamps.data.migrations.m0004_worldhub import SQL as M0004

MIGRATIONS: list[tuple[int, str]] = [
    (1, M0001),
    (2, M0002),
    (3, M0003),
    (4, M0004),
]

SCHEMA_VERSION: int = MIGRATIONS[-1][0]
