"""World Hub identity columns.

Hub entity/asset UUIDs are stored as stable external ids on locally
imported records, so publication updates can reconcile by identity and
existing local records never need their primary keys rewritten.
"""

SQL = """
ALTER TABLE worlds ADD COLUMN hub_id TEXT;
ALTER TABLE characters ADD COLUMN hub_id TEXT;
ALTER TABLE assets ADD COLUMN hub_id TEXT;
CREATE UNIQUE INDEX ix_worlds_hub ON worlds(hub_id) WHERE hub_id IS NOT NULL;
CREATE UNIQUE INDEX ix_characters_hub ON characters(hub_id) WHERE hub_id IS NOT NULL;
CREATE UNIQUE INDEX ix_assets_hub ON assets(hub_id) WHERE hub_id IS NOT NULL
"""
