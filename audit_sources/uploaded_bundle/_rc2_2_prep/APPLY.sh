#!/usr/bin/env bash
# =============================================================================
#  ArbiCore X — RC2.2 Dependency-Resolution Patch: Apply-and-Commit Script
# =============================================================================
#
#  Purpose: apply the frontend reproducibility fix (v0.1.0-rc2.2) into a
#           local checkout of arbicore-x-vps-bundle. Adds exactly two files
#           to app/frontend/ (yarn.lock + .npmrc) and refreshes metadata.
#
#  Two-step user workflow:
#    STEP 1 (dev repo — ArbiCoreX-V01):
#      commit frontend/yarn.lock and frontend/.npmrc to the dev repo `main`
#      (via Emergent Save-to-GitHub or a local commit + push). Note the new
#      dev-repo commit SHA — you pass it as the second arg to this script.
#
#    STEP 2 (release repo — arbicore-x-vps-bundle):
#      run this script inside your local clone of arbicore-x-vps-bundle,
#      passing the new dev-repo SHA:
#
#        bash APPLY.sh /path/to/_rc2_2_prep <NEW_APP_SOURCE_SHA>
#
#      One atomic commit is produced. Does NOT push, does NOT tag, does
#      NOT create a GitHub Release.
# =============================================================================

set -euo pipefail
die() { echo "ERROR: $*" >&2; exit 2; }

# ------------------------------------------------------------------- args
if [ $# -lt 2 ]; then
  cat >&2 <<EOF
Usage: $0 <path-to-_rc2_2_prep> <new-app-source-sha>

  <path-to-_rc2_2_prep>  Extracted scratch directory (contains bundle_root/)
  <new-app-source-sha>   Full 40-char commit SHA of the ArbiCoreX-V01 commit
                          that added frontend/yarn.lock + frontend/.npmrc.
                          Get it with:
                            cd /path/to/ArbiCoreX-V01
                            git log -1 --format=%H

EOF
  exit 2
fi
PATCH_DIR="$(cd "$1" && pwd)"
NEW_APP_SHA="$2"
[ -d "$PATCH_DIR/bundle_root" ] || die "'$PATCH_DIR/bundle_root' missing"
echo "$NEW_APP_SHA" | grep -qE '^[a-f0-9]{40}$' \
  || die "expected 40-char lowercase hex SHA, got: '$NEW_APP_SHA'"
NEW_APP_SHA_SHORT="${NEW_APP_SHA:0:7}"

# ------------------------------------------------------------------- repo + layout
REPO_ROOT="$(git rev-parse --show-toplevel 2>/dev/null || true)"
[ -n "$REPO_ROOT" ] || die "not inside a git repository"

REMOTE_URL="$(git config --get remote.origin.url 2>/dev/null || true)"
echo "$REMOTE_URL" | grep -qE 'arbicore-x-vps-bundle(\.git)?$' \
  || die "origin is not arbicore-x-vps-bundle. Got: '$REMOTE_URL'"

git diff-index --quiet HEAD -- || {
  echo "ERROR: working tree has uncommitted changes. Commit or stash first." >&2
  git status --short >&2; exit 2; }

detect_bundle_root() { [ -f "$1/VERSION" ] && [ -f "$1/DEPLOYMENT_MANIFEST.md" ]; }
if   detect_bundle_root "$REPO_ROOT/arbicore-x-vps-bundle"; then
  BUNDLE_LAYOUT="nested"; BUNDLE_ROOT="$REPO_ROOT/arbicore-x-vps-bundle"; BUNDLE_REL="arbicore-x-vps-bundle"
elif detect_bundle_root "$REPO_ROOT"; then
  BUNDLE_LAYOUT="flat";   BUNDLE_ROOT="$REPO_ROOT";                        BUNDLE_REL="."
else
  die "could not locate bundle root; did earlier APPLYs run?"
fi
brel() { if [ "$BUNDLE_REL" = "." ]; then echo "$1"; else echo "$BUNDLE_REL/$1"; fi; }

# preflight: expect base to be RC2.1 (or RC2.2 on a re-run)
CURR_VER="$(cat "$BUNDLE_ROOT/VERSION")"
case "$CURR_VER" in
  arbicore-x-vps-bundle-0.1.0-rc2.1|arbicore-x-vps-bundle-0.1.0-rc2.2) ;;
  *) die "expected base VERSION rc2.1 (or rc2.2 for re-run), got: '$CURR_VER'" ;;
esac

echo "Applying RC2.2 dependency-resolution patch"
echo "                       from : $PATCH_DIR"
echo "                       into : $REPO_ROOT"
echo "                     layout : $BUNDLE_LAYOUT"
echo "             bundle root at : $BUNDLE_ROOT"
echo "           base VERSION was : $CURR_VER -> arbicore-x-vps-bundle-0.1.0-rc2.2"
echo "     new app-source SHA    : $NEW_APP_SHA ($NEW_APP_SHA_SHORT)"
echo "                       HEAD : $(git rev-parse HEAD)"
echo ""

# ------------------------------------------------------------------- copy payload
echo "[1/5] Copying RC2.2 payload"
mkdir -p "$BUNDLE_ROOT/app/frontend"
cp -v "$PATCH_DIR/bundle_root/app/frontend/yarn.lock"                     "$BUNDLE_ROOT/app/frontend/yarn.lock"
cp -v "$PATCH_DIR/bundle_root/app/frontend/.npmrc"                        "$BUNDLE_ROOT/app/frontend/.npmrc"
cp -v "$PATCH_DIR/bundle_root/VERSION"                                    "$BUNDLE_ROOT/VERSION"
cp -v "$PATCH_DIR/bundle_root/DEPLOYMENT_MANIFEST.md"                     "$BUNDLE_ROOT/DEPLOYMENT_MANIFEST.md"
cp -v "$PATCH_DIR/bundle_root/RELEASE_NOTES_v0.1.0-rc2.2.md"              "$BUNDLE_ROOT/RELEASE_NOTES_v0.1.0-rc2.2.md"

# ------------------------------------------------------------------- backfill SHAs into manifest + release notes
echo ""
echo "[2/5] Backfilling app-source SHA into DEPLOYMENT_MANIFEST + RELEASE_NOTES"
sed -i.bak -E "s|__APP_SOURCE_SHA_RC2_2__|$NEW_APP_SHA|g"        "$BUNDLE_ROOT/DEPLOYMENT_MANIFEST.md"
sed -i.bak -E "s|__APP_SOURCE_SHA_RC2_2_SHORT__|$NEW_APP_SHA_SHORT|g" "$BUNDLE_ROOT/DEPLOYMENT_MANIFEST.md"
sed -i.bak -E "s|__APP_SOURCE_SHA_RC2_2__|$NEW_APP_SHA|g"        "$BUNDLE_ROOT/RELEASE_NOTES_v0.1.0-rc2.2.md"
rm -f "$BUNDLE_ROOT/DEPLOYMENT_MANIFEST.md.bak" "$BUNDLE_ROOT/RELEASE_NOTES_v0.1.0-rc2.2.md.bak"
grep -q "$NEW_APP_SHA"       "$BUNDLE_ROOT/DEPLOYMENT_MANIFEST.md"        || die "SHA backfill failed in manifest"
grep -q "$NEW_APP_SHA_SHORT" "$BUNDLE_ROOT/DEPLOYMENT_MANIFEST.md"        || die "short SHA backfill failed in manifest"
grep -q "$NEW_APP_SHA"       "$BUNDLE_ROOT/RELEASE_NOTES_v0.1.0-rc2.2.md" || die "SHA backfill failed in release notes"
echo "       both files reference $NEW_APP_SHA"

# ------------------------------------------------------------------- consistency
echo ""
echo "[3/5] Consistency checks"
grep -q '^arbicore-x-vps-bundle-0.1.0-rc2.2$' "$BUNDLE_ROOT/VERSION" \
  || die "VERSION did not update to rc2.2"
grep -q 'arbicore-x-vps-bundle-0.1.0-rc2.2' "$BUNDLE_ROOT/DEPLOYMENT_MANIFEST.md" \
  || die "manifest missing rc2.2 identity"
grep -q 'arbicore-x-vps-bundle-0.1.0-rc2.2' "$BUNDLE_ROOT/RELEASE_NOTES_v0.1.0-rc2.2.md" \
  || die "release notes missing rc2.2 identity"

# yarn.lock spot-checks
head -3 "$BUNDLE_ROOT/app/frontend/yarn.lock" | grep -q 'yarn lockfile v1' \
  || die "yarn.lock header not recognized"
grep -q '^react-day-picker@8.10.1:' "$BUNDLE_ROOT/app/frontend/yarn.lock" \
  || die "yarn.lock missing react-day-picker@8.10.1"
grep -q '^date-fns@4.1.0:'          "$BUNDLE_ROOT/app/frontend/yarn.lock" \
  || die "yarn.lock missing date-fns@4.1.0"

# .npmrc content
grep -q '^legacy-peer-deps=true$'   "$BUNDLE_ROOT/app/frontend/.npmrc" \
  || die ".npmrc missing legacy-peer-deps=true"

# byte-identity of protected trees since previous HEAD
BACKEND_PS="$(brel 'app/backend')"
OC_PS="$(brel 'app/opportunity_center')"
REALIGN_PS="$(brel 'infrastructure/realignment')"
SHARED_PS="$(brel 'infrastructure/shared-infrastructure')"
GREENFIELD_PS="$(brel 'infrastructure/greenfield')"

echo "       app/backend diff since HEAD ($BACKEND_PS):"
git -C "$REPO_ROOT" diff --name-only HEAD -- "$BACKEND_PS"     | sed 's/^/         /'
echo "       app/opportunity_center diff since HEAD:"
git -C "$REPO_ROOT" diff --name-only HEAD -- "$OC_PS"          | sed 's/^/         /'
echo "       infrastructure/realignment diff since HEAD:"
git -C "$REPO_ROOT" diff --name-only HEAD -- "$REALIGN_PS"     | sed 's/^/         /'
echo "       infrastructure/shared-infrastructure diff since HEAD:"
git -C "$REPO_ROOT" diff --name-only HEAD -- "$SHARED_PS"      | sed 's/^/         /'
echo "       infrastructure/greenfield diff since HEAD:"
git -C "$REPO_ROOT" diff --name-only HEAD -- "$GREENFIELD_PS"  | sed 's/^/         /'
echo "       (all five should be empty; RC2.2 only adds two files under app/frontend/ + metadata)"

# app/frontend must NOT show package.json in the diff — that would be a source change
FE_DIFF="$(git -C "$REPO_ROOT" diff --name-only HEAD -- "$(brel 'app/frontend')")"
echo "$FE_DIFF" | grep -vE '(^|/)app/frontend/(yarn\.lock|\.npmrc)$' | grep -qE 'app/frontend/' \
  && die "unexpected app/frontend file(s) in diff:\n$FE_DIFF" || true
echo "       app/frontend diff limited to yarn.lock + .npmrc: OK"

# ------------------------------------------------------------------- stage
echo ""
echo "[4/5] Staging"
cd "$REPO_ROOT"
git add \
  "$(brel 'app/frontend/yarn.lock')" \
  "$(brel 'app/frontend/.npmrc')" \
  "$(brel 'VERSION')" \
  "$(brel 'DEPLOYMENT_MANIFEST.md')" \
  "$(brel 'RELEASE_NOTES_v0.1.0-rc2.2.md')"
git status --short

# ------------------------------------------------------------------- commit
echo ""
echo "[5/5] Committing"
COMMIT_MSG="fix(deps,rc2.2): commit frontend yarn.lock + .npmrc for reproducible builds

Resolves the ERESOLVE peer-dependency error in the frontend Docker build.
NO application code, API, business logic, or dependency version changes.

Base VERSION before patch    : $CURR_VER -> arbicore-x-vps-bundle-0.1.0-rc2.2
New application-source SHA   : $NEW_APP_SHA ($NEW_APP_SHA_SHORT)
Layout detected at apply time: $BUNDLE_LAYOUT

Problem: on a truly clean checkout, the RC2.1 frontend Dockerfile fell
         through to \`npm ci\` / \`npm install\` because no lockfile was
         committed. npm >= 7 refuses to install a tree where
         react-day-picker@8.10.1 (peer-requires date-fns ^2 || ^3) is
         combined with date-fns@4.1.0, producing ERESOLVE. Yarn 1 (the
         project's declared packageManager) tolerates the peer mismatch
         and installs, but without a committed yarn.lock, yarn's tolerant
         path could not be reached deterministically.

Fix    : commit the canonical yarn.lock (yarn 1.22.22-generated, 12739
         lines, 74 direct dependencies transitively frozen) so the
         Dockerfile's preferred yarn --frozen-lockfile path activates
         automatically. Also commit app/frontend/.npmrc with
         'legacy-peer-deps=true' so any operator/CI runner reaching for
         npm gets the same tolerant peer resolution yarn already has.

Files touched:
  * app/frontend/yarn.lock                                     (new)
  * app/frontend/.npmrc                                        (new)
  * VERSION                                                    (-> 0.1.0-rc2.2)
  * DEPLOYMENT_MANIFEST.md                                     (sec 1 + 2 + 9 + 10)
  * RELEASE_NOTES_v0.1.0-rc2.2.md                              (new)

Not modified:
  * app/frontend/package.json                                  (dep versions frozen)
  * app/frontend/{public,src,craco.config.js,...}              (source untouched)
  * app/backend/, app/opportunity_center/                      (byte-identical)
  * infrastructure/realignment/, shared-infrastructure/        (byte-identical)
  * infrastructure/greenfield/*                                (RC2.1 packaging unchanged)
  * .dockerignore                                              (RC2.1 unchanged)
  * env templates, scripts, nginx, ssl, backups, monitoring    (all unchanged)

Validation: run 'cd infrastructure/greenfield && docker compose build'
on a fresh clone; frontend build now takes the yarn-lockfile path
(yarn install --frozen-lockfile) instead of the npm fallthrough.

Tarball + SHASUMS regenerated via build_and_tag.sh (separate commit).
"
git commit -m "$COMMIT_MSG"
git log -1 --stat

echo ""
echo "===================================================================="
echo "  RC2.2 DEPENDENCY-RESOLUTION PATCH COMMIT COMPLETE"
echo "===================================================================="
echo ""
echo "Next steps:"
echo "  1. Verify on a fresh clone that docker compose build succeeds:"
echo "       git clone . /tmp/rc2.2-verify"
echo "       cd /tmp/rc2.2-verify && git checkout \$(git rev-parse HEAD)"
echo "       cd \$(git rev-parse --show-toplevel)/$(brel 'infrastructure/greenfield')"
echo "       docker compose build"
echo ""
echo "  2. Regenerate tarball + SHASUMS + verification:"
echo "       bash $PATCH_DIR/build_and_tag.sh"
echo ""
echo "  3. Commit SHASUMS separately (build_and_tag.sh prints the command)"
echo ""
echo "  4. Only after Phase 6 validation, tag v0.1.0-rc2.2 and push"
echo ""
