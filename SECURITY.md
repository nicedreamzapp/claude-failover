# Security policy

## Reporting a vulnerability

Please do not open a public issue for security problems.

Report them privately through GitHub: go to the **Security** tab of this repo and click **Report a vulnerability** ([direct link](https://github.com/nicedreamzapp/claude-failover/security/advisories/new)). Only the maintainer sees the report.

Helpful details: what you found, how to reproduce it, which commit, your Mac and macOS version, and the env vars you had set.

I aim to reply within 3 days and to ship a fix or a clear plan within 30 days, depending on severity. You will be credited in the advisory unless you ask not to be.

## Supported versions

Fixes go into the latest code on `main`. Please update before reporting if you are on an older version.

## What matters most here

The parts where a mistake could hurt someone:

- `bin/agent-llm`, which runs the real Claude CLI with your arguments, or sends the prompt to the URL in `LOCAL_LLM_URL`
- the flag file at `~/.local/state/llm-backend`, which decides where every prompt goes
- `bin/llm-failover`, which loads and unloads a LaunchAgent and runs the command in `LLM_NOTIFY_CMD`
- the example LaunchAgent in `LaunchAgents/`, which starts `mlx_lm.server` on `127.0.0.1` port 9420
