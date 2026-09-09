"""World Hub conformance.

The kit ships a checker; this runs it as part of the suite so the standard is
something the build enforces rather than something a document asks anyone to
remember. It covers the contract's vocabulary, recipe names written into code,
compatibility gating, whether the conformance fixtures are stale, and the two
install-time traps that are invisible until they fire.

If this fails, read the message: it names the file, the line, and the fix.
Full details are in vendor/worldhub-kit/CONSUMER_GUIDE.md.
"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

APP_ROOT = Path(__file__).resolve().parents[2]
VERIFY = APP_ROOT / "vendor" / "worldhub-kit" / "js" / "verify.mjs"


@pytest.mark.skipif(shutil.which("node") is None, reason="node is not available")
def test_world_hub_conformance():
    assert VERIFY.is_file(), (
        "vendor/worldhub-kit is missing. Run `node scripts/kit-sync.mjs taskstamps` from World Hub."
    )
    result = subprocess.run(
        ["node", str(VERIFY), "--app-root", str(APP_ROOT)],
        capture_output=True, text=True, check=False,
    )
    assert result.returncode == 0, f"\n{result.stdout}{result.stderr}"
