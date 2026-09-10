#!/usr/bin/env bash
# SPDX-License-Identifier: Apache-2.0
set -euo pipefail

owner="${PROJECT_OWNER:-dlamaro96}"
root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
parent="$(dirname "$root")"
repos=(recordlane recordlane-python recordlane-typescript recordlane-ecosystem recordlane-docs)

for repo in "${repos[@]}"; do
  remote="$(gh api "repos/$owner/$repo")"
  test "$(jq -r .private <<<"$remote")" = false
  test "$(jq -r .default_branch <<<"$remote")" = main
  test "$(gh api "repos/$owner/$repo/private-vulnerability-reporting" --jq .enabled)" = true
  protection="$(gh api "repos/$owner/$repo/branches/main/protection")"
  test "$(jq -r .allow_force_pushes.enabled <<<"$protection")" = false
  test "$(jq -r .allow_deletions.enabled <<<"$protection")" = false
  local_path="$parent/$repo"
  if [ "$repo" = recordlane ]; then local_path="$root"; fi
  local_sha="$(git -C "$local_path" rev-parse HEAD)"
  remote_sha="$(gh api "repos/$owner/$repo/commits/main" --jq .sha)"
  test "$local_sha" = "$remote_sha"
  printf 'PASS %-22s %s\n' "$repo" "$remote_sha"
done

docs_url="https://$owner.github.io/recordlane-docs/"
curl --fail --silent --show-error --location "$docs_url" >/dev/null
printf 'PASS documentation          %s\n' "$docs_url"

if [ -n "${RECORDLANE_RELEASE_TAG:-}" ]; then
  "$root/backend/.venv/bin/pytest" -q \
    "$root/tests/acceptance/test_contract_scenarios.py::test_ax_published_artifacts_and_attestations"
  printf 'PASS release consumer       %s\n' "$RECORDLANE_RELEASE_TAG"
else
  printf 'NOTE set RECORDLANE_RELEASE_TAG to verify release assets, images, signatures, and attestations.\n'
fi
