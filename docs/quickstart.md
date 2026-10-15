---
title: Quickstart - switch claude -p calls to a local model and back
description: Flip your claude -p scripts to a local mlx-lm model with llm-failover local, send a test prompt through agent-llm, then switch back to Claude with llm-failover claude.
---

# Quickstart

This assumes you finished [Install](install.md).

## 1. Point your scripts at agent-llm

Wherever your code runs the Claude CLI headlessly, call `agent-llm` instead:

```python
# Before
result = subprocess.run(["/opt/homebrew/bin/claude", "-p", prompt], ...)

# After
result = subprocess.run(["/Users/YOU/.local/bin/agent-llm", "-p", prompt], ...)
```

While the backend is `claude`, `agent-llm` replaces itself with the real `claude` process (`os.execv`) using your exact arguments, so behavior is the same as before.

!!! tip "Put the prompt right after `-p`"
    In local mode `agent-llm` takes the argument immediately after `-p` as the prompt. `agent-llm -p "prompt"` and `echo "prompt" | agent-llm -p` both work. `agent-llm -p --output-format json "prompt"` would send the text `--output-format` as the prompt.

## 2. Flip to local

```bash
llm-failover local
```

This writes `local` to the flag file, loads the LaunchAgent, and waits up to 180 seconds for the server to answer on `http://127.0.0.1:9420/v1/models`:

```text
agent backend now: local (port 9420)
loading local server (cold start ~30-90s on first call)..... ready (<seconds>s)
```

The very first run also downloads the model and can exceed 180 seconds. If it prints `TIMEOUT`, wait for the download to finish and run `llm-failover local` again.

## 3. Send a prompt

```bash
echo "say hello in one word" | agent-llm -p
```

The reply comes from the local model as plain text.

## 4. Flip back to Claude

```bash
llm-failover claude
```

```text
agent backend now: claude
local server unloaded (memory freed)
```

The next `agent-llm` call goes to Claude again. The local model's memory is released.

## Get a notification on every flip

```bash
export LLM_NOTIFY_CMD=/usr/local/bin/my-notify-script
llm-failover local
```

Your command is called with one argument: `agent backend flipped to LOCAL. claude usage paused. flip back: llm-failover claude`. Add `-q` after the mode (`llm-failover local -q`) to skip it.

## Show the backend on a dashboard

The backend is a one-word text file, so anything can read it. Example Flask endpoint from the README:

```python
@app.route("/api/llm-backend")
def llm_backend():
    flag = Path.home() / ".local/state/llm-backend"
    return {"backend": flag.read_text().strip() if flag.exists() else "claude"}
```
