#!/usr/bin/env bash
# SPDX-License-Identifier: Apache-2.0
set -euo pipefail
owner="${PROJECT_OWNER:-dlamaro96}"
workspace="${1:-recordlane-workspace}"
mkdir -p "$workspace"
for repository in recordlane recordlane-python recordlane-typescript recordlane-ecosystem recordlane-docs; do
  target="$workspace/$repository"
  if [ -d "$target/.git" ]; then
    git -C "$target" fetch --prune origin
    printf 'updated refs: %s\n' "$target"
  elif [ -e "$target" ]; then
    printf 'refusing to overwrite non-repository path: %s\n' "$target" >&2; exit 2
  else
    git clone "https://github.com/$owner/$repository.git" "$target"
  fi
done
printf 'Workspace ready at %s. Each repository remains independently buildable.\n' "$workspace"
