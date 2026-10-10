#!/usr/bin/env bash
# R4-SCRUB Phase A restore — reverse quarantine moves (before destroy only).
set -euo pipefail
EVID_DIR="/home/raghu/projects/arbicore-x-cert/artifacts/security/r4_scrub_phase_a_20261010T122730Z"
python3 - "$EVID_DIR/move_map.json" <<'PY'
import json, shutil, sys
from pathlib import Path
m = json.loads(Path(sys.argv[1]).read_text())
for row in m['moves']:
    src = Path(row['destination'])
    dst = Path(row['source'])
    if not src.is_file():
        raise SystemExit(f'missing quarantine file: {src}')
    if dst.exists():
        raise SystemExit(f'restore target exists: {dst}')
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.move(str(src), str(dst))
    print(f'restored {dst}')
print('restore complete')
PY
