#!/usr/bin/env bash
set -euo pipefail

platform="${1:-}"
repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
codex_marketplace_root="${repo_root}/.agents/plugins"
claude_marketplace="${repo_root}/.claude-plugin"
plugin_name="autoscirub"
marketplace_name="autoscirub-local"

usage() {
  printf 'Usage: %s {codex|claude|openclaw}\n' "$(basename "$0")" >&2
}

check_cmd() {
  command -v "$1" >/dev/null 2>&1 || {
    printf 'Missing command: %s\n' "$1" >&2
    exit 1
  }
}

install_codex() {
  check_cmd codex
  codex plugin marketplace add "$codex_marketplace_root"
  codex plugin add "${plugin_name}@${marketplace_name}"
}

install_claude() {
  check_cmd claude
  claude plugin marketplace add "$claude_marketplace"
  claude plugin install "${plugin_name}@${marketplace_name}"
}

install_openclaw() {
  if command -v openclaw >/dev/null 2>&1; then
    openclaw plugins install "$repo_root" --marketplace "$claude_marketplace" || \
      openclaw skills install "$repo_root/plugins/autoscirub/skills/autoscirub"
    return
  fi
  printf 'Missing command: openclaw\n' >&2
  exit 1
}

case "$platform" in
  codex)
    install_codex
    ;;
  claude)
    install_claude
    ;;
  openclaw)
    install_openclaw
    ;;
  *)
    usage
    exit 1
    ;;
esac
