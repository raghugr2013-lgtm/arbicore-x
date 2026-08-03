# ArbiCore X v2.0.5 — Deployment Fix (Missing Eth Stack in Prod Requirements)

**Status:** ✅ **READY FOR DEPLOYMENT**
**Type:** release-engineering patch. **Zero application logic changed.**

## Root cause

`deployment/docker/backend/requirements.prod.txt` was missing the 16-package
eth stack required by `arbicore/execution/{broadcast,calldata}.py` and their
transitive dependencies. The dev `requirements.txt` had all of them; the
prod requirements file did not. Consequence: backend container built cleanly
but crashed on first import inside the runtime image with:

    ModuleNotFoundError: No module named 'eth_abi'

Import chain:  `server.py → arbicore.execution.broadcast → arbicore.execution.calldata → from eth_abi import encode`

## Fix

Added 16 packages to `requirements.prod.txt` (pinned to the exact versions
already in `app/backend/requirements.txt`):

    bitarray==3.10.0       eth-keys==0.7.0        parsimonious==0.10.0
    ckzg==2.1.8            eth-rlp==2.2.0         pycryptodome==3.23.0
    cytoolz==1.1.0         eth-typing==6.0.0      rlp==4.1.0
    eth-account==0.13.7    eth-utils==6.0.0       toolz==1.1.0
    eth-hash==0.8.0        eth_abi==5.2.0
    eth-keyfile==0.8.1     hexbytes==1.3.1

## Verification

**Clean-environment install:** fresh venv with ONLY `requirements.prod.txt` →
`pip install` exit 0 · 136 packages installed.

**Import chain:** every module that failed on the VPS now imports cleanly:
`eth_abi.encode`, `eth_account 0.13.7`, `eth_utils 6.0.0`,
`arbicore.execution.calldata`, `arbicore.execution.broadcast`,
`arbicore.auth`, `arbicore.data.mid`, `server`.

**Runtime smoke test** (isolated prod venv → uvicorn):

    INFO:     Application startup complete.
    GET  /api/                              200  {"message":"Hello World"}
    GET  /api/arbicore/mid/status           200  {available:true, domains:11}
    POST /api/auth/login  (admin creds)     200  {token, user{role:"admin"}}

All 5 background workers started (calibration · MID indexes · auth seed ·
adaptive weights · evidence signing · discovery · auto-executor). No import
errors. No restart loop.

## Regression

Application code untouched. Backend test suite unchanged: **1469 pass**,
76 skipped, 0 failed — identical to v2.0.4.

## Deployment

Same command as v2.0.4:

    git fetch && git checkout v2.0.5
    make build          # will now install the eth stack
    docker run --rm arbicore-x-backend:2.0.5 python -c "from eth_abi import encode; print('OK')"
    docker compose -f deployment/compose/docker-compose.shared.yml up -d

Bump the image-tag default was already at 2.0.3 in v2.0.4; when this ships as
v2.0.5 the operator MAY optionally re-tag their built image as
`arbicore-x-backend:2.0.5` for tracking, but the default `2.0.3` tag also
works — the image tag is decoupled from the app version.

## Rollback

The v2.0.4 image (if built) crash-loops. The v2.0.3 image (if built) also
crash-loops. **v2.0.5 is the first VPS-viable image.** Roll back only to
the pre-v2.0.3 `arbicore-x-backend:1.0.0` on the VPS if v2.0.5 has any
independent issue — the 1.0.0 image predates the execution/broadcast
integration and does not import the eth stack.
