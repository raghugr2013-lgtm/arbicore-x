# backend/ — staging slot for the audited ArbiCore X source

This directory must contain the **audited backend source** before running any step past
`00_detect_env.sh`. Step `01_preflight.sh` will refuse to continue if the expected files
are missing.

## What goes here

Copy the contents of the audited archive's top-level `backend/` into this directory:

```
arbicore-x-deploy/backend/
├── Dockerfile              # ships in this bundle (do NOT overwrite)
├── .dockerignore           # ships in this bundle
├── .env                    # auto-baked by steps/00_detect_env.sh from the LIVE container (chmod 600)
├── server.py               # from the audited backend/
├── requirements.txt        # from the audited backend/
├── arbicore/               # from the audited backend/  (must include intel/launch/labels.json)
├── routes/                 # from the audited backend/  (if present)
├── services/               # from the audited backend/  (if present)
└── models/                 # from the audited backend/  (if present)
```

## What you MUST NOT do here

- Do **not** edit `.env` after `00_detect_env.sh` has written it; it is the exact
  configuration the OLD container is running with, plus the two scanner-preservation
  flags (`ARBICORE_SCANNER_CEX_ARB=on`, `ARBICORE_SCANNER_FUNDING_ARB=on`).
- Do **not** overwrite `Dockerfile` with the audited archive's Dockerfile unless you
  diff them first; the one shipped here is the production-pinned variant.
- Do **not** commit `.env` to git (`.gitignore` already excludes it; verify before any push).

## Quick verification

After copying the audited source in, you can sanity-check by running:

```bash
steps/01_preflight.sh
```

Preflight verifies `server.py`, `requirements.txt`, `Dockerfile`, `.env`, and the
`arbicore/` module are all present before allowing build/cutover.
