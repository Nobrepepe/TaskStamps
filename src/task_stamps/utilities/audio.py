"""Best-effort local audio playback.

Tries common command-line players so the app stays dependency-free.
Playback failures are logged and never crash the application.
"""

from __future__ import annotations

import shutil
import subprocess
import sys
import threading
from pathlib import Path

from task_stamps.utilities.logging_setup import get_logger

logger = get_logger("audio")


class AudioPlayer:
    def __init__(self) -> None:
        self._player: str | None = None
        for candidate in ("ffplay", "paplay", "pw-play", "mpv", "aplay", "afplay"):
            if shutil.which(candidate):
                self._player = candidate
                break

    @property
    def available(self) -> bool:
        return self._player is not None or sys.platform == "win32"

    def play(self, path: Path, volume: float = 1.0) -> bool:
        """Start playback without blocking. Returns False when unavailable."""
        volume = max(0.0, min(1.0, volume))
        try:
            if sys.platform == "win32" and path.suffix.lower() == ".wav":
                import winsound

                winsound.PlaySound(str(path), winsound.SND_FILENAME | winsound.SND_ASYNC)
                return True
            if self._player is None:
                logger.warning("No audio player found; skipping sound %s", path)
                return False
            command = self._build_command(self._player, path, volume)
            subprocess.Popen(
                command,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                stdin=subprocess.DEVNULL,
            )
            return True
        except Exception:  # noqa: BLE001 - a sound must never crash the app
            logger.exception("Audio playback failed for %s", path)
            return False

    def play_sequence(self, paths: list[Path], volume: float = 1.0) -> bool:
        """Play readable files in order without blocking the UI thread."""
        paths = [path for path in paths if path.is_file()]
        if not paths or not self.available:
            return False
        volume = max(0.0, min(1.0, volume))
        threading.Thread(
            target=self._play_sequence_blocking,
            args=(paths, volume),
            daemon=True,
        ).start()
        return True

    def _play_sequence_blocking(self, paths: list[Path], volume: float) -> None:
        for path in paths:
            try:
                if sys.platform == "win32" and path.suffix.lower() == ".wav":
                    import winsound

                    winsound.PlaySound(str(path), winsound.SND_FILENAME)
                    continue
                if self._player is None:
                    return
                subprocess.run(
                    self._build_command(self._player, path, volume),
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    stdin=subprocess.DEVNULL,
                    check=False,
                )
            except Exception:  # noqa: BLE001 - a sound must never crash the app
                logger.exception("Audio playback failed for %s", path)

    @staticmethod
    def _build_command(player: str, path: Path, volume: float) -> list[str]:
        if player == "ffplay":
            return [
                "ffplay",
                "-nodisp",
                "-autoexit",
                "-loglevel",
                "quiet",
                "-volume",
                str(int(volume * 100)),
                str(path),
            ]
        if player in ("paplay", "pw-play"):
            return [player, f"--volume={int(volume * 65536)}", str(path)]
        if player == "mpv":
            return ["mpv", "--no-video", "--really-quiet", f"--volume={int(volume * 100)}", str(path)]
        if player == "afplay":
            return ["afplay", "-v", f"{volume:.2f}", str(path)]
        return [player, str(path)]  # aplay and fallbacks
