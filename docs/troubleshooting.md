---
title: Troubleshooting claude-failover - error messages, timeouts and common fixes
description: Fixes for claude-failover errors such as LaunchAgent plist not found, TIMEOUT check launchd logs, claude binary not found and agent-llm local error, taken from the error messages in the scripts.
---

# Troubleshooting

Every error below is a message printed by the code. The repository has no GitHub issues yet, so this page is built from the scripts. <!-- TODO-VERIFY: revisit once real issues are filed. -->

## `ERROR: LaunchAgent plist not found at ...`

Printed by `llm-failover local`, exit code 2.

The script looks for `~/Library/LaunchAgents/<LLM_LAUNCHAGENT>.plist`. With defaults that is `~/Library/LaunchAgents/com.local.mlxserver.plist`.

- Copy the example plist to exactly that name (see [Install](install.md#4-install-the-launchagent)), or
- set `LLM_LAUNCHAGENT` to the label you used, so the file name matches.

The flag is already `local` at this point, so also read [the next section](#the-flag-says-local-but-the-server-never-came-up).

## `TIMEOUT — check launchd logs`

Printed by `llm-failover local`, exit code 3, after 180 seconds without a response on `http://127.0.0.1:<LLM_PORT>/v1/models`.

1. **First run:** mlx-lm may still be downloading the model. Wait and run `llm-failover local` again.
2. **Check the server logs** set in the plist: `/tmp/mlxserver.err` and `/tmp/mlxserver.log`.
3. **Wrong venv path:** `/PATH/TO/VENV` must be replaced in both `ProgramArguments` and `WorkingDirectory`.
4. **Port mismatch:** `--port` in the plist must equal `LLM_PORT` (default 9420).
5. **Not enough memory** for the chosen model. Try the default 7B model.

## The flag says local but the server never came up

`llm-failover local` writes `local` to the flag **before** it tries to start the server. If it exits with code 2 or 3, `agent-llm` calls are now going to a server that is not running and will fail with `agent-llm local error: <urlopen error ... Connection refused>`.

Fix the cause and rerun `llm-failover local`, or go back with `llm-failover claude`.

## `agent-llm: claude binary not found at ...`

Printed by `agent-llm` in Claude mode, exit code 127.

`agent-llm` uses `CLAUDE_BIN`, then `claude` on `PATH`, then `/usr/local/bin/claude`. Scripts started by cron or launchd often have a short `PATH`. Set `CLAUDE_BIN` to the full path:

```bash
export CLAUDE_BIN="$(which claude)"
```

## `agent-llm local error: ...`

Printed by `agent-llm` in local mode, exit code 1. The text after the colon is the Python exception. Some likely ones:

| Message contains | Likely cause |
|---|---|
| `Connection refused` | Server not running, or `LOCAL_LLM_URL` points at the wrong port. Run `llm-failover status`. |
| `timed out` | No answer within 120 seconds. Large prompt, large `LOCAL_LLM_MAX_TOKENS`, or a cold model. |
| `HTTP Error 404` | `LOCAL_LLM_URL` must be the full `/v1/chat/completions` URL. |
| `'choices'` | The server answered with JSON that has no `choices` field (often an error body). Check the server logs. |

<!-- TODO-VERIFY: exact exception text varies by Python version and OS; the rows above are what urllib typically raises. -->

## agent-llm hangs with no output

In local mode, if no prompt follows `-p`, `agent-llm` reads stdin until end of file. Run from a terminal with nothing piped in, it waits for you to type. Pass the prompt after `-p` or pipe it in.

## Calls go local when I expected Claude

`agent-llm` treats **anything other than `claude`** in the flag file as local, including `gemma`, `qwen`, typos, or an empty file. Run:

```bash
cat ~/.local/state/llm-backend
llm-failover claude
```

## Local replies ignore `--output-format json` or my system prompt

Expected. In local mode only the prompt is sent. See [What local mode does not do](how-it-works.md#what-local-mode-does-not-do).

## `llm-failover -q local` prints usage

The mode must be the first argument. Use `llm-failover local -q`.

## `ValueError: invalid literal for int()`

`LOCAL_LLM_MAX_TOKENS` must be a whole number. It is parsed on every run, even in Claude mode.

## The server keeps running after `llm-failover claude`

`claude` only unloads the plist if `launchctl list` contains the label. If you started `mlx_lm.server` some other way, or used a different label, stop it yourself or set `LLM_LAUNCHAGENT` to match.
