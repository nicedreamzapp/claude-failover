---
title: Install claude-failover on macOS (agent-llm, llm-failover, mlx-lm LaunchAgent)
description: Step-by-step install of claude-failover on an Apple Silicon Mac. Put agent-llm and llm-failover on your PATH, create an mlx-lm virtualenv, and set up the on-demand LaunchAgent.
---

# Install

## One-line install

```bash
curl -fsSL https://raw.githubusercontent.com/nicedreamzapp/claude-failover/main/install.sh | bash
```

This clones the repo to `~/.local/share/claude-failover` (`FAILOVER_DIR`), symlinks `agent-llm` and `llm-failover` into `~/.local/bin` (`KIT_BIN_DIR`) and writes `~/.config/claude-failover/config` (label and ports for `llm-failover`). If [claude-code-local](https://github.com/nicedreamzapp/claude-code-local) is installed (`~/.local/mlx-native-server/server.py`, or its `/health` answers on `CCL_PORT`, default 4000), failover uses that server and nothing else is set up. Otherwise it creates a venv with mlx-lm in the clone and an on-demand LaunchAgent `~/Library/LaunchAgents/<FAILOVER_LABEL>.plist` (default label `com.local.mlxserver`, port `LLM_PORT`, default 9420, model `FAILOVER_MODEL`). No model is downloaded at install time.

| Variable | Effect |
|---|---|
| `FAILOVER_REPO` | Git URL or local path to clone. |
| `FAILOVER_DIR` | Clone location (default `~/.local/share/claude-failover`). |
| `KIT_BIN_DIR` | Where the commands are linked (default `~/.local/bin`). |
| `FAILOVER_LABEL` | LaunchAgent label (default `com.local.mlxserver`). |
| `FAILOVER_MODEL` | Model for `mlx_lm.server` (default `mlx-community/Qwen2.5-7B-Instruct-4bit`). |
| `FAILOVER_WITH_MLX=1` | Set up the mlx venv and LaunchAgent even when claude-code-local is present. |
| `FAILOVER_SKIP_PIP=1` | Create the venv but skip `pip install mlx-lm`. |

Uninstall:

```bash
curl -fsSL https://raw.githubusercontent.com/nicedreamzapp/claude-failover/main/uninstall.sh | bash
# also delete the clone, flag file, config and logs:
curl -fsSL https://raw.githubusercontent.com/nicedreamzapp/claude-failover/main/uninstall.sh | bash -s -- --purge
```

It only removes a LaunchAgent the installer wrote and symlinks that point into the clone.

The rest of this page is the manual install.

## Requirements

| Requirement | Why |
|---|---|
| macOS on Apple Silicon | `llm-failover` uses `launchctl` and the local server is mlx-lm, which runs on Apple Silicon. |
| Python 3.9+ | `agent-llm` is a Python 3 script using only the standard library. <!-- TODO-VERIFY: 3.9 minimum is stated in the README; not tested in CI. --> |
| `curl` | `llm-failover` health-checks the local server with `curl`. |
| [Claude Code CLI](https://claude.ai/code) | Used whenever the backend is `claude`. |
| [mlx-lm](https://github.com/ml-explore/mlx-examples/tree/main/llms/mlx_lm) | The local OpenAI-compatible server. |

`agent-llm` by itself has no macOS-specific code, so it runs anywhere Python does. Only `llm-failover` needs macOS.

## 1. Clone the repo

```bash
git clone https://github.com/nicedreamzapp/claude-failover.git
cd claude-failover
```

## 2. Put the scripts on your PATH

```bash
mkdir -p ~/.local/bin
cp bin/agent-llm bin/llm-failover ~/.local/bin/
chmod +x ~/.local/bin/agent-llm ~/.local/bin/llm-failover
```

Make sure `~/.local/bin` is on your `PATH`, or call the scripts by full path.

## 3. Create an mlx-lm virtualenv

```bash
python3 -m venv ~/.local/share/mlx-server/.venv
~/.local/share/mlx-server/.venv/bin/pip install mlx-lm
```

The model weights are not downloaded here. mlx-lm fetches them from Hugging Face the first time the server starts.

## 4. Install the LaunchAgent

```bash
cp LaunchAgents/com.example.mlxserver.plist.example \
   ~/Library/LaunchAgents/com.local.mlxserver.plist
```

Edit the copy:

- Replace `/PATH/TO/VENV` (it appears twice, in `ProgramArguments` and `WorkingDirectory`) with the absolute path of the folder that holds `.venv`, for example `/Users/YOU/.local/share/mlx-server`.
- Optionally change the model after `--model`. If you do, set `LOCAL_LLM_MODEL` to the same id (see [Configuration](configuration.md#choosing-a-model)).

!!! warning "The file name must match the label"
    `llm-failover` looks for the plist at `~/Library/LaunchAgents/<label>.plist`, where the label is `LLM_LAUNCHAGENT` (default `com.local.mlxserver`). The `<key>Label</key>` inside the file should be the same string.

The example plist has `RunAtLoad` and `KeepAlive` set to `false`, so nothing runs until `llm-failover local` loads it.

## 5. Check it

```bash
llm-failover status
```

On a fresh install this prints:

```text
current backend: claude
local server: down (lazy)
```

Continue with the [Quickstart](quickstart.md).

## Uninstall (manual install)

```bash
llm-failover claude                       # unload the server (if llm-failover loaded it)
rm ~/.local/bin/agent-llm ~/.local/bin/llm-failover
rm ~/Library/LaunchAgents/com.local.mlxserver.plist
rm -rf ~/.local/share/mlx-server          # the venv
rm ~/.local/state/llm-backend             # the flag file
```

Downloaded model weights live in the Hugging Face cache, not in this project's folders. <!-- TODO-VERIFY: default cache location (~/.cache/huggingface) is mlx-lm / huggingface_hub behavior, not set by this repo. -->
