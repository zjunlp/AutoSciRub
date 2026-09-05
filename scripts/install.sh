#!/usr/bin/env bash
set -euo pipefail
repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
if command -v python3 >/dev/null 2>&1; then
  exec python3 "$repo_root/scripts/install.py" "$@"
elif command -v python >/dev/null 2>&1; then
  exec python "$repo_root/scripts/install.py" "$@"
else
  printf 'Python 3.10+ is required. Install Python, then rerun this command.\n' >&2
  exit 1
fi
