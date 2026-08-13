from __future__ import annotations

from datetime import date
from pathlib import Path

import pytest

from task_stamps.container import AppContainer, build_container
from task_stamps.utilities.clock import FixedClock
from task_stamps.utilities.rng import SeededRandomProvider

# 2026-01-05 is a Monday.
MONDAY = date(2026, 1, 5)


@pytest.fixture
def clock() -> FixedClock:
    return FixedClock(MONDAY)


@pytest.fixture
def data_dir(tmp_path: Path) -> Path:
    return tmp_path / "app_data"


@pytest.fixture
def container(data_dir: Path, clock: FixedClock):
    instance = build_container(
        data_dir=data_dir, clock=clock, rng=SeededRandomProvider(42)
    )
    yield instance
    instance.close()


@pytest.fixture
def source_files(tmp_path: Path) -> Path:
    directory = tmp_path / "source_files"
    directory.mkdir()
    return directory
