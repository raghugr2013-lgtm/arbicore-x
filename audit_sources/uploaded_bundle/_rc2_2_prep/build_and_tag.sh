#!/usr/bin/env bash
# =============================================================================
#  ArbiCore X — RC2.2 Dependency-Resolution Patch: Build Tarball + SHASUMS
# =============================================================================
#
#  Adapted from RC2.1 build_and_tag.sh (v2.2). Same layout auto-detect, same
#  git-archive reproducible-tarball approach, same Windows/Git Bash
#  compatibility (--force-local + cygpath POSIX normalization), same gated
#  post-build verification.
#
#  RC2.2-specific assertions added:
#    - VERSION = arbicore-x-vps-bundle-0.1.0-rc2.2
#    - RELEASE_NOTES_v0.1.0-rc2.2.md present + references RC2.2
#    - app/frontend/yarn.lock present, has yarn 1 header, contains
#      react-day-picker@8.10.1 + date-fns@4.1.0
#    - app/frontend/.npmrc present, contains legacy-peer-deps=true
#    - RC2.1 packaging fix still present (Dockerfiles, .dockerignore,
#      compose build contexts)
# =============================================================================

set -euo pipefail
die() { echo "ERROR: $*" >&2; exit 2; }
fail_verify() { echo "  x $*" >&2; VERIFY_ERRORS=$((VERIFY_ERRORS + 1)); }
pass_verify() { echo "  v $*"; }

REPO_ROOT="$(git rev-parse --show-toplevel 2>/dev/null || true)"
[ -n "$REPO_ROOT" ] || die "not in a git repo"
cd "$REPO_ROOT"

detect_bundle_root() { [ -f "$1/VERSION" ] && [ -f "$1/DEPLOYMENT_MANIFEST.md" ]; }
if   detect_bundle_root "$REPO_ROOT/arbicore-x-vps-bundle"; then
  BUNDLE_LAYOUT="nested"; BUNDLE_ROOT="$REPO_ROOT/arbicore-x-vps-bundle"; BUNDLE_REL="arbicore-x-vps-bundle"
elif detect_bundle_root "$REPO_ROOT"; then
  BUNDLE_LAYOUT="flat";   BUNDLE_ROOT="$REPO_ROOT";                        BUNDLE_REL="."
else
  die "could not locate bundle root; did APPLY.sh run?"
fi

VERSION_STRING="$(cat "$BUNDLE_ROOT/VERSION")"
[ "$VERSION_STRING" = "arbicore-x-vps-bundle-0.1.0-rc2.2" ] \
  || die "expected VERSION 'arbicore-x-vps-bundle-0.1.0-rc2.2', got: '$VERSION_STRING'"

TARBALL="$REPO_ROOT/arbicore-x-vps-bundle-0.1.0-rc2.2.tar.gz"
SHASUMS="$REPO_ROOT/arbicore-x-vps-bundle-0.1.0-rc2.2.SHASUMS"

echo "Layout          : $BUNDLE_LAYOUT"
echo "Bundle root     : $BUNDLE_ROOT"
echo "Tarball target  : $TARBALL"
echo ""

# ============================================================= [1/5] build
echo "[1/5] Building reproducible tarball (git archive)"
if [ "$BUNDLE_LAYOUT" = "nested" ]; then
  git archive --format=tar --prefix=arbicore-x-vps-bundle/ "HEAD:arbicore-x-vps-bundle" | gzip -n > "$TARBALL"
else
  git archive --format=tar --prefix=arbicore-x-vps-bundle/ HEAD                          | gzip -n > "$TARBALL"
fi
ls -l "$TARBALL"

# ============================================================= [2/5] checksums
echo ""
echo "[2/5] Computing checksums"
SHA256="$(sha256sum "$TARBALL" | awk '{print $1}')"
MD5="$(md5sum   "$TARBALL" | awk '{print $1}')"
echo "SHA-256: $SHA256"
echo "MD5    : $MD5"

cat > "$SHASUMS" <<EOF
$SHA256  arbicore-x-vps-bundle-0.1.0-rc2.2.tar.gz
$MD5  arbicore-x-vps-bundle-0.1.0-rc2.2.tar.gz
EOF
echo "       wrote $(basename "$SHASUMS")"

# ============================================================= [3/5] verify
echo ""
echo "[3/5] Post-build verification"
VERIFY_DIR="$(mktemp -d)"
trap 'rm -rf "$VERIFY_DIR"' EXIT
VERIFY_ERRORS=0

tar_path() { if command -v cygpath >/dev/null 2>&1; then cygpath -u "$1"; else printf '%s\n' "$1"; fi; }
TARBALL_POSIX="$(tar_path "$TARBALL")"
VERIFY_DIR_POSIX="$(tar_path "$VERIFY_DIR")"
TAR_LOCAL_OPT="--force-local"
echo "       archive path (as tar sees it): $TARBALL_POSIX"
echo "       verify dir   (as tar sees it): $VERIFY_DIR_POSIX"

# 3.1 archive integrity
tar $TAR_LOCAL_OPT -tzf "$TARBALL_POSIX" >/dev/null 2>&1 \
  && pass_verify "archive integrity (tar -tzf clean)" \
  || fail_verify "archive integrity"
tar $TAR_LOCAL_OPT -xzf "$TARBALL_POSIX" -C "$VERIFY_DIR_POSIX"

# 3.2 top-level
TOP="$(ls -1 "$VERIFY_DIR")"
[ "$(echo "$TOP" | wc -l | tr -d ' ')" = "1" ] && [ "$TOP" = "arbicore-x-vps-bundle" ] \
  && pass_verify "expected top-level directory: arbicore-x-vps-bundle/" \
  || fail_verify "top-level dir mismatch: $TOP"
B="$VERIFY_DIR/arbicore-x-vps-bundle"

# 3.3 VERSION
V="$(cat "$B/VERSION" 2>/dev/null | tr -d '[:space:]')"
[ "$V" = "arbicore-x-vps-bundle-0.1.0-rc2.2" ] \
  && pass_verify "VERSION correct: $V" || fail_verify "VERSION: got '$V'"

# 3.4 DEPLOYMENT_MANIFEST
[ -f "$B/DEPLOYMENT_MANIFEST.md" ] && grep -q 'arbicore-x-vps-bundle-0.1.0-rc2.2' "$B/DEPLOYMENT_MANIFEST.md" \
  && pass_verify "DEPLOYMENT_MANIFEST.md references RC2.2" \
  || fail_verify "DEPLOYMENT_MANIFEST.md missing or lacks RC2.2 identity"

# 3.5 RELEASE_NOTES_v0.1.0-rc2.2.md
[ -f "$B/RELEASE_NOTES_v0.1.0-rc2.2.md" ] && grep -q 'arbicore-x-vps-bundle-0.1.0-rc2.2' "$B/RELEASE_NOTES_v0.1.0-rc2.2.md" \
  && pass_verify "RELEASE_NOTES_v0.1.0-rc2.2.md references RC2.2" \
  || fail_verify "RELEASE_NOTES_v0.1.0-rc2.2.md missing or wrong"

# 3.6 RC2 heritage: env templates
for t in .env.example .env.production.example .env.development.example; do
  [ -f "$B/$t" ] && pass_verify "RC2 env template present: $t" || fail_verify "env template missing: $t"
done

# 3.7 RC2 heritage: shared-infra
for f in \
  infrastructure/shared-infrastructure/docker-compose.shared.yml \
  infrastructure/shared-infrastructure/.env.shared.example \
  infrastructure/shared-infrastructure/README.md \
  docs/SHARED_INFRASTRUCTURE.md ; do
  [ -f "$B/$f" ] && pass_verify "RC2 shared-infra: $f" || fail_verify "shared-infra missing: $f"
done

# 3.8 RC2.1 heritage: .dockerignore
[ -f "$B/.dockerignore" ] && pass_verify "RC2.1 .dockerignore present" \
  || fail_verify "RC2.1 .dockerignore missing"

# 3.9 RC2.1 heritage: Dockerfiles use bundle-root-relative COPY
grep -q 'COPY app/frontend/package.json' "$B/infrastructure/greenfield/frontend/Dockerfile" \
  && grep -q 'infrastructure/greenfield/frontend/nginx-spa.conf' "$B/infrastructure/greenfield/frontend/Dockerfile" \
  && pass_verify "RC2.1 frontend Dockerfile uses bundle-root paths" \
  || fail_verify "RC2.1 frontend Dockerfile lost bundle-root paths"

grep -q 'COPY app/opportunity_center/package.json' "$B/infrastructure/greenfield/opportunity_center/Dockerfile" \
  && grep -q 'infrastructure/greenfield/opportunity_center/nginx-spa.conf' "$B/infrastructure/greenfield/opportunity_center/Dockerfile" \
  && pass_verify "RC2.1 opportunity_center Dockerfile uses bundle-root paths" \
  || fail_verify "RC2.1 opportunity_center Dockerfile lost bundle-root paths"

# 3.10 RC2.1 heritage: yarn.lock optional + npm fallback still in Dockerfile
grep -q 'yarn.lock\*' "$B/infrastructure/greenfield/frontend/Dockerfile" \
  && grep -q 'npm ci'  "$B/infrastructure/greenfield/frontend/Dockerfile" \
  && pass_verify "RC2.1 install fallthrough logic intact in frontend Dockerfile" \
  || fail_verify "RC2.1 install fallthrough logic lost"

# 3.11 RC2.1 heritage: compose file references both greenfield Dockerfiles
grep -q 'infrastructure/greenfield/frontend/Dockerfile' "$B/infrastructure/greenfield/docker-compose.yml" \
  && grep -q 'infrastructure/greenfield/opportunity_center/Dockerfile' "$B/infrastructure/greenfield/docker-compose.yml" \
  && pass_verify "RC2.1 compose build contexts intact" \
  || fail_verify "RC2.1 compose build contexts lost"

# 3.12 RC2.2 NEW: yarn.lock present with expected header + entries
if [ -f "$B/app/frontend/yarn.lock" ]; then
  head -3 "$B/app/frontend/yarn.lock" | grep -q 'yarn lockfile v1' \
    && pass_verify "RC2.2 yarn.lock present with yarn 1 header" \
    || fail_verify "RC2.2 yarn.lock header not yarn 1"
  grep -q '^react-day-picker@8.10.1:' "$B/app/frontend/yarn.lock" \
    && pass_verify "RC2.2 yarn.lock pins react-day-picker@8.10.1" \
    || fail_verify "RC2.2 yarn.lock missing react-day-picker@8.10.1"
  grep -q '^date-fns@4.1.0:'          "$B/app/frontend/yarn.lock" \
    && pass_verify "RC2.2 yarn.lock pins date-fns@4.1.0" \
    || fail_verify "RC2.2 yarn.lock missing date-fns@4.1.0"
else
  fail_verify "RC2.2 app/frontend/yarn.lock missing"
fi

# 3.13 RC2.2 NEW: .npmrc present with legacy-peer-deps=true
if [ -f "$B/app/frontend/.npmrc" ]; then
  grep -q '^legacy-peer-deps=true$' "$B/app/frontend/.npmrc" \
    && pass_verify "RC2.2 .npmrc sets legacy-peer-deps=true" \
    || fail_verify "RC2.2 .npmrc missing legacy-peer-deps=true"
else
  fail_verify "RC2.2 app/frontend/.npmrc missing"
fi

# 3.14 RC2.2 NEW: package.json is UNCHANGED — no dep version drift
if [ -f "$B/app/frontend/package.json" ]; then
  # sanity: this must still declare react-day-picker@8.10.1 + date-fns@4.1.0
  grep -q '"react-day-picker":.*"8.10.1"' "$B/app/frontend/package.json" \
    && grep -q '"date-fns":.*"4.1.0"'     "$B/app/frontend/package.json" \
    && pass_verify "RC2.2 package.json dep versions unchanged" \
    || fail_verify "RC2.2 package.json shows unexpected dep version drift"
fi

# 3.15 gate
if [ "$VERIFY_ERRORS" -gt 0 ]; then
  echo "" >&2
  echo "ABORT: $VERIFY_ERRORS post-build verification error(s)." >&2
  echo "       SHA backfill + SHASUMS-commit command NOT emitted." >&2
  exit 4
fi
echo ""
echo "       post-build verification: ALL CHECKS PASSED"

# ============================================================= [4/5] backfill
echo ""
echo "[4/5] Backfilling SHA-256 into RELEASE_NOTES + DEPLOYMENT_MANIFEST"
sed -i.bak -E "s|^\*\*Bundle SHA-256:\*\* .*$|**Bundle SHA-256:** \`$SHA256\`|" \
  "$BUNDLE_ROOT/RELEASE_NOTES_v0.1.0-rc2.2.md"
rm -f "$BUNDLE_ROOT/RELEASE_NOTES_v0.1.0-rc2.2.md.bak"

sed -i.bak -E "s|\*\(pending regeneration by \`build_and_tag.sh\`\)\*|\`$SHA256\`|" \
  "$BUNDLE_ROOT/DEPLOYMENT_MANIFEST.md"
rm -f "$BUNDLE_ROOT/DEPLOYMENT_MANIFEST.md.bak"
echo "       both files updated to reference $SHA256"

# ============================================================= [5/5] three-way + emit
echo ""
echo "[5/5] Verifying three-way agreement of the SHA-256"
grep -q "$SHA256" "$SHASUMS"                                              || die "SHASUMS mismatch"
grep -q "$SHA256" "$BUNDLE_ROOT/RELEASE_NOTES_v0.1.0-rc2.2.md"            || die "RELEASE_NOTES mismatch"
grep -q "$SHA256" "$BUNDLE_ROOT/DEPLOYMENT_MANIFEST.md"                   || die "DEPLOYMENT_MANIFEST mismatch"
echo "       all three copies agree"

if [ "$BUNDLE_REL" = "." ]; then
  RN_PATH="RELEASE_NOTES_v0.1.0-rc2.2.md"; DM_PATH="DEPLOYMENT_MANIFEST.md"
else
  RN_PATH="$BUNDLE_REL/RELEASE_NOTES_v0.1.0-rc2.2.md"; DM_PATH="$BUNDLE_REL/DEPLOYMENT_MANIFEST.md"
fi

echo ""
echo "===================================================================="
echo "  TARBALL + SHASUMS + BACKFILL COMPLETE  (verification: PASSED)"
echo "===================================================================="
echo ""
echo "Files:"
echo "  $TARBALL"
echo "  $SHASUMS"
echo ""
echo "SHA-256: $SHA256"
echo ""
echo "Next: commit SHASUMS as a separate audit-friendly commit:"
echo "  cd $REPO_ROOT"
echo "  git add \\"
echo "    arbicore-x-vps-bundle-0.1.0-rc2.2.SHASUMS \\"
echo "    $RN_PATH \\"
echo "    $DM_PATH"
echo "  git commit -m 'prep(rc2.2): SHASUMS ($SHA256) + release-notes hash backfill'"
echo ""
echo "Then (only when ready to tag):"
echo "  git tag -a v0.1.0-rc2.2 HEAD -m 'ArbiCore X VPS Bundle v0.1.0 RC 2.2 (dependency-resolution patch)'"
echo "  git push origin main && git push origin v0.1.0-rc2.2"
echo ""
