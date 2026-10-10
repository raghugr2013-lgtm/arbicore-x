#!/bin/bash
set -euo pipefail
# Restore pre-R1 Caddyfile and reload (uses docker root for file copy)
docker run --rm -v /opt/caddy:/opt/caddy:rw alpine:3.20 \
  cp -a "/opt/caddy/Caddyfile.pre-r1-docs-deny-20261010T085028Z" /opt/caddy/Caddyfile
docker exec caddy caddy reload --config /etc/caddy/Caddyfile --adapter caddyfile
