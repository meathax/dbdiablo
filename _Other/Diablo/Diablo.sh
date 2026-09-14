#!/bin/sh
# MiSTer Scripts menu entry. Resolve the transactional activation on every run.
exec python3 - "$@" <<'DIABLO_MENU_PY'
import hashlib
import json
import os
from pathlib import Path
import re
import sys

try:
    root = Path(os.environ.get("DIABLO_INSTALL_ROOT", "/media/fat"))
    state = json.loads((root / ".diablo-install.json").read_text(encoding="utf-8"))
    candidate = state.get("active_candidate_id", "")
    if state.get("schema") != "diablo-install-state-v1" or state.get("status") != "pass":
        raise ValueError("no passing Diablo installation")
    if not isinstance(candidate, str) or not re.fullmatch(r"[0-9a-f]{64}", candidate):
        raise ValueError("invalid active candidate")
    relative = ".diablo-releases/" + candidate
    if state.get("active_release") != relative:
        raise ValueError("invalid active release path")
    package = root / relative
    manifest_path = package / "package-manifest.json"
    launcher = package / "diablo_launcher.py"
    if any(path.is_symlink() for path in (root / ".diablo-releases", package, manifest_path, launcher)):
        raise ValueError("active release must not use symlinks")
    raw = manifest_path.read_bytes()
    if hashlib.sha256(raw).hexdigest() != state.get("active_package_manifest_sha256"):
        raise ValueError("active package manifest hash mismatch")
    manifest = json.loads(raw)
    if manifest.get("candidate_id") != candidate or manifest.get("status") != "pass":
        raise ValueError("active package identity mismatch")
    records = [item for item in manifest.get("files", []) if item.get("path") == "diablo_launcher.py"]
    body = launcher.read_bytes()
    if len(records) != 1 or records[0].get("sha256") != hashlib.sha256(body).hexdigest() or records[0].get("bytes") != len(body):
        raise ValueError("active launcher hash mismatch")
    command = [sys.executable, str(launcher), "--package-root", str(package),
               "--campaign", "diablo", "--data-root",
               os.environ.get("DIABLO_DATA_ROOT", str(root / "games/Diablo")),
               "--save-root", os.environ.get("DIABLO_SAVE_ROOT", str(root / "saves/Diablo")),
               "--config-root", os.environ.get("DIABLO_CONFIG_ROOT", str(root / "config/Diablo"))]
    os.execv(sys.executable, command + sys.argv[1:])
except (OSError, ValueError, TypeError, AttributeError) as error:
    print("Diablo menu: " + str(error), file=sys.stderr)
    sys.exit(1)
DIABLO_MENU_PY
