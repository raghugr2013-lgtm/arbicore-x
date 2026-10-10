#!/usr/bin/env bash
# R5-APPLY rollback — restore pre-containment contracts/.env (re-exposes plaintext key).
set -euo pipefail
ESCROW="/home/raghu/arbicore_backups/r5_deployer_containment_20261010T130403Z/contracts.env.pre-r5"
ENVF="/home/raghu/projects/arbicore-x-v2/contracts/.env"
test -f "$ESCROW"
cp -a "$ESCROW" "$ENVF"
chmod 600 "$ENVF"
echo "restored contracts/.env from escrow; verify DEPLOYER_PRIVATE_KEY present manually (do not print)"
