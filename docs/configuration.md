---
title: Configuration - every claude-failover environment variable, command and flag
description: Reference for claude-failover configuration, read from the source. Environment variables for agent-llm and llm-failover, commands, aliases, exit codes, the flag file and the LaunchAgent plist.
---

# Configuration

Everything on this page is read from [`bin/agent-llm`](https://github.com/nicedreamzapp/claude-failover/blob/main/bin/agent-llm), [`bin/llm-failover`](https://github.com/nicedreamzapp/claude-failover/blob/main/bin/llm-failover) and the [example plist](https://github.com/nicedreamzapp/claude-failover/blob/main/LaunchAgents/com.example.mlxserver.plist.example). All settings are environment variables. `llm-failover` also reads `LLM_LAUNCHAGENT`, `LLM_PORT` and `CCL_PORT` from an optional `KEY=VALUE` file (`FAILOVER_CONFIG`, written by `install.sh`); the environment wins over the file.

## Environment variables

| Variable | Read by | Default | What the code does with it |
|---|---|---|---|
| `LLM_BACKEND_FLAG` | both | `~/.local/state/llm-backend` | Path of the flag file. `llm-failover` creates its parent directory on every run. |
| `CLAUDE_BIN` | `agent-llm` | `shutil.which("claude")`, then `/usr/local/bin/claude` | Path of the real Claude CLI used in `claude` mode. If the path does not exist, `agent-llm` exits 127. |
| `LOCAL_LLM_URL` | `agent-llm` | auto | Full URL the prompt is POSTed to in `local` mode, used as-is. A URL ending in `/v1/messages` gets the Anthropic Messages API, anything else OpenAI chat-completions. When unset (auto): `http://127.0.0.1:<CCL_PORT>/v1/messages` if claude-code-local's `/health` answers, otherwise `http://127.0.0.1:<LLM_PORT>/v1/chat/completions`. |
| `LOCAL_LLM_MODEL` | `agent-llm` | `mlx-community/Qwen2.5-7B-Instruct-4bit` | Sent as `model` in the request body. For Anthropic-style URLs the default is `claude-sonnet-4-6` (claude-code-local accepts any id). |
| `LOCAL_LLM_API_KEY` | `agent-llm` | `sk-local` | Sent as `x-api-key` to Anthropic-style URLs. |
| `CCL_PORT` | both | `4000` | Port of the [claude-code-local](https://github.com/nicedreamzapp/claude-code-local) server. Probed at `/health`; when it answers it is preferred over mlx-lm. |
| `LOCAL_LLM_MAX_TOKENS` | `agent-llm` | `800` | Sent as `max_tokens`. Parsed with `int()` at startup in both modes, so a non-integer value makes `agent-llm` crash even when the backend is `claude`. |
| `LLM_LAUNCHAGENT` | `llm-failover` | `com.local.mlxserver` | LaunchAgent label. Also decides the plist path: `~/Library/LaunchAgents/<label>.plist`. |
| `LLM_PORT` | both | `9420` | Port of the mlx-lm server: health check `http://127.0.0.1:<port>/v1/models` in `llm-failover`, and the fallback URL in `agent-llm` when `LOCAL_LLM_URL` is unset. |
| `FAILOVER_CONFIG` | `llm-failover` | `~/.config/claude-failover/config` | Optional `KEY=VALUE` file for `LLM_LAUNCHAGENT`, `LLM_PORT`, `CCL_PORT`. |
| `LLM_NOTIFY_CMD` | `llm-failover` | unset | Command run after a successful flip, with the message as its single argument. Its output and exit status are ignored. |

!!! note "One port, three settings"
    The mlx-lm port appears in two places: `--port` in the plist and `LLM_PORT` (read by both scripts). They default to `9420`. If you set `LOCAL_LLM_URL` yourself, it must match too.

`LLM_NOTIFY_CMD` is run as a single program path, not through a shell, so it cannot contain its own arguments. Wrap anything more complex in a small script.

## llm-failover commands

```text
llm-failover [local|claude|status] [-q|--quiet]
```

| Command | Effect |
|---|---|
| `status` (or no argument) | Prints `current backend: <flag contents>` (or `claude` if the file is missing) and which server is serving: claude-code-local on `CCL_PORT`, else mlx-lm on `LLM_PORT`, else down. |
| `local` | Writes `local` to the flag. If claude-code-local answers on `CCL_PORT`, stops there. Otherwise loads and kickstarts the LaunchAgent if the mlx-lm server is not already up, and polls once per second for up to 180 seconds. Sends the notification on success. |
| `gemma`, `qwen` | Aliases for `local`. They do not choose a model. |
| `claude` | Writes `claude` to the flag. Unloads the plist only if `llm-failover local` loaded it (a marker file next to the flag) and `launchctl list` still contains the label. Sends the notification. |
| anything else | Prints usage and exits 1. |

`-q` / `--quiet` can appear anywhere in the arguments and suppresses the notification. The mode is always taken from the **first** argument, so `llm-failover -q local` is treated as an unknown command. Put the mode first: `llm-failover local -q`.

### Exit codes

| Code | Meaning |
|---|---|
| `0` | Success. |
| `1` | Unknown command (usage printed). |
| `2` | `local`: plist not found at `~/Library/LaunchAgents/<label>.plist`. |
| `3` | `local`: server did not answer within 180 seconds. |

In both the `2` and `3` cases the flag has already been set to `local`. See [Troubleshooting](troubleshooting.md#the-flag-says-local-but-the-server-never-came-up).

## agent-llm

```text
agent-llm -p "prompt"
echo "prompt" | agent-llm -p
```

### Backend selection

`agent-llm` reads the flag file, strips whitespace and lowercases it.

- Missing file or `claude` (any case): Claude mode.
- **Any other value**, including `local`, `gemma`, a typo, or an empty file: local mode.

### Claude mode

Runs `os.execv(CLAUDE_BIN, [CLAUDE_BIN] + all arguments)`. The process becomes the real `claude` CLI, so stdin, stdout, exit code and every flag behave exactly as if you called `claude` yourself.

### Local mode

| Behavior | Value in code |
|---|---|
| Prompt source | The argument right after `-p`. If `-p` appears more than once, the last one wins. If `-p` is the final argument, or there is no `-p`, or the prompt is empty, stdin is read. |
| Other arguments | Ignored. |
| Request | One user message: `{"model", "messages": [{"role": "user", "content": prompt}], "max_tokens", "temperature": 0.3}` |
| Temperature | `0.3`, fixed. |
| Timeout | 120 seconds. |
| Streaming | No. |
| Output | `choices[0].message.content`, or `message.reasoning` if content is empty, stripped and printed with a trailing newline. |
| Exit status | `0` on success, `1` on any error (message on stderr starting `agent-llm local error:`). |

The `reasoning` fallback exists because, per the code comment, some models (Gemma 3) emit a reasoning channel. <!-- TODO-VERIFY: which servers/models actually return a `reasoning` field. -->

## The flag file

A plain text file containing `claude` or `local`. You can write it yourself:

```bash
echo local > ~/.local/state/llm-backend
```

Writing it by hand changes where `agent-llm` sends calls but does not start or stop the server. Use `llm-failover` if you want both.

## The LaunchAgent plist

Settings in `LaunchAgents/com.example.mlxserver.plist.example`:

| Key | Example value | Notes |
|---|---|---|
| `Label` | `com.local.mlxserver` | Must match `LLM_LAUNCHAGENT` and the file name. |
| `ProgramArguments` | `/PATH/TO/VENV/.venv/bin/python -m mlx_lm.server --model mlx-community/Qwen2.5-7B-Instruct-4bit --host 127.0.0.1 --port 9420` | Replace the placeholder path. |
| `WorkingDirectory` | `/PATH/TO/VENV` | Replace the placeholder path. |
| `RunAtLoad` | `false` | Set to `true` to start the server at login (warm failover, uses RAM all the time). `llm-failover claude` still unloads it. |
| `KeepAlive` | `false` | launchd does not restart the server if it exits. |
| `ThrottleInterval` | `30` | launchd minimum seconds between starts. |
| `StandardOutPath` | `/tmp/mlxserver.log` | Server stdout. |
| `StandardErrorPath` | `/tmp/mlxserver.err` | Server stderr. Check here first when the server will not start. |
| `EnvironmentVariables.PATH` | `/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin` | PATH seen by the server process. |

## Choosing a model

Change `--model` in the plist and set `LOCAL_LLM_MODEL` to the same id. The README lists these options; the sizes are the README's figures and have not been measured in this repo.

| Model | Disk | RAM loaded | README notes |
|---|---|---|---|
| `mlx-community/Qwen2.5-7B-Instruct-4bit` | ~4 GB | ~5 GB | Default. Triage, classification. |
| `mlx-community/gemma-3-27b-it-4bit` | ~16 GB | ~22 GB | Drafts, longer reasoning. 32 GB+ Mac. |
| `mlx-community/Qwen3-Coder-30B-A3B-Instruct` | ~16 GB | ~22 GB | Code and structured output. MoE, 3B active. |
| `mlx-community/Llama-3.3-70B-Instruct-4bit` | ~40 GB | ~42 GB | 64 GB+ Mac. |

<!-- TODO-VERIFY: disk/RAM figures above are copied from README.md and not backed by a measurement in the repo. -->
