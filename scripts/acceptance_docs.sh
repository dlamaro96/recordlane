#!/usr/bin/env bash
# SPDX-License-Identifier: Apache-2.0
set -euo pipefail

project_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
docs_source="${RECORDLANE_DOCS_SOURCE:-$project_root/../recordlane-docs}"
ecosystem_source="${RECORDLANE_ECOSYSTEM_SOURCE:-$project_root/../recordlane-ecosystem}"

for required in "$docs_source/package.json" "$ecosystem_source/pyproject.toml"; do
  if [ ! -f "$required" ]; then
    printf 'required acceptance source is missing: %s\n' "$required" >&2
    exit 2
  fi
done

acceptance_root="$(mktemp -d -t recordlane-contributor-XXXXXX)"
cleanup() {
  case "$acceptance_root" in
    /tmp/recordlane-contributor-*|/private/tmp/recordlane-contributor-*|/var/folders/*/recordlane-contributor-*)
      rm -rf "$acceptance_root"
      ;;
    *)
      printf 'refusing to remove unexpected temporary path: %s\n' "$acceptance_root" >&2
      ;;
  esac
}
trap cleanup EXIT

copy_repository() {
  local source="$1"
  local target="$2"
  mkdir -p "$target"
  rsync -a \
    --exclude='.git' --exclude='.venv' --exclude='node_modules' \
    --exclude='.pytest_cache' --exclude='dist' --exclude='test-results' \
    --exclude='playwright-report' --exclude='__pycache__' \
    "$source/" "$target/"
}

platform="$acceptance_root/recordlane"
docs="$acceptance_root/recordlane-docs"
ecosystem="$acceptance_root/recordlane-ecosystem"
copy_repository "$project_root" "$platform"
copy_repository "$docs_source" "$docs"
copy_repository "$ecosystem_source" "$ecosystem"

# The core clone must be independently usable: no sibling repository or
# maintainer validation environment is present beside it.
test ! -e "$acceptance_root/recordlane-python"
test ! -e "$acceptance_root/recordlane-typescript"
! rg -n '/tmp/recordlane-.*validation|/Users/daniamaro96' \
  "$platform/recordlane" "$platform/scripts"/*.py \
  "$platform/tests/acceptance" "$platform/README.md"

python3 -m venv "$platform/backend/.venv"
"$platform/backend/.venv/bin/pip" install --disable-pip-version-check -e "$platform/backend[test]"
"$platform/backend/.venv/bin/python" "$platform/scripts/validate_requirements.py"
for domain_pack in "$platform"/domains/*/*.yaml; do
  "$platform/backend/.venv/bin/python" "$platform/scripts/validate_config.py" "$domain_pack"
done
RECORDLANE_DEMO_MODE=true RECORDLANE_DATABASE_URL="sqlite:///$acceptance_root/contributor.db" \
  "$platform/backend/.venv/bin/pytest" \
  "$platform/tests/unit" "$platform/tests/property"

npm --prefix "$platform/apps/web" ci --no-audit --no-fund
npm --prefix "$platform/apps/web" test
npm --prefix "$platform/apps/web" run build

# The documentation generator has no runtime packages or network fetches.
# npm's offline flag makes an accidental future dependency immediately visible.
(cd "$docs" && npm_config_offline=true npm test && npm_config_offline=true npm run build)
test -f "$docs/dist/index.html"
test -f "$docs/dist/api/openapi.json"

python3 -m venv "$ecosystem/.venv"
"$ecosystem/.venv/bin/pip" install --disable-pip-version-check -e "$ecosystem[test]"
"$ecosystem/.venv/bin/pytest" "$ecosystem/tests"

printf 'clean core clone, offline docs, domain examples, frontend build, and connector contributor flow passed\n'
