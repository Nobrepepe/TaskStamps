"""Move all existing board choices to the dark recessed floor."""

SQL = """
UPDATE app_settings
SET serialized_value = '"Recessed"', updated_at = datetime('now')
WHERE key = 'board_background'
"""
