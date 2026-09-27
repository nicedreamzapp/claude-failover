# claude-failover

**A backup brain for Claude Code. When your Claude Max plan hits its limit, your tokens are exhausted, or Claude is down — flip one command and your `claude -p` agents keep running on a local LLM. Default to Claude. Local only when you need it.**

**What it is:** two small scripts (`agent-llm`, a drop-in stand-in for `claude -p`, and `llm-failover`, a one-command switch) that route your headless Claude Code calls to a local MLX model on your Mac when you flip a flag, and straight back to Claude when you flip it again.

Built for people who **like** Claude and want to keep using it as primary, but don't want a usage cap or an Anthropic outage to halt every script that depends on `claude -p`.

This is **NOT** "ditch Claude and run everything local." For that, see [claude-code-local](https://github.com/nicedreamzapp/claude-code-local) — that project replaces Claude entirely with a local model. This project is the opposite angle: **Claude stays primary**, local is just there for the day you need it.

## What I built

Written by Matt Macosko:

- [`bin/agent-llm`](bin/agent-llm): Python shim that reads the flag file. On `claude` it `exec`s the real Claude CLI with your arguments untouched. On `local` it pulls the prompt from `-p` or stdin, POSTs it to an OpenAI-compatible `/v1/chat/completions` endpoint, and prints the reply.
- [`bin/llm-failover`](bin/llm-failover): Bash switch. `local` writes the flag, loads the LaunchAgent and waits up to 180 s for the server to answer; `claude` writes the flag and unloads the server to free RAM; `status` shows both. Optional notify hook and `-q` quiet flag.
- [`LaunchAgents/com.example.mlxserver.plist.example`](LaunchAgents/com.example.mlxserver.plist.example): launchd template that runs `mlx_lm.server` on demand only (`RunAtLoad` and `KeepAlive` off).

Upstream, not mine: [mlx-lm](https://github.com/ml-explore/mlx-examples/tree/main/llms/mlx_lm) (the local server), Qwen 2.5 (default model weights), and [Claude Code](https://claude.ai/code) (the CLI being wrapped). See [CREDITS.md](CREDITS.md).

---

## When you'd want this

- You're on Claude Max ($100/mo SDK credit, or any tier with a usage cap) and you sometimes hit it mid-month
- You run headless `claude -p` scripts (cron jobs, agents, watchers, custom tooling) and don't want them to die during an Anthropic outage
- You want to run lower-stakes work locally to **preserve your Claude budget for the work that actually needs Claude's quality**
- You have an Apple Silicon Mac with enough RAM to run an MLX model (8 GB minimum for a 7B-class model, 32+ GB for 30B class)

## How it works

```
┌─────────────────────┐
│ Your script         │
│ subprocess.run([    │       reads ~/.local/state/llm-backend
│   "agent-llm",      │ ─────────────────────────────────────────┐
│   "-p", prompt      │                                          │
│ ])                  │                                          │
└─────────────────────┘                                          │
                                                                 ▼
                                          ┌─────────────────────────────────────┐
                                          │ flag = "claude"  →  exec real `claude -p`│
                                          │ flag = "local"   →  POST to localhost:9420│
                                          └─────────────────────────────────────┘
```

**The whole switch is a single text file.** Flip it with `llm-failover local` or `llm-failover claude`. Every subsequent `agent-llm` invocation reads the flag and routes accordingly.

## Lazy-load by default — zero RAM cost when not in failover

`llm-failover` doesn't keep the local server running 24/7. It LOADS the model only when you flip to local mode, and UNLOADS it when you flip back. So most days you're just on Claude with no extra memory pressure. The local model only consumes RAM during an actual failover.

Tradeoff: cold-load on the first call after a flip costs 30-90 seconds (depending on your machine and whether the weights are in OS file cache). After that, calls run at full local speed (~10 tok/s for a 30B-class model on M-series).

If you want INSTANT failover instead, change `RunAtLoad` to `<true/>` in your plist — the server stays warm at the cost of holding the model weights in RAM continuously. Note that `llm-failover claude` still unloads it, so it is warm again only after your next login or `llm-failover local`.

---

## Install

Requires: Apple Silicon Mac (macOS only: `llm-failover` uses `launchctl`), Python 3.9+, `curl`, [Claude Code CLI](https://claude.ai/code), [mlx-lm](https://github.com/ml-explore/mlx-examples/tree/main/llms/mlx_lm).

```bash
# 1. Clone
git clone https://github.com/nicedreamzapp/claude-failover.git
cd claude-failover

# 2. Drop the binaries on your PATH
mkdir -p ~/.local/bin
cp bin/agent-llm bin/llm-failover ~/.local/bin/
chmod +x ~/.local/bin/agent-llm ~/.local/bin/llm-failover

# 3. Set up an mlx-lm venv (the model itself, Qwen 2.5 7B by default,
#    downloads from Hugging Face the first time the server starts)
python3 -m venv ~/.local/share/mlx-server/.venv
~/.local/share/mlx-server/.venv/bin/pip install mlx-lm

# 4. Copy the example LaunchAgent and edit the placeholders
cp LaunchAgents/com.example.mlxserver.plist.example ~/Library/LaunchAgents/com.local.mlxserver.plist
# Replace /PATH/TO/VENV with the absolute path (e.g. /Users/YOU/.local/share/mlx-server)
# and optionally change the --model line

# 5. Verify the failover toggle works
llm-failover status
# expects: "current backend: claude" (default) and "local server: down (lazy)"

llm-failover local
# flips the flag, loads the LaunchAgent, waits for the server
# (the very first run also downloads the model, so it can take longer than 90s
#  and hit the 180s timeout; just run it again once the download finishes)

echo "say hello in one word" | agent-llm -p
# should run on local model

llm-failover claude
# unloads the server, flips back. RAM released.
```

## Wiring your scripts

Find every place in your code that calls Claude programmatically:

```python
# Before
result = subprocess.run(["/opt/homebrew/bin/claude", "-p", prompt], ...)

# After
result = subprocess.run(["/Users/YOU/.local/bin/agent-llm", "-p", prompt], ...)
```

That's it. While the flag is "claude" the shim execs the real Claude CLI and your script behaves identically to before. When you flip the flag, every subsequent call routes to your local server with zero code changes.

## Optional: status indicator on a dashboard

If you have a self-hosted dashboard, poll the flag file (or expose `/api/llm-backend` as an endpoint) and show a colored badge: green for CLAUDE, blue for LOCAL. Useful when an agent has been quietly running on the wrong backend for a while.

```python
# Simple endpoint snippet (Flask)
@app.route("/api/llm-backend")
def llm_backend():
    flag = Path.home() / ".local/state/llm-backend"
    return {"backend": flag.read_text().strip() if flag.exists() else "claude"}
```

## Notify on flip

Set `LLM_NOTIFY_CMD` to any one-arg command (Slack webhook wrapper, iMessage script, Pushover, `say`):

```bash
export LLM_NOTIFY_CMD=/usr/local/bin/my-notify-script
llm-failover local
# → "agent backend flipped to LOCAL. claude usage paused. flip back: llm-failover claude"
```

Add `-q` (or `--quiet`) to flip without sending a notification.

---

## Configuration

All env vars (with defaults):

| Variable               | Default                                              | Purpose                                                 |
|------------------------|------------------------------------------------------|---------------------------------------------------------|
| `LLM_BACKEND_FLAG`     | `~/.local/state/llm-backend`                         | File holding `claude` or `local`                         |
| `CLAUDE_BIN`           | `which claude`, then `/usr/local/bin/claude`         | Path to the real Claude CLI                              |
| `LOCAL_LLM_URL`        | `http://127.0.0.1:9420/v1/chat/completions`          | OpenAI-compatible endpoint                               |
| `LOCAL_LLM_MODEL`      | `mlx-community/Qwen2.5-7B-Instruct-4bit`             | Model id the local server expects                        |
| `LOCAL_LLM_MAX_TOKENS` | `800`                                                | Max output tokens per call                               |
| `LLM_LAUNCHAGENT`      | `com.local.mlxserver`                                | LaunchAgent label `llm-failover` will load/unload       |
| `LLM_PORT`             | `9420`                                               | Port `llm-failover` health-checks (change `LOCAL_LLM_URL` to match) |
| `LLM_NOTIFY_CMD`       | (none)                                               | One-arg command run on flip (notification hook)         |

## Choosing a local model

The default uses Qwen 2.5 7B 4-bit MLX (~4 GB on disk, ~5 GB loaded). It's small enough to run anywhere and good enough for triage / classification / format-conversion work.

Realistic upgrades for more capable replies on Apple Silicon:

| Model                         | Disk    | RAM Loaded | Best For                                      |
|-------------------------------|---------|------------|-----------------------------------------------|
| `mlx-community/Qwen2.5-7B-Instruct-4bit`     | ~4 GB   | ~5 GB      | Default. Fast. Triage, classification.        |
| `mlx-community/gemma-3-27b-it-4bit`          | ~16 GB  | ~22 GB     | Drafts, longer reasoning. Needs 32 GB+ Mac.   |
| `mlx-community/Qwen3-Coder-30B-A3B-Instruct` | ~16 GB  | ~22 GB     | Code/structured output. MoE — 3B active, fast. |
| `mlx-community/Llama-3.3-70B-Instruct-4bit`  | ~40 GB  | ~42 GB     | Closest to Claude quality. Needs 64 GB+ Mac.  |

Just change the `--model` line in your LaunchAgent plist and `LOCAL_LLM_MODEL` env var.

## Honest limitations

Local 7B-30B models won't write replies as good as Claude on tasks that need:
- Deep awareness of your codebase / repo specifics
- Subtle tone or domain knowledge
- Long-context reasoning over many files
- Tool use / web search / advanced coding agents

What the local path does not do yet (see [`bin/agent-llm`](bin/agent-llm)):
- **No automatic failover.** Nothing detects a usage cap or outage. You (or your own script) run `llm-failover local`.
- **Only the prompt is forwarded.** In local mode every flag except `-p` is ignored, so `--output-format json`, `--model`, `--allowedTools`, system prompts and tools do nothing. Output is plain text.
- **One-shot calls only.** Single user message, fixed temperature 0.3, 120 s request timeout, no streaming.
- **macOS only** for the switch. `agent-llm` alone runs anywhere Python does, but `llm-failover` needs `launchctl`.

This project is for **keeping agents alive when Claude is unavailable**, NOT for replacing Claude on its strongest workloads. Expect to flip back to Claude as soon as it's available again.

## License

MIT

## Related

- [CREDITS.md](CREDITS.md): upstream projects this is built on
- [claude-code-local](https://github.com/nicedreamzapp/claude-code-local) — replace Claude entirely with a local model
- [mlx-lm](https://github.com/ml-explore/mlx-examples/tree/main/llms/mlx_lm) — the local server this depends on
- [Claude Code](https://claude.ai/code) — Anthropic's official CLI

---

Tags: claude, claude-code, claude-max, claude-fallback, claude-failover, claude-backup, anthropic-fallback, claude-rate-limit, mlx, mlx-lm, gemma, qwen, llama, apple-silicon, local-llm, offline-llm, llm-router, agent-fallback, claude-usage-limit
