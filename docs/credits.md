---
title: Credits - the upstream projects claude-failover is built on
description: claude-failover is two small scripts around other people's work. Credits for Claude Code by Anthropic, mlx-lm and MLX by Apple's ml-explore team, and Qwen 2.5 by Alibaba's Qwen team.
---

# Credits

claude-failover is two scripts and a launchd template written by Matt Macosko. The heavy lifting is done by these projects:

| Project | Role here | By |
|---|---|---|
| [Claude Code](https://claude.ai/code) | The CLI that `agent-llm` wraps and that stays the primary backend. | Anthropic |
| [mlx-lm](https://github.com/ml-explore/mlx-examples/tree/main/llms/mlx_lm) | `mlx_lm.server`, the local OpenAI-compatible server. | Apple's ml-explore team |
| [MLX](https://github.com/ml-explore/mlx) | The array framework mlx-lm runs on. | Apple's ml-explore team |
| [Qwen 2.5](https://qwenlm.github.io/) | Default local model weights (`mlx-community/Qwen2.5-7B-Instruct-4bit`). | Alibaba's Qwen team |
| [mlx-community](https://huggingface.co/mlx-community) | MLX conversions of the model weights referenced in the docs. | Hugging Face community |

The other models listed in [Configuration](configuration.md#choosing-a-model) (Gemma 3, Qwen3-Coder, Llama 3.3) belong to their respective authors.

This documentation site is built with [MkDocs](https://www.mkdocs.org/) and [Material for MkDocs](https://squidfunk.github.io/mkdocs-material/).

If your work is listed here and you'd like the wording changed, or something is missing, [open an issue](https://github.com/nicedreamzapp/claude-failover/issues).
