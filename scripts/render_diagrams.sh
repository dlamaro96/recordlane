#!/usr/bin/env bash
# SPDX-License-Identifier: Apache-2.0
set -euo pipefail
task_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
command -v dot >/dev/null || { printf 'Graphviz dot is required\n' >&2; exit 2; }
for source in "$task_root"/assets/diagrams/src/*.dot; do
  name="$(basename "$source" .dot)"
  common=(-Gbgcolor="#f4f6f8" -Gfontcolor="#17202b" -Gfontname="Arial" \
    -Nfillcolor="#ffffff" -Ncolor="#c8d1dc" -Nfontcolor="#17202b" -Nfontname="Arial" \
    -Ecolor="#2f5bff" -Efontcolor="#596574" -Efontname="Arial")
  dot -Tsvg "${common[@]}" "$source" -o "$task_root/assets/diagrams/$name.svg"
  dot -Tpng -Gdpi=160 "${common[@]}" "$source" -o "$task_root/assets/diagrams/$name.png"
done
printf 'Rendered %s editable diagrams to SVG and PNG.\n' "$(find "$task_root/assets/diagrams/src" -name '*.dot' | wc -l | tr -d ' ')"
