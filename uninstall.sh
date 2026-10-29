#!/usr/bin/env bash
# claude-failover uninstaller (macOS).
#
#   curl -fsSL https://raw.githubusercontent.com/nicedreamzapp/claude-failover/main/uninstall.sh | bash
#   curl -fsSL https://raw.githubusercontent.com/nicedreamzapp/claude-failover/main/uninstall.sh | bash -s -- --purge
#   bash ~/.local/share/claude-failover/uninstall.sh [--purge]
#
# Removes what install.sh created: the mlx LaunchAgent (only if the installer
# wrote it), the agent-llm / llm-failover symlinks (only if they point into the
# checkout) and the venv. Keeps the backend flag and config unless --purge;
# --purge also deletes the flag, config, logs and the clone in FAILOVER_DIR.
# Same environment variables as install.sh.

set -euo pipefail

main() {
  local purge=0 arg
  for arg in "$@"; do
    case "$arg" in
      --purge) purge=1 ;;
      -h|--help) sed -n '2,12p' "${BASH_SOURCE[0]:-/dev/null}" 2>/dev/null; return 0 ;;
      *) echo "usage: uninstall.sh [--purge]" >&2; return 1 ;;
    esac
  done

  local dir="${FAILOVER_DIR:-$HOME/.local/share/claude-failover}"
  local bindir="${KIT_BIN_DIR:-$HOME/.local/bin}"
  local config="${FAILOVER_CONFIG:-$HOME/.config/claude-failover/config}"
  local flag="${LLM_BACKEND_FLAG:-$HOME/.local/state/llm-backend}"
  local marker="installed by claude-failover install.sh"
  say() { printf 'claude-failover: %s\n' "$*"; }

  # What install.sh recorded.
  local cfg_label="" cfg_src="" key val
  if [ -f "$config" ]; then
    while IFS='=' read -r key val || [ -n "$key" ]; do
      case "$key" in
        LLM_LAUNCHAGENT) cfg_label="$val" ;;
        FAILOVER_SRC) cfg_src="$val" ;;
      esac
    done < "$config"
  fi
  local label="${FAILOVER_LABEL:-${cfg_label:-com.local.mlxserver}}"

  # Checkouts the install may have used: this script's own, the recorded one, FAILOVER_DIR.
  local srcs=() self="${BASH_SOURCE[0]:-}" d
  if [ -n "$self" ] && [ -f "$self" ]; then
    self="$(cd "$(dirname "$self")" && pwd -P)"
    [ -f "$self/bin/llm-failover" ] && srcs+=("$self")
  fi
  [ -n "$cfg_src" ] && srcs+=("$cfg_src")
  [ -d "$dir" ] && srcs+=("$(cd "$dir" && pwd -P)")
  srcs+=("$dir")

  # 1. LaunchAgent, only if our installer wrote it.
  local plist="$HOME/Library/LaunchAgents/${label}.plist"
  if [ -f "$plist" ]; then
    if grep -q "$marker" "$plist"; then
      launchctl bootout "gui/$(id -u)/${label}" 2>/dev/null || true
      rm -f "$plist"
      say "removed LaunchAgent $label"
    else
      say "leaving $plist (not created by install.sh)"
    fi
  fi
  rm -f "$(dirname "$flag")/llm-failover.loaded"

  # 2. Symlinks that point into one of our checkouts.
  local b link target
  for b in agent-llm llm-failover; do
    link="$bindir/$b"
    [ -L "$link" ] || continue
    target="$(readlink "$link")"
    for d in ${srcs[@]+"${srcs[@]}"}; do
      if [ "$target" = "$d/bin/$b" ]; then
        rm -f "$link"
        say "removed $link"
        break
      fi
    done
  done

  # 3. Venvs.
  for d in ${srcs[@]+"${srcs[@]}"}; do
    if [ -f "$d/.venv/pyvenv.cfg" ]; then
      rm -rf "$d/.venv"
      say "removed $d/.venv"
    fi
  done

  # 4. --purge: flag, config, logs, clone.
  if [ "$purge" = 1 ]; then
    rm -f "$flag" "$config"
    rmdir "$(dirname "$config")" 2>/dev/null || true
    rm -rf "$HOME/Library/Logs/claude-failover"
    if [ -f "$dir/bin/llm-failover" ]; then
      rm -rf "$dir"
      say "removed $dir"
    fi
    if [ -n "$self" ] && [ -f "$self/bin/llm-failover" ]; then
      say "left the checkout you ran this from: $self"
    fi
  fi
  say "uninstalled"
}

main "$@"
