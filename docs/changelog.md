---
title: claude-failover changelog - history from git
description: Change history of claude-failover built from the repository's git log. No tagged releases yet.
---

# Changelog

There are no tagged releases. This list comes from the commits on `main`.

## 2026-09-27

README rewrite, merged from pull request #1 (`a33a2e8`, change in `9287839`).

- Added a plain summary of what the two scripts do and a "What I built" section separating the project's own files from upstream work.
- Documented local-mode limits accurately: no automatic failover, only the prompt is forwarded, one-shot calls with fixed temperature 0.3 and a 120 s timeout, macOS only for the switch.
- Install steps note that the first `llm-failover local` downloads the model and can hit the 180 s timeout.

## 2026-08-06

`bac62dc`: added `CREDITS.md` naming mlx-lm, Qwen 2.5 and Claude Code.

## 2026-05-14

`307e217`: first commit. `bin/agent-llm`, `bin/llm-failover`, the example LaunchAgent plist, README and MIT license.
