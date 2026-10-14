"""Enforce 80% statement coverage independently for each financial/inference package."""

import json
from pathlib import Path

report = json.loads(Path("var/coverage.json").read_text())
for package in ["engine", "trackers", "analysis", "inference"]:
    files = [v["summary"] for k, v in report["files"].items() if f"/whichcard/{package}/" in k]
    statements = sum(f["num_statements"] for f in files)
    covered = sum(f["covered_lines"] for f in files)
    if statements:
        percent = 100 * covered / statements
        print(f"{package}: {percent:.1f}%")
        if percent < 80:
            raise SystemExit(f"{package} coverage below 80%")
