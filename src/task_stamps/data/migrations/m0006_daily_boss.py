"""Dedicated character Boss media and immutable daily selections."""

SQL = """
ALTER TABLE characters ADD COLUMN boss_image_asset_version_id TEXT
    REFERENCES asset_versions(id);
ALTER TABLE characters ADD COLUMN boss_sound_asset_version_id TEXT
    REFERENCES asset_versions(id);

CREATE TABLE daily_bosses (
    boss_date TEXT PRIMARY KEY,
    character_id TEXT NOT NULL REFERENCES characters(id),
    image_asset_version_id TEXT NOT NULL REFERENCES asset_versions(id),
    sound_asset_version_id TEXT REFERENCES asset_versions(id),
    created_at TEXT NOT NULL
);
CREATE INDEX ix_daily_bosses_character ON daily_bosses(character_id)
"""
