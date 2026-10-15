---
title: Install claude-failover on macOS (agent-llm, llm-failover, mlx-lm LaunchAgent)
description: Step-by-step install of claude-failover on an Apple Silicon Mac. Put agent-llm and llm-failover on your PATH, create an mlx-lm virtualenv, and set up the on-demand LaunchAgent.
---

# Install

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

## Uninstall

```bash
llm-failover claude                       # unload the server
rm ~/.local/bin/agent-llm ~/.local/bin/llm-failover
rm ~/Library/LaunchAgents/com.local.mlxserver.plist
rm -rf ~/.local/share/mlx-server          # the venv
rm ~/.local/state/llm-backend             # the flag file
```

Downloaded model weights live in the Hugging Face cache, not in this project's folders. <!-- TODO-VERIFY: default cache location (~/.cache/huggingface) is mlx-lm / huggingface_hub behavior, not set by this repo. -->
