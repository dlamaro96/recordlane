#!/usr/bin/env bash
# SPDX-License-Identifier: Apache-2.0
set -euo pipefail
scan_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
evidence="$scan_root/docs/evidence/2026-09-09/security"
mkdir -p "$evidence"
gitleaks git "$scan_root" --no-banner --redact --report-format json --report-path "$evidence/gitleaks-history.json"
gitleaks dir "$scan_root" --no-banner --redact --report-format json --report-path "$evidence/gitleaks.json"
npm --prefix "$scan_root/apps/web" audit --audit-level=high
trivy_flags=(--scanners vuln,secret,misconfig --severity HIGH,CRITICAL \
  --skip-dirs .git --skip-dirs node_modules --skip-dirs .venv --skip-dirs dist \
  --helm-values "$scan_root/tests/kubernetes/kind-values.yaml")
trivy fs "${trivy_flags[@]}" --exit-code 1 "$scan_root"
trivy fs "${trivy_flags[@]}" --format json --output "$evidence/trivy-filesystem.json" "$scan_root"

api_image="${RECORDLANE_SCAN_API_IMAGE:-recordlane-demo-api:latest}"
web_image="${RECORDLANE_SCAN_WEB_IMAGE:-recordlane-demo-web:latest}"
for image in "$api_image" "$web_image"; do
  docker image inspect "$image" >/dev/null
done
trivy image --scanners vuln,secret --severity HIGH,CRITICAL --exit-code 1 "$api_image"
trivy image --scanners vuln,secret --severity HIGH,CRITICAL --format json --output "$evidence/trivy-api.json" "$api_image"
trivy image --scanners vuln,secret --severity HIGH,CRITICAL --exit-code 1 "$web_image"
trivy image --scanners vuln,secret --severity HIGH,CRITICAL --format json --output "$evidence/trivy-web.json" "$web_image"
