"""Import, validate, version and resolve managed media assets.

Imported files are copied into the app-managed data directory; nothing ever
depends on the original source path. Replacing an image or sound creates a
new immutable version, so historical records keep rendering the exact bytes
they were created with.
"""

from __future__ import annotations

import shutil
from pathlib import Path

from task_stamps.config import AppConfig
from task_stamps.data.repositories.assets import AssetRepository
from task_stamps.domain.enums import AssetType
from task_stamps.domain.exceptions import AssetImportError, AssetInUseError
from task_stamps.domain.models import AssetVersion
from task_stamps.utilities.files import sha256_of
from task_stamps.utilities.ids import new_id
from task_stamps.utilities.logging_setup import get_logger

logger = get_logger("assets")

_IMAGE_TYPES = {AssetType.WORLD_COVER, AssetType.PORTRAIT, AssetType.STAMP_IMAGE}

_IMAGE_EXTENSIONS = {".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".webp": "image/webp"}
_SOUND_EXTENSIONS = {".wav": "audio/wav", ".mp3": "audio/mpeg", ".ogg": "audio/ogg"}

_SUBDIR_BY_TYPE = {
    AssetType.WORLD_COVER: "worlds",
    AssetType.PORTRAIT: "characters",
    AssetType.STAMP_IMAGE: "stamps",
    AssetType.SOUND: "sounds",
}


def _sniff_image(header: bytes, extension: str) -> bool:
    if extension == ".png":
        return header.startswith(b"\x89PNG\r\n\x1a\n")
    if extension in (".jpg", ".jpeg"):
        return header.startswith(b"\xff\xd8\xff")
    if extension == ".webp":
        return header[:4] == b"RIFF" and header[8:12] == b"WEBP"
    return False


def _sniff_sound(header: bytes, extension: str) -> bool:
    if extension == ".wav":
        return header[:4] == b"RIFF" and header[8:12] == b"WAVE"
    if extension == ".mp3":
        return header.startswith(b"ID3") or header[:2] in (b"\xff\xfb", b"\xff\xf3", b"\xff\xf2", b"\xff\xfa")
    if extension == ".ogg":
        return header.startswith(b"OggS")
    return False


class AssetService:
    def __init__(self, config: AppConfig, assets: AssetRepository) -> None:
        self.config = config
        self.assets = assets

    def import_file(
        self,
        source: Path | str,
        asset_type: AssetType,
        existing_asset_id: str | None = None,
    ) -> AssetVersion:
        """Copy a file into managed storage and record a new immutable version.

        When ``existing_asset_id`` is given, the new version replaces the
        asset's *current* version without touching older versions.
        """
        source = Path(source)
        if not source.is_file():
            raise AssetImportError(f"The selected file does not exist: {source.name}")
        extension = source.suffix.lower()
        allowed = _IMAGE_EXTENSIONS if asset_type in _IMAGE_TYPES else _SOUND_EXTENSIONS
        if extension not in allowed:
            kind = "image (PNG, JPEG, WebP)" if asset_type in _IMAGE_TYPES else "sound (WAV, MP3, OGG)"
            raise AssetImportError(
                f"'{source.name}' is not a supported {kind} file."
            )
        try:
            header = source.open("rb").read(16)
        except OSError as error:
            raise AssetImportError(f"The file could not be read: {source.name}") from error
        sniffer = _sniff_image if asset_type in _IMAGE_TYPES else _sniff_sound
        if not sniffer(header, extension):
            raise AssetImportError(
                f"'{source.name}' does not look like a valid {extension} file."
            )

        version_id = new_id()
        subdir = _SUBDIR_BY_TYPE[asset_type]
        relative_path = f"assets/{subdir}/{version_id}{extension}"
        destination = self.config.data_dir / relative_path
        try:
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, destination)
        except OSError as error:
            logger.exception("Asset copy failed: %s -> %s", source, destination)
            raise AssetImportError(
                f"Copying '{source.name}' into the app data directory failed."
            ) from error

        try:
            if existing_asset_id is not None:
                asset = self.assets.get_asset(existing_asset_id)
            else:
                asset = self.assets.create_asset(asset_type)
            return self.assets.add_version(
                version_id=version_id,
                asset_id=asset.id,
                relative_path=relative_path,
                file_name=source.name,
                mime_type=allowed[extension],
                file_size=destination.stat().st_size,
                checksum=sha256_of(destination),
            )
        except Exception:
            destination.unlink(missing_ok=True)
            raise

    def replace_version(
        self, old_version_id: str | None, source: Path | str, asset_type: AssetType
    ) -> AssetVersion:
        """Import a new version of the same logical asset (or a new asset)."""
        asset_id = None
        if old_version_id is not None:
            old = self.assets.find_version(old_version_id)
            asset_id = old.asset_id if old else None
        return self.import_file(source, asset_type, existing_asset_id=asset_id)

    def absolute_path(self, version: AssetVersion) -> Path:
        path = (self.config.data_dir / version.relative_path).resolve()
        if self.config.data_dir.resolve() not in path.parents:
            raise AssetImportError("Asset path escapes the data directory.")
        return path

    def path_for_version_id(self, version_id: str | None) -> Path | None:
        version = self.assets.find_version(version_id)
        if version is None:
            return None
        path = self.absolute_path(version)
        return path if path.is_file() else None

    def relative_src(self, version_id: str | None) -> str | None:
        """Flet image src relative to the served data directory."""
        version = self.assets.find_version(version_id)
        if version is None:
            return None
        return "/" + version.relative_path

    def relative_path(self, version_id: str | None) -> str | None:
        """Return an asset version's path relative to the data directory."""
        version = self.assets.find_version(version_id)
        return version.relative_path if version else None

    def cleanup_unreferenced_versions(self) -> int:
        """Explicit maintenance: delete files no record references anymore."""
        removed = 0
        for version in self.assets.unreferenced_versions():
            if self.assets.is_version_referenced(version.id):
                raise AssetInUseError(
                    "Refusing to delete an asset version that is still referenced."
                )
            path = self.config.data_dir / version.relative_path
            path.unlink(missing_ok=True)
            self.assets.delete_version(version.id)
            removed += 1
        logger.info("Cleaned up %s unreferenced asset versions", removed)
        return removed
