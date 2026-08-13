from __future__ import annotations

import logging
import logging.handlers
from pathlib import Path

LOGGER_NAME = "task_stamps"


def setup_logging(logs_dir: Path) -> logging.Logger:
    logger = logging.getLogger(LOGGER_NAME)
    if logger.handlers:
        return logger
    logger.setLevel(logging.DEBUG)
    logs_dir.mkdir(parents=True, exist_ok=True)
    handler = logging.handlers.RotatingFileHandler(
        logs_dir / "task_stamps.log", maxBytes=1_000_000, backupCount=3, encoding="utf-8"
    )
    handler.setFormatter(
        logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s")
    )
    logger.addHandler(handler)
    return logger


def get_logger(child: str | None = None) -> logging.Logger:
    name = LOGGER_NAME if child is None else f"{LOGGER_NAME}.{child}"
    return logging.getLogger(name)
