"""Tests for bin/agent-llm, the `claude -p` stand-in.

Covers backend selection from the flag file, the Claude pass-through (exec),
prompt parsing in local mode, the request sent to the OpenAI-compatible server,
response handling, and every error path that sets a non-zero exit code.
"""
from __future__ import annotations

import pytest


def _flag(path, value: str):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(value)
    return path


# --------------------------------------------------------------------------- #
# Backend selection
# --------------------------------------------------------------------------- #
class TestBackendSelection:
    def test_missing_flag_file_defaults_to_claude(self, run_agent, fake_claude, flag):
        assert not flag.exists()
        r = run_agent("-p", "hi", env={"CLAUDE_BIN": str(fake_claude.path)})
        assert fake_claude.call() is not None
        assert r.stdout == "FAKE CLAUDE OUTPUT\n"

    @pytest.mark.parametrize("value", ["claude", "claude\n", "  Claude  \n", "CLAUDE"])
    def test_claude_flag_is_trimmed_and_case_insensitive(self, run_agent, fake_claude, flag, value):
        _flag(flag, value)
        run_agent("-p", "hi", env={"CLAUDE_BIN": str(fake_claude.path)})
        assert fake_claude.call() is not None

    @pytest.mark.parametrize("value", ["local", "local\n", "LOCAL"])
    def test_local_flag_routes_to_server(self, run_agent, fake_claude, flag, llm_server, value):
        _flag(flag, value)
        r = run_agent(
            "-p", "hi", env={"CLAUDE_BIN": str(fake_claude.path), "LOCAL_LLM_URL": llm_server.url}
        )
        assert r.returncode == 0, r.stderr
        assert fake_claude.call() is None
        assert len(llm_server.requests) == 1

    @pytest.mark.parametrize("value", ["", "gemma", "qwen", "clade"])
    def test_any_other_flag_value_routes_local(self, run_agent, fake_claude, flag, llm_server, value):
        # Documented in docs/configuration.md ("Any other value ... local mode").
        _flag(flag, value)
        r = run_agent(
            "-p", "hi", env={"CLAUDE_BIN": str(fake_claude.path), "LOCAL_LLM_URL": llm_server.url}
        )
        assert r.returncode == 0, r.stderr
        assert fake_claude.call() is None

    def test_llm_backend_flag_env_overrides_default_path(self, run_agent, fake_claude, flag, tmp_path, llm_server):
        _flag(flag, "claude")  # default location says claude...
        custom = _flag(tmp_path / "elsewhere" / "flag", "local")  # ...override says local
        r = run_agent(
            "-p",
            "hi",
            env={
                "LLM_BACKEND_FLAG": str(custom),
                "CLAUDE_BIN": str(fake_claude.path),
                "LOCAL_LLM_URL": llm_server.url,
            },
        )
        assert r.returncode == 0, r.stderr
        assert fake_claude.call() is None
        assert len(llm_server.requests) == 1


# --------------------------------------------------------------------------- #
# Claude mode: exec pass-through
# --------------------------------------------------------------------------- #
class TestClaudeMode:
    def test_args_passed_through_untouched(self, run_agent, fake_claude):
        args = ["-p", "multi word prompt", "--output-format", "json", "--model", "x y", ""]
        run_agent(*args, env={"CLAUDE_BIN": str(fake_claude.path)})
        call = fake_claude.call()
        assert call["argv"][1:] == args

    def test_stdin_stdout_and_exit_code_belong_to_claude(self, run_agent, fake_claude):
        r = run_agent("-p", env={"CLAUDE_BIN": str(fake_claude.path)}, stdin="piped prompt")
        assert fake_claude.call()["stdin"] == "piped prompt"
        assert r.stdout == "FAKE CLAUDE OUTPUT\n"
        assert r.returncode == 7  # the fake's exit code, proving the process was replaced

    def test_claude_found_on_path(self, run_agent, fake_claude, tmp_path, base_env):
        bindir = tmp_path / "pathbin"
        bindir.mkdir()
        (bindir / "claude").symlink_to(fake_claude.path)
        run_agent("-p", "hi", env={"PATH": f"{bindir}:{base_env['PATH']}"})
        assert fake_claude.call()["argv"][1:] == ["-p", "hi"]

    def test_claude_bin_env_wins_over_path(self, run_agent, fake_claude, tmp_path, base_env):
        bindir = tmp_path / "pathbin"
        bindir.mkdir()
        decoy = bindir / "claude"
        decoy.write_text("#!/bin/sh\necho DECOY\n")
        decoy.chmod(0o755)
        r = run_agent(
            "-p", "hi", env={"PATH": f"{bindir}:{base_env['PATH']}", "CLAUDE_BIN": str(fake_claude.path)}
        )
        assert "DECOY" not in r.stdout
        assert fake_claude.call() is not None

    def test_missing_claude_binary_exits_127(self, run_agent, tmp_path):
        missing = tmp_path / "no-such-claude"
        r = run_agent("-p", "hi", env={"CLAUDE_BIN": str(missing)})
        assert r.returncode == 127
        assert "claude binary not found" in r.stderr
        assert str(missing) in r.stderr
        assert r.stdout == ""

    def test_invalid_max_tokens_crashes_even_in_claude_mode(self, run_agent, fake_claude):
        # Documented in docs/configuration.md: parsed at startup in both modes.
        r = run_agent(
            "-p", "hi", env={"CLAUDE_BIN": str(fake_claude.path), "LOCAL_LLM_MAX_TOKENS": "lots"}
        )
        assert r.returncode != 0
        assert "ValueError" in r.stderr
        assert fake_claude.call() is None


# --------------------------------------------------------------------------- #
# Local mode: prompt parsing
# --------------------------------------------------------------------------- #
@pytest.fixture
def local(run_agent, flag, llm_server, fake_claude):
    """Run agent-llm in local mode and return (result, prompt the server saw)."""
    _flag(flag, "local")

    def _run(*args, stdin="", env=None):
        e = {"LOCAL_LLM_URL": llm_server.url, "CLAUDE_BIN": str(fake_claude.path)}
        e.update(env or {})
        r = run_agent(*args, env=e, stdin=stdin)
        prompt = llm_server.requests[-1]["json"]["messages"][0]["content"] if llm_server.requests else None
        return r, prompt

    return _run


class TestLocalPromptParsing:
    def test_prompt_after_dash_p(self, local):
        r, prompt = local("-p", "what is 2+2")
        assert r.returncode == 0, r.stderr
        assert prompt == "what is 2+2"

    def test_prompt_from_stdin_when_dash_p_is_last(self, local):
        _, prompt = local("-p", stdin="from stdin\nline two")
        assert prompt == "from stdin\nline two"

    def test_prompt_from_stdin_without_dash_p(self, local):
        _, prompt = local(stdin="no flag at all")
        assert prompt == "no flag at all"

    def test_other_flags_are_ignored(self, local):
        _, prompt = local("--output-format", "json", "-p", "the prompt", "--model", "sonnet")
        assert prompt == "the prompt"

    def test_last_dash_p_wins(self, local):
        _, prompt = local("-p", "first", "-p", "second")
        assert prompt == "second"

    def test_empty_prompt_arg_falls_back_to_stdin(self, local):
        _, prompt = local("-p", "", stdin="stdin wins")
        assert prompt == "stdin wins"

    def test_unicode_prompt_round_trips(self, local):
        _, prompt = local("-p", "café ☕ 日本語")
        assert prompt == "café ☕ 日本語"

    def test_flag_value_after_dash_p_is_taken_as_prompt(self, local):
        # Known limitation documented in docs/quickstart.md: the argument right
        # after -p is always the prompt, even if it looks like a flag.
        _, prompt = local("-p", "--output-format", "json")
        assert prompt == "--output-format"

    def test_long_form_print_is_not_recognised(self, local):
        # Known limitation documented in docs/how-it-works.md.
        _, prompt = local("--print", "ignored", stdin="stdin used instead")
        assert prompt == "stdin used instead"


# --------------------------------------------------------------------------- #
# Local mode: request and response
# --------------------------------------------------------------------------- #
class TestLocalRequest:
    def test_default_request_body(self, local, llm_server):
        local("-p", "hi")
        req = llm_server.requests[0]
        assert req["method"] == "POST"
        assert req["path"] == "/v1/chat/completions"
        assert req["headers"]["Content-Type"] == "application/json"
        assert req["json"] == {
            "model": "mlx-community/Qwen2.5-7B-Instruct-4bit",
            "messages": [{"role": "user", "content": "hi"}],
            "max_tokens": 800,
            "temperature": 0.3,
        }

    def test_model_and_max_tokens_from_env(self, local, llm_server):
        local("-p", "hi", env={"LOCAL_LLM_MODEL": "my/model", "LOCAL_LLM_MAX_TOKENS": "42"})
        body = llm_server.requests[0]["json"]
        assert body["model"] == "my/model"
        assert body["max_tokens"] == 42

    def test_url_from_env_is_used_verbatim(self, local, llm_server):
        url = f"http://127.0.0.1:{llm_server.port}/custom/path"
        local("-p", "hi", env={"LOCAL_LLM_URL": url})
        assert llm_server.requests[0]["path"] == "/custom/path"


class TestLocalResponse:
    def test_prints_content_with_single_trailing_newline(self, local, llm_server):
        llm_server.response = {"choices": [{"message": {"content": "  answer text \n\n"}}]}
        r, _ = local("-p", "hi")
        assert r.returncode == 0
        assert r.stdout == "answer text\n"
        assert r.stderr == ""

    def test_multiline_content_preserved(self, local, llm_server):
        llm_server.response = {"choices": [{"message": {"content": "line 1\nline 2"}}]}
        r, _ = local("-p", "hi")
        assert r.stdout == "line 1\nline 2\n"

    @pytest.mark.parametrize("content", ["", None])
    def test_falls_back_to_reasoning_field(self, local, llm_server, content):
        llm_server.response = {"choices": [{"message": {"content": content, "reasoning": "thought it through"}}]}
        r, _ = local("-p", "hi")
        assert r.returncode == 0
        assert r.stdout == "thought it through\n"

    def test_content_preferred_over_reasoning(self, local, llm_server):
        llm_server.response = {"choices": [{"message": {"content": "final", "reasoning": "scratch"}}]}
        r, _ = local("-p", "hi")
        assert r.stdout == "final\n"

    def test_empty_reply_prints_blank_line_and_succeeds(self, local, llm_server):
        llm_server.response = {"choices": [{"message": {"content": ""}}]}
        r, _ = local("-p", "hi")
        assert r.returncode == 0
        assert r.stdout == "\n"

    def test_only_first_choice_is_used(self, local, llm_server):
        llm_server.response = {"choices": [{"message": {"content": "one"}}, {"message": {"content": "two"}}]}
        r, _ = local("-p", "hi")
        assert r.stdout == "one\n"


class TestLocalErrors:
    def _assert_error(self, r, needle: str):
        assert r.returncode == 1
        assert r.stdout == ""
        assert r.stderr.startswith("agent-llm local error:")
        assert needle in r.stderr

    def test_connection_refused(self, local, free_port):
        r, _ = local("-p", "hi", env={"LOCAL_LLM_URL": f"http://127.0.0.1:{free_port}/v1/chat/completions"})
        self._assert_error(r, "refused")

    def test_http_error_status(self, local, llm_server):
        llm_server.status = 500
        llm_server.response = {"error": "boom"}
        r, _ = local("-p", "hi")
        self._assert_error(r, "HTTP Error 500")

    def test_404_from_wrong_url(self, local, llm_server):
        llm_server.status = 404
        r, _ = local("-p", "hi")
        self._assert_error(r, "HTTP Error 404")

    def test_response_without_choices(self, local, llm_server):
        llm_server.response = {"error": {"message": "model not loaded"}}
        r, _ = local("-p", "hi")
        self._assert_error(r, "'choices'")

    def test_empty_choices_list(self, local, llm_server):
        llm_server.response = {"choices": []}
        r, _ = local("-p", "hi")
        self._assert_error(r, "list index out of range")

    def test_non_json_body(self, local, llm_server):
        llm_server.raw_body = b"<html>not json</html>"
        r, _ = local("-p", "hi")
        self._assert_error(r, "")

    def test_malformed_url(self, local):
        r, _ = local("-p", "hi", env={"LOCAL_LLM_URL": "not a url"})
        self._assert_error(r, "unknown url type")
