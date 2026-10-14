"""CLI completion checks against a synthetic database, with no user state changes."""

import json
import os
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
env = dict(os.environ, WHICHCARD_DB=str(ROOT / "var/fixtures.db"), WHICHCARD_TODAY="2026-10-14")
commands = [
    ["recommend", "costco", "--amount", "180"],
    ["trackers"],
    ["insights"],
    ["gap"],
    ["redeem"],
    ["airport", "SFO"],
    ["review"],
    ["ask", "How much dining?"],
    ["cards", "list"],
]
for command in commands:
    result = subprocess.run(
        [str(ROOT / ".venv/bin/whichcard"), *command, "--json"],
        env=env,
        capture_output=True,
        text=True,
        check=True,
    )
    value = json.loads(result.stdout)
    if command[0] == "recommend":
        assert value["ranked"] and all(
            r["reasons"] and r["range"] and r["confidence"] for r in value["ranked"]
        )
    subprocess.run(
        [str(ROOT / ".venv/bin/whichcard"), *command], env=env, capture_output=True, text=True, check=True
    )
    print("CLI passed:", " ".join(command))
