# Deploy 27dfab4 — Verification — 2026-10-03

- **Status:** Frontend deploy finished. Backend was already on this commit. No source change, no Network Config SAVE/APPLY, no BNB activation, no SHADOW/Gate 9/M5/Alchemy work.
- **Commit:** `27dfab42ae6981b39628c04fd9d1b869c3f6c57b`
- **Verified (UTC):** `2026-10-03T14:26Z` (frontend container started `2026-10-03T14:24:18Z`)
- **Secrets policy:** RPC credentials not printed. Alchemy key fingerprint is `sha256(<key>)[:8]` of the path segment after `/v2/`.

This note closes the interrupted deploy. An earlier agent built and recreated the backend, then stopped while the frontend image was still failing Yarn registry timeouts. This pass did not rebuild the backend.

---

## Result

| Field | Value |
|---|---|
| **Source commit** | `27dfab42ae6981b39628c04fd9d1b869c3f6c57b` |
| **Frontend image** | `arbicore-x-frontend:27dfab4-20261003` |
| **Frontend digest** | `sha256:d8bf12f0974b19f879d24fa53f062b230a88d3f300369ae77c1211a6d59bebd8` |
| **Frontend created** | `2026-10-03T14:20:23Z` |
| **Frontend container** | `arbicore-x-frontend` (healthy, `healthz` = ok) |
| **Backend image** | `arbicore-x-backend:27dfab4-20261003` |
| **Backend digest** | `sha256:77f0bb536f7f02ca18d18dadb16985aac34e980de5f6de540aaf660a0e7ca2bb` |
| **Backend created** | `2026-10-03T12:34:40Z` |
| **Backend container** | `arbicore-x-backend-new` (healthy, started `2026-10-03T12:42:03Z`, not recreated during the frontend swap) |
| **Backend BUILD_INFO** | `git_sha=27dfab42ae6981b39628c04fd9d1b869c3f6c57b`, `git_tag=27dfab4-20261003`, `app_version=27dfab4`, `build_time=2026-10-03T12:23:06Z` |
| **Bundle** | `static/js/main.c229a593.js` (827171 bytes, mtime `2026-10-03T14:19:45Z`). Replaces September 1 bundle `main.dc5f82a3.js` from `arbicore-x-frontend:0.1.0` (`sha256:69e799f5fc9825c2f572ffa63991845dde3cd9fb4e27daaf7d0b3a22abccdd88`, created `2026-09-01T19:05:01Z`). |
| **Public index** | `https://144-91-78-175.sslip.io/` serves `static/js/main.c229a593.js` and `static/css/main.8abf2014.css` |
| **BNB in Settings → Network** | Present in the running bundle. Frozen allowlist is `["base","ethereum","arbitrum","optimism","polygon","bnb"]` next to the settings subnav (`network`). |
| **Add Network** | Present. Bundle contains the label `Add Network` and test ids `v2-settings-network-add-select` / `v2-settings-network-add-btn`. |
| **Six chains** | `base`, `ethereum`, `arbitrum`, `optimism`, `polygon`, `bnb` |
| **env_sync** | Generalized. Running `/app/arbicore/config/env_sync.py` references `SUPPORTED_CHAINS` (6 mentions). Running `persistent.py` has `SUPPORTED_CHAINS ("base", "ethereum", "arbitrum", "optimism", "polygon", "bnb")`. |
| **Network Config revision** | `rev-7c93bb93e65b4f5a9b7340bf513437c0` |
| **Network Config updated_at** | `2026-10-03T04:57:17.836236+00:00` (unchanged) |
| **Live Network Config** | Base PAYG only. `chains_enabled.base=true`; ethereum, arbitrum, optimism, polygon, and bnb are false. Base RPC `[0]` `base-mainnet.g.alchemy.com` fp `cd505118`; `[1]` `mainnet.base.org`. |
| **ce00e63d** | Absent |
| **APPLY during this deploy** | None. Latest network audit remains the pre-existing `2026-10-03T04:57:17Z` apply of `rev-7c93bb93e65b4f5a9b7340bf513437c0`. |
| **Safety** | `ARBICORE_EXECUTION_MODE=SHADOW`, `ARBICORE_AUTOEXEC_AUTOSTART=false`, `ARBICORE_RUNTIME_AUTOSTART=false`, `ARBICORE_SHADOW_CERT_ENABLED=true` |
| **Rollback images** | Unchanged. `arbicore-x-backend:g5.79-green-20260927` = `sha256:aaadc3a9cc78d695a9e7e2d16681babc71c576033ad3764061a918946d8e993a`. `arbicore-x-backend:ws-a-befb14e-20261002` = `sha256:12759b11a783619ad25746a030c5bbcc71b83ed64ff05b3316153d6402a594ae`. |

Settings → Network was verified from the running bundle and from the public index serving that bundle. The settings screen itself was not clicked; it sits behind operator login, and this pass did not authenticate or change config.

---

## Deployment problem

The committed frontend Dockerfile's `yarn install --frozen-lockfile` could not reach `registry.yarnpkg.com` from `node:20-alpine`. A host-network probe from that image timed out on IPv6 `2606:4700::6810:722` while fetching `date-fns-4.1.0.tgz`. The same probe to `registry.npmjs.org` returned HTTP 200.

One workaround build then succeeded. It did not change the git tree at `27dfab4`:

- `docker build --network=host`
- Yarn network timeout `600000`
- Inside the image only, lockfile tarball URLs were rewritten from `https://registry.yarnpkg.com/` to `https://registry.npmjs.org/` before `yarn install --frozen-lockfile`
- `NODE_OPTIONS=--dns-result-order=ipv4first` for that install

`yarn install` completed in 1822s and `craco build` produced `main.c229a593.js`. The September 1 frontend image was left in place and was not retagged. Only `arbicore-x-frontend` was recreated onto `arbicore-x-frontend:27dfab4-20261003`. Baked API origin remains `https://144-91-78-175.sslip.io`.
