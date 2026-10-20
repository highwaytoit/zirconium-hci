"""Seed the file-manager shortcut once, preserving user choices thereafter."""

import json
import os
from pathlib import Path
import subprocess
import time


config_dir = Path(os.environ.get("XDG_CONFIG_HOME") or Path.home() / ".config")
state_dir = Path(os.environ.get("XDG_STATE_HOME") or Path.home() / ".local/state")
marker = state_dir / "zirconium/strata-keybind.done"

if marker.exists():
    raise SystemExit(0)

# DMS may still be deploying its configuration when its service becomes ready.
# Leave setup pending for a later session if the managed binds never appear.
binds = config_dir / "niri/dms/binds.kdl"
for _ in range(30):
    if binds.is_file():
        break
    time.sleep(1)
else:
    raise SystemExit("DMS Niri bindings are not available yet")

# Let DMS parse the configuration, including user overrides and includes.
sheet = json.loads(subprocess.check_output(["dms", "keybinds", "show", "niri"]))
existing = any(
    binding["key"].casefold() in {"mod+e", "super+e"}
    for group in sheet["binds"].values()
    for binding in group
)

marker.parent.mkdir(parents=True, exist_ok=True)
if not existing:
    subprocess.run(
        ["dms", "keybinds", "set", "niri", "Mod+E", "spawn strata",
         "--desc", "Open File Manager"],
        check=True,
    )

# Preserving an existing shortcut also completes setup: never claim it later.
marker.touch()
