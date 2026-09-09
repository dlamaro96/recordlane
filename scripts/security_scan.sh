#!/usr/bin/env bash
# SPDX-License-Identifier: Apache-2.0
set -euo pipefail
scan_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
gitleaks detect --source "$scan_root" --no-banner --redact
npm --prefix "$scan_root/apps/web" audit --audit-level=high
trivy fs --scanners vuln,secret,misconfig --severity HIGH,CRITICAL --exit-code 1 --skip-dirs .git --skip-dirs node_modules --skip-dirs .venv "$scan_root"
