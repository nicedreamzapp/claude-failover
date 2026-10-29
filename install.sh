#!/usr/bin/env bash
# claude-failover installer (macOS).
#
#   curl -fsSL https://raw.githubusercontent.com/nicedreamzapp/claude-failover/main/install.sh | bash
#   bash ~/.local/share/claude-failover/install.sh        (from a checkout)
#
# Puts agent-llm and llm-failover on your PATH (symlinks into the checkout).
# If claude-code-local is installed (or its server answers on CCL_PORT), failover
# uses that server and nothing else is set up. Otherwise it creates an mlx-lm
# venv plus an on-demand LaunchAgent for mlx_lm.server. No model is downloaded
# here; mlx-lm fetches it the first time `llm-failover local` starts the server.
#
# Environment (all optional):
#   FAILOVER_REPO      git URL or local path to clone (default GitHub)
#   FAILOVER_DIR       where to clone (default ~/.local/share/claude-failover)
#   KIT_BIN_DIR        where the commands go (default ~/.local/bin)
#   FAILOVER_LABEL     LaunchAgent label (default com.local.mlxserver)
#   FAILOVER_MODEL     model for mlx_lm.server (default mlx-community/Qwen2.5-7B-Instruct-4bit)
#   FAILOVER_WITH_MLX  1 = set up the mlx venv + LaunchAgent even with claude-code-local
#   FAILOVER_SKIP_PIP  1 = create the venv but do not pip install mlx-lm
#   FAILOVER_CONFIG    config file llm-failover reads (default ~/.config/claude-failover/config)
#   LLM_PORT           mlx_lm.server port (default 9420)
#   CCL_PORT           claude-code-local port (default 4000)

set -euo pipefail

main() {
  local repo="${FAILOVER_REPO:-https://github.com/nicedreamzapp/claude-failover}"
  local dir="${FAILOVER_DIR:-$HOME/.local/share/claude-failover}"
  local bindir="${KIT_BIN_DIR:-$HOME/.local/bin}"
  local label="${FAILOVER_LABEL:-com.local.mlxserver}"
  local model="${FAILOVER_MODEL:-mlx-community/Qwen2.5-7B-Instruct-4bit}"
  local config="${FAILOVER_CONFIG:-$HOME/.config/claude-failover/config}"
  local llm_port="${LLM_PORT:-9420}"
  local ccl_port="${CCL_PORT:-4000}"
  local marker="installed by claude-failover install.sh"

  say() { printf 'claude-failover: %s\n' "$*"; }
  die() { printf 'claude-failover: ERROR: %s\n' "$*" >&2; exit 1; }

  is_checkout() {
    [ -f "$1/bin/llm-failover" ] && [ -f "$1/bin/agent-llm" ] &&
      git -C "$1" rev-parse --is-inside-work-tree >/dev/null 2>&1
  }

  [ "$(uname -s)" = "Darwin" ] || say "warning: llm-failover needs macOS (launchctl); agent-llm works anywhere"
  command -v git >/dev/null || die "git is required"
  command -v python3 >/dev/null || die "python3 is required"

  # 1. Checkout: use the one this script lives in, else clone / update FAILOVER_DIR.
  local self="${BASH_SOURCE[0]:-}" src=""
  if [ -n "$self" ] && [ -f "$self" ]; then
    self="$(cd "$(dirname "$self")" && pwd -P)"
    is_checkout "$self" && src="$self"
  fi
  if [ -z "$src" ]; then
    if is_checkout "$dir"; then
      if [ -n "$(git -C "$dir" status --porcelain --untracked-files=no 2>/dev/null)" ]; then
        say "local edits in $dir, skipping update"
      else
        git -C "$dir" pull --ff-only -q || say "warning: could not update $dir, using it as is"
      fi
    elif [ -e "$dir" ] && [ -n "$(ls -A "$dir" 2>/dev/null)" ]; then
      die "$dir exists and is not a claude-failover checkout; set FAILOVER_DIR"
    else
      mkdir -p "$(dirname "$dir")"
      git clone -q "$repo" "$dir" || die "git clone $repo failed"
    fi
    src="$(cd "$dir" && pwd -P)"
  fi
  chmod +x "$src/bin/agent-llm" "$src/bin/llm-failover"

  # 2. Commands on PATH.
  mkdir -p "$bindir"
  local b link
  for b in agent-llm llm-failover; do
    link="$bindir/$b"
    if [ -e "$link" ] && [ ! -L "$link" ]; then
      mv "$link" "$link.pre-kit"
      say "moved existing $link to $link.pre-kit"
    fi
    ln -sfn "$src/bin/$b" "$link"
  done

  # 3. Local server: claude-code-local if present, else mlx-lm venv + LaunchAgent.
  local ccl=0
  if [ -f "$HOME/.local/mlx-native-server/server.py" ]; then
    ccl=1
  elif curl -fsS --max-time 2 "http://127.0.0.1:${ccl_port}/health" 2>/dev/null | grep -q ok; then
    ccl=1
  fi

  local plist="$HOME/Library/LaunchAgents/${label}.plist"
  if [ "$ccl" = 1 ] && [ "${FAILOVER_WITH_MLX:-0}" != 1 ]; then
    say "claude-code-local found: failover will use its server (port ${ccl_port}); skipping the mlx venv"
  else
    local venv="$src/.venv"
    if [ ! -x "$venv/bin/python" ]; then
      python3 -m venv "$venv" || die "could not create $venv"
    fi
    if [ "${FAILOVER_SKIP_PIP:-0}" = 1 ]; then
      say "FAILOVER_SKIP_PIP=1: skipping pip install mlx-lm"
    else
      say "installing mlx-lm into $venv"
      "$venv/bin/python" -m pip install -q --upgrade pip >/dev/null 2>&1 || true
      "$venv/bin/python" -m pip install -q mlx-lm || die "pip install mlx-lm failed"
    fi

    if [ -f "$plist" ] && ! grep -q "$marker" "$plist"; then
      say "keeping your existing $plist (not created by this installer)"
    else
      local logdir="$HOME/Library/Logs/claude-failover" tmp
      mkdir -p "$(dirname "$plist")" "$logdir"
      tmp="$(mktemp "${TMPDIR:-/tmp}/claude-failover-plist.XXXXXX")"
      write_plist "$tmp" "$label" "$venv" "$model" "$llm_port" "$logdir" "$marker"
      if command -v plutil >/dev/null; then
        plutil -lint -s "$tmp" || { rm -f "$tmp"; die "generated plist is invalid"; }
      fi
      if [ -f "$plist" ] && cmp -s "$tmp" "$plist"; then
        rm -f "$tmp"
      else
        # Changed definition: drop the old one so the next `llm-failover local` loads the new one.
        launchctl bootout "gui/$(id -u)/${label}" 2>/dev/null || true
        mv "$tmp" "$plist"
      fi
      say "LaunchAgent $label ready (on demand, port ${llm_port}; not started)"
    fi
  fi

  # 4. Config for llm-failover (label/ports) and for uninstall.sh (checkout path).
  mkdir -p "$(dirname "$config")"
  {
    echo "# $marker; read by llm-failover (environment wins)"
    echo "LLM_LAUNCHAGENT=$label"
    echo "LLM_PORT=$llm_port"
    echo "CCL_PORT=$ccl_port"
    echo "FAILOVER_SRC=$src"
  } > "$config"

  case ":$PATH:" in
    *":$bindir:"*) ;;
    *) say "add $bindir to your PATH to use agent-llm and llm-failover" ;;
  esac
  say "done. Try: llm-failover status"
  say "uninstall: curl -fsSL https://raw.githubusercontent.com/nicedreamzapp/claude-failover/main/uninstall.sh | bash"
}

xml_escape() {
  local s="$1"
  s="${s//&/&amp;}"; s="${s//</&lt;}"; s="${s//>/&gt;}"
  printf '%s' "$s"
}

write_plist() {
  local out="$1" label venv model port logdir marker
  label="$(xml_escape "$2")"; venv="$(xml_escape "$3")"; model="$(xml_escape "$4")"
  port="$(xml_escape "$5")"; logdir="$(xml_escape "$6")"; marker="$7"
  cat > "$out" <<EOF
<?xml version="1.0" encoding="UTF-8"?>
<!-- $marker -->
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>$label</string>
    <key>ProgramArguments</key>
    <array>
        <string>$venv/bin/python</string>
        <string>-m</string>
        <string>mlx_lm.server</string>
        <string>--model</string>
        <string>$model</string>
        <string>--host</string>
        <string>127.0.0.1</string>
        <string>--port</string>
        <string>$port</string>
    </array>
    <key>WorkingDirectory</key>
    <string>$venv</string>
    <key>RunAtLoad</key>
    <false/>
    <key>KeepAlive</key>
    <false/>
    <key>ThrottleInterval</key>
    <integer>30</integer>
    <key>StandardOutPath</key>
    <string>$logdir/mlxserver.log</string>
    <key>StandardErrorPath</key>
    <string>$logdir/mlxserver.err</string>
    <key>EnvironmentVariables</key>
    <dict>
        <key>PATH</key>
        <string>/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin</string>
        <key>LLM_PORT</key>
        <string>$port</string>
    </dict>
</dict>
</plist>
EOF
}

main "$@"
