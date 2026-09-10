#!/usr/bin/env bash
# SPDX-License-Identifier: Apache-2.0
set -euo pipefail
release_tag="${1:?usage: scripts/build_release.sh v0.1.0-alpha.1}"
case "$release_tag" in v[0-9]*.[0-9]*.[0-9]*-*) ;; *) printf 'Expected a semantic prerelease tag, got %s\n' "$release_tag" >&2; exit 2;; esac
release_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
mkdir -p "$release_root/dist"
find "$release_root/dist" -mindepth 1 -maxdepth 1 -type f -delete
git -C "$release_root" archive --format=tar.gz --prefix="recordlane-${release_tag#v}/" -o "$release_root/dist/recordlane-${release_tag#v}.tar.gz" HEAD
helm package "$release_root/deploy/helm/recordlane" --version "${release_tag#v}" --app-version "${release_tag#v}" --destination "$release_root/dist"
syft "dir:$release_root" -o spdx-json="$release_root/dist/recordlane-${release_tag#v}.sbom.spdx.json"
(cd "$release_root" && git rev-parse HEAD) > "$release_root/dist/SOURCE_COMMIT"
(cd "$release_root/dist" && find . -maxdepth 1 -type f ! -name SHA256SUMS -print | LC_ALL=C sort | xargs shasum -a 256) > "$release_root/dist/SHA256SUMS"
