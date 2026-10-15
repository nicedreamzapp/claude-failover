---
title: claude-failover FAQ - usage limits, outages, local models and Claude Code
description: Answers about claude-failover. Does it switch automatically, does it work with the interactive Claude Code UI, which local model to use, Linux support, and what happens to flags in local mode.
---

# FAQ

## Does it switch to local automatically when I hit my Claude limit?

No. Nothing in the code detects a usage limit or an outage. You run `llm-failover local`, or have your own script do it.

## Does this work with interactive Claude Code?

It is built for headless `claude -p` calls from scripts. In Claude mode `agent-llm` passes any arguments to `claude`, but in local mode it only handles a single prompt and prints one reply, so it is not a substitute for the interactive session.

## Does it cost anything while I'm on Claude?

Not in memory. The local server is only loaded between `llm-failover local` and `llm-failover claude`. In Claude mode `agent-llm` replaces itself with the real `claude` process, so it adds only a Python start-up before exec.

## Which local model should I use?

The default is `mlx-community/Qwen2.5-7B-Instruct-4bit`. The [Configuration](configuration.md#choosing-a-model) page lists the larger options the README suggests and how to switch.

## Can I use Ollama, LM Studio or llama.cpp instead of mlx-lm?

`agent-llm` will talk to any server with an OpenAI-compatible `/v1/chat/completions` endpoint; set `LOCAL_LLM_URL`. `llm-failover` only knows how to start and stop a launchd job and health-checks `/v1/models`, so you would manage that server yourself and write the flag directly. <!-- TODO-VERIFY: not tested against these servers in the repo. -->

## Does it run on Linux or Intel Macs?

`agent-llm` is plain Python and runs anywhere. `llm-failover` needs `launchctl` (macOS), and the example server is mlx-lm, which targets Apple Silicon.

## Do my `--output-format json` or `--allowedTools` flags work in local mode?

No. Only the prompt is forwarded. Output is plain text.

## Can I name the shim `claude` so I don't have to edit scripts?

Not with the default settings. In Claude mode `agent-llm` finds the real CLI with `which claude`, which would find the shim itself. If you try this, set `CLAUDE_BIN` to the real CLI's full path. <!-- TODO-VERIFY: this setup is not documented or tested in the repo. -->

## How is this different from claude-code-local?

[claude-code-local](https://github.com/nicedreamzapp/claude-code-local) replaces Claude with a local model. claude-failover keeps Claude as the default and uses a local model only while you switch to it.

## Is it affiliated with Anthropic?

No. It wraps Anthropic's Claude Code CLI, which you install separately.

## What license is it under?

MIT.
