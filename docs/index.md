---
title: claude-failover - run claude -p scripts on a local LLM when Claude is unavailable
description: claude-failover is a drop-in stand-in for claude -p plus a one-command switch that routes headless Claude Code calls to a local mlx-lm model on Apple Silicon when you hit a usage limit or Claude is down.
---

# claude-failover

Your cron jobs and agents call `claude -p`. One day the plan hits its usage limit, or Claude has an outage, and every one of them stops. claude-failover lets you run `llm-failover local` and have those same calls answered by a local model on your Mac, then `llm-failover claude` to go back.

It is two small scripts:

- **`agent-llm`**: a stand-in for `claude -p`. While the backend is `claude` it hands your exact arguments to the real Claude Code CLI. While the backend is `local` it sends the prompt to a local OpenAI-compatible server and prints the reply.
- **`llm-failover`**: the switch. It writes the backend flag and starts or stops the local [mlx-lm](https://github.com/ml-explore/mlx-examples/tree/main/llms/mlx_lm) server through a macOS LaunchAgent.

Claude stays the default. The local model only runs, and only uses RAM, while you are switched to it.

```text
your script ──> agent-llm -p "prompt"
                    │
                    ├─ flag = claude ──> exec the real `claude` CLI (same args)
                    └─ flag = local  ──> POST http://127.0.0.1:9420/v1/chat/completions
```

## Who it is for

- You run headless `claude -p` calls from scripts, cron jobs, watchers or your own tools.
- You want Claude to stay primary, but you do not want a usage cap or an outage to halt everything.
- You have an Apple Silicon Mac that can hold an MLX model in memory. The project README gives 8 GB as the minimum for a 7B-class model and 32 GB+ for 30B-class models. <!-- TODO-VERIFY: RAM guidance comes from the README, not from a test in the repo. -->

## Who it is not for

If you want to replace Claude with a local model entirely, see the sibling project [claude-code-local](https://github.com/nicedreamzapp/claude-code-local). claude-failover is the opposite angle: Claude is primary and local is the backup.

It is also not a full Claude Code replacement in local mode. Only the prompt text is forwarded; tools, system prompts, `--output-format` and other flags are dropped. See [How it works](how-it-works.md#what-local-mode-does-not-do).

## Screenshots

The repository does not contain screenshots or GIFs yet. <!-- TODO-VERIFY: add a terminal recording of `llm-failover local` / `agent-llm -p` if Matt wants one. -->

## Next steps

- [Install](install.md) the two scripts and the LaunchAgent.
- [Quickstart](quickstart.md): flip to local, send one prompt, flip back.
- [Configuration](configuration.md): every environment variable and command.
