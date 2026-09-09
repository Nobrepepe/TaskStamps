"""Typed access to persisted application settings."""

from __future__ import annotations

from task_stamps.data.repositories.settings import SettingsRepository

KEY_SOUND_ENABLED = "sound_enabled"
KEY_MASTER_VOLUME = "master_volume"
KEY_FALLBACK_SOUND = "fallback_sound_version_id"
KEY_BOSS_FALLBACK_SOUND = "boss_fallback_sound_version_id"
KEY_REDUCED_ANIMATION = "reduced_animation"
KEY_WEEK_START = "week_start"  # "monday" | "sunday"
KEY_BOARD_BACKGROUND = "board_background"
KEY_BOSS_BANNER = "boss_banner_enabled"

BOARD_BACKGROUNDS: dict[str, str] = {
    "Recessed": "#171310",
    "Level": "#12100f",
    "Warmer": "#1d1714",
    "Ink": "#0d0c0b",
}


class SettingsService:
    def __init__(self, repo: SettingsRepository) -> None:
        self.repo = repo

    # -- sound -------------------------------------------------------
    @property
    def sound_enabled(self) -> bool:
        return bool(self.repo.get(KEY_SOUND_ENABLED, True))

    @sound_enabled.setter
    def sound_enabled(self, value: bool) -> None:
        self.repo.set(KEY_SOUND_ENABLED, bool(value))

    @property
    def master_volume(self) -> float:
        return float(self.repo.get(KEY_MASTER_VOLUME, 0.8))

    @master_volume.setter
    def master_volume(self, value: float) -> None:
        self.repo.set(KEY_MASTER_VOLUME, max(0.0, min(1.0, float(value))))

    @property
    def fallback_sound_version_id(self) -> str | None:
        return self.repo.get(KEY_FALLBACK_SOUND, None)

    @fallback_sound_version_id.setter
    def fallback_sound_version_id(self, value: str | None) -> None:
        self.repo.set(KEY_FALLBACK_SOUND, value)

    @property
    def boss_fallback_sound_version_id(self) -> str | None:
        """The Boss defeat sound used when the day's character has none."""
        return self.repo.get(KEY_BOSS_FALLBACK_SOUND, None)

    @boss_fallback_sound_version_id.setter
    def boss_fallback_sound_version_id(self, value: str | None) -> None:
        self.repo.set(KEY_BOSS_FALLBACK_SOUND, value)

    # -- interface ----------------------------------------------------
    @property
    def reduced_animation(self) -> bool:
        return bool(self.repo.get(KEY_REDUCED_ANIMATION, False))

    @reduced_animation.setter
    def reduced_animation(self, value: bool) -> None:
        self.repo.set(KEY_REDUCED_ANIMATION, bool(value))

    @property
    def boss_banner_enabled(self) -> bool:
        return bool(self.repo.get(KEY_BOSS_BANNER, True))

    @boss_banner_enabled.setter
    def boss_banner_enabled(self, value: bool) -> None:
        self.repo.set(KEY_BOSS_BANNER, bool(value))

    @property
    def week_start(self) -> str:
        return str(self.repo.get(KEY_WEEK_START, "monday"))

    @week_start.setter
    def week_start(self, value: str) -> None:
        if value not in ("monday", "sunday"):
            raise ValueError("week_start must be 'monday' or 'sunday'")
        self.repo.set(KEY_WEEK_START, value)

    @property
    def board_background(self) -> str:
        name = str(self.repo.get(KEY_BOARD_BACKGROUND, "Recessed"))
        return name if name in BOARD_BACKGROUNDS else "Recessed"

    @board_background.setter
    def board_background(self, value: str) -> None:
        if value not in BOARD_BACKGROUNDS:
            raise ValueError(f"unknown board background: {value}")
        self.repo.set(KEY_BOARD_BACKGROUND, value)

    @property
    def board_background_color(self) -> str:
        return BOARD_BACKGROUNDS[self.board_background]

    def export_dict(self) -> dict[str, object]:
        return self.repo.all()
