"""World Hub package reading and protocol validation.

Implements the consumer side of World Hub Package Protocol 1: safe ZIP
extraction, manifest and embedded-contract validation, full checksum
verification, and reference resolution — all before any application
state changes. This module knows the protocol, not the application; the
same behavioral rules are replicated in every World Hub consumer.
"""

from __future__ import annotations

import hashlib
import json
import shutil
import zipfile
from dataclasses import dataclass, field
from pathlib import Path

SUPPORTED_PROTOCOL_VERSIONS = {1}
SUPPORTED_CONTRACT_VERSIONS = {1}
PACKAGE_FORMAT = "world-hub-package"
CONTRACT_FORMAT = "world-hub-application-contract"


class PackageError(Exception):
    """A package failed validation. The message is user-facing."""


@dataclass
class PackageInfo:
    root: Path
    manifest: dict
    contract: dict
    content: dict
    entities: list[dict]
    worlds: list[dict]
    characters: list[dict]
    relationships: list[dict]
    documents: list[dict]
    asset_index: list[dict]
    checksums: dict[str, str]
    tags: list[dict] = field(default_factory=list)

    @property
    def publication_id(self) -> str:
        return self.manifest["publicationId"]

    @property
    def production_id(self) -> str:
        return self.manifest["production"]["id"]

    def entities_by_id(self) -> dict[str, dict]:
        return {entity["id"]: entity for entity in self.entities}

    def asset_entries(self, asset_id: str) -> list[dict]:
        return [entry for entry in self.asset_index if entry["assetId"] == asset_id]

    def asset_file(self, asset_id: str, preferred_recipes: list[str]) -> dict | None:
        """The best index entry for an asset given a recipe preference order."""
        entries = self.asset_entries(asset_id)
        for recipe in preferred_recipes:
            for entry in entries:
                if entry["recipeId"] == recipe:
                    return entry
        return entries[0] if entries else None

    def absolute(self, package_path: str) -> Path:
        return self.root / Path(*package_path.split("/"))


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(65536), b""):
            digest.update(chunk)
    return digest.hexdigest()


def extract_zip_safely(zip_path: Path, destination: Path) -> None:
    """Extract a package ZIP, refusing unsafe entries outright."""
    destination.mkdir(parents=True, exist_ok=True)
    resolved_destination = destination.resolve()
    seen: set[str] = set()
    try:
        with zipfile.ZipFile(zip_path) as archive:
            for info in archive.infolist():
                name = info.filename
                if name.endswith("/"):
                    continue
                if name in seen:
                    raise PackageError("The archive contains duplicate entries and was rejected.")
                seen.add(name)
                normalized = name.replace("\\", "/")
                if normalized.startswith("/") or ".." in normalized.split("/") or ":" in normalized.split("/")[0]:
                    raise PackageError("The archive contains unsafe file paths and was rejected.")
                if (info.external_attr >> 16) & 0o170000 == 0o120000:
                    raise PackageError("The archive contains symbolic links and was rejected.")
                target = (destination / Path(*normalized.split("/"))).resolve()
                if resolved_destination != target and resolved_destination not in target.parents:
                    raise PackageError("The archive contains unsafe file paths and was rejected.")
                target.parent.mkdir(parents=True, exist_ok=True)
                with archive.open(info) as source, target.open("wb") as out:
                    shutil.copyfileobj(source, out)
    except zipfile.BadZipFile as error:
        raise PackageError("The file is not a readable ZIP archive.") from error


def _read_json(root: Path, package_path: str) -> object:
    path = root / Path(*package_path.split("/"))
    if not path.is_file():
        raise PackageError(f"The package is missing {package_path}.")
    try:
        return json.loads(path.read_text("utf-8"))
    except json.JSONDecodeError as error:
        raise PackageError(f"The package file {package_path} is not valid JSON.") from error


def load_package(root: Path, expected_app_type: str) -> PackageInfo:
    """Validate a package directory completely; raise PackageError otherwise."""
    manifest = _read_json(root, "manifest.json")
    if not isinstance(manifest, dict) or manifest.get("format") != PACKAGE_FORMAT:
        raise PackageError("This is not a World Hub package.")
    if manifest.get("protocolVersion") not in SUPPORTED_PROTOCOL_VERSIONS:
        raise PackageError(
            "This package uses a newer World Hub protocol than this app understands."
        )
    if manifest.get("complete") is not True:
        raise PackageError("The package is marked incomplete.")
    if manifest.get("applicationType") != expected_app_type:
        raise PackageError(
            f"This package is for “{manifest.get('applicationType')}”, not for this app."
        )
    for key in ("publicationId", "production", "contract", "sourceLibraryId", "publishedAt", "entities", "sections"):
        if key not in manifest:
            raise PackageError(f"The package manifest is missing {key}.")

    contract = _read_json(root, "production/contract.json")
    if not isinstance(contract, dict) or contract.get("format") != CONTRACT_FORMAT:
        raise PackageError("The embedded application contract is not valid.")
    if contract.get("appType") != manifest["applicationType"]:
        raise PackageError("The embedded contract does not match the package's application type.")
    if manifest["contract"].get("version") not in SUPPORTED_CONTRACT_VERSIONS:
        raise PackageError("This package uses a contract version this app does not support.")
    if contract.get("contractVersion") not in SUPPORTED_CONTRACT_VERSIONS:
        raise PackageError("This package uses a contract format this app does not support.")

    checksums = _read_json(root, "checksums.json")
    if not isinstance(checksums, dict):
        raise PackageError("The package checksum list is unreadable.")
    for package_path, expected in checksums.items():
        file_path = root / Path(*package_path.split("/"))
        if not file_path.is_file():
            raise PackageError(f"The package is missing {package_path}.")
        if _sha256(file_path) != expected:
            raise PackageError(f"A package file failed its checksum: {package_path}.")
    listed = set(checksums.keys()) | {"checksums.json"}
    for file_path in sorted(root.rglob("*")):
        if file_path.is_file():
            relative = "/".join(file_path.relative_to(root).parts)
            if relative not in listed:
                raise PackageError(f"The package contains an unlisted file: {relative}.")

    entities = _read_json(root, "catalog/entities.json")
    worlds = _read_json(root, "catalog/worlds.json")
    characters = _read_json(root, "catalog/characters.json")
    relationships = _read_json(root, "catalog/relationships.json")
    documents = _read_json(root, "catalog/documents.json")
    tags = _read_json(root, "catalog/tags.json")
    asset_index = _read_json(root, "assets/index.json")
    content = _read_json(root, "production/content.json")

    entity_ids = {entity["id"] for entity in entities}
    for relationship in relationships:
        if relationship["sourceId"] not in entity_ids or relationship["targetId"] not in entity_ids:
            raise PackageError("A packaged relationship references a missing record.")
    for document in documents:
        for entity_id in document.get("entityIds", []):
            if entity_id not in entity_ids:
                raise PackageError("A packaged document references a missing record.")
        if not (root / Path(*document["path"].split("/"))).is_file():
            raise PackageError(f"A document file is missing: {document['path']}.")
    asset_ids = {entry["assetId"] for entry in asset_index}
    for entry in asset_index:
        if not (root / Path(*entry["path"].split("/"))).is_file():
            raise PackageError(f"An asset file is missing: {entry['path']}.")
    for world in worlds:
        for ref in (world.get("coverAssetId"), world.get("backgroundAssetId")):
            if ref and ref not in asset_ids:
                raise PackageError("A world profile references a missing asset.")
    for character in characters:
        for ref in (character.get("portraitAssetId"), character.get("fullBodyAssetId")):
            if ref and ref not in asset_ids:
                raise PackageError("A character profile references a missing asset.")
    for slot, selected in (content.get("selections") or {}).items():
        for entity_id in selected:
            if entity_id not in entity_ids:
                raise PackageError(f"Selection “{slot}” references a missing record.")
    for set_key, items in (content.get("assetSets") or {}).items():
        for item in items:
            if item["assetId"] not in asset_ids:
                raise PackageError(f"Asset set “{set_key}” references a missing asset.")

    return PackageInfo(
        root=root,
        manifest=manifest,
        contract=contract,
        content=content,
        entities=entities,
        worlds=worlds,
        characters=characters,
        relationships=relationships,
        documents=documents,
        asset_index=asset_index,
        checksums=checksums,
        tags=tags,
    )


def read_current_pointer(production_dir: Path) -> dict | None:
    """Read current.json from a linked World Hub production folder."""
    pointer_path = production_dir / "current.json"
    try:
        pointer = json.loads(pointer_path.read_text("utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    if not isinstance(pointer, dict) or "publicationId" not in pointer:
        return None
    return pointer
