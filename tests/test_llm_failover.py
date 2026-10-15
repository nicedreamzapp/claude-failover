"""Tests for bin/llm-failover, the Bash backend switch.

`launchctl`, `curl` and `sleep` are replaced by fakes on PATH (see conftest.py),
so the launchd load/unload logic and the 180 s readiness loop run on any
POSIX runner in milliseconds and never touch a real launchd.
"""
from __future__ import annotations

import os
import shutil
import subprocess
import sys

import pytest

from conftest import LLM_FAILOVER, FakeLLMServer


def _uid() -> str:
    return str(os.getuid())


# --------------------------------------------------------------------------- #
# status
# --------------------------------------------------------------------------- #
class TestStatus:
    @pytest.mark.parametrize("args", [(), ("status",), ("status", "-q")])
    def test_default_status_with_no_flag_file(self, run_failover, args):
        r = run_failover(*args)
        assert r.returncode == 0, r.stderr
        assert r.stdout == "current backend: claude\nlocal server: down (lazy)\n"

    def test_status_reports_flag_and_server_up(self, run_failover, flag, mac):
        flag.parent.mkdir(parents=True)
        flag.write_text("local\n")
        mac.up_after = 0
        r = run_failover("status")
        assert r.stdout == "current backend: local\nlocal server: UP (port 9420)\n"

    def test_status_does_not_touch_launchd_or_flag(self, run_failover, flag, mac):
        run_failover("status")
        assert mac.launchctl_calls == []
        assert not flag.exists()

    def test_health_check_uses_llm_port(self, run_failover, mac):
        r = run_failover("status", env={"LLM_PORT": "5555"})
        assert r.returncode == 0
        assert mac.curl_calls == ["-sS --max-time 2 http://127.0.0.1:5555/v1/models"]

    def test_creates_flag_parent_directory(self, run_failover, tmp_path):
        custom = tmp_path / "deep" / "nested" / "flag"
        run_failover("status", env={"LLM_BACKEND_FLAG": str(custom)})
        assert custom.parent.is_dir()

    @pytest.mark.skipif(shutil.which("curl") is None, reason="needs the real curl binary")
    def test_status_with_real_curl_against_real_server(self, run_failover, base_env):
        """End-to-end health check: real curl hitting a real HTTP server on loopback."""
        with FakeLLMServer() as srv:
            r = run_failover("status", fake_tools=False, env={"LLM_PORT": str(srv.port)})
        assert r.returncode == 0, r.stderr
        assert f"local server: UP (port {srv.port})" in r.stdout
        assert {"method": "GET", "path": "/v1/models"} in srv.requests


# --------------------------------------------------------------------------- #
# local
# --------------------------------------------------------------------------- #
class TestLocal:
    def test_server_already_up_just_flips_flag(self, run_failover, flag, mac):
        mac.up_after = 0
        r = run_failover("local")
        assert r.returncode == 0, r.stderr
        assert flag.read_text() == "local\n"
        assert r.stdout == "agent backend now: local (port 9420)\nlocal server already up\n"
        assert mac.launchctl_calls == []

    @pytest.mark.parametrize("alias", ["gemma", "qwen"])
    def test_aliases_write_local(self, run_failover, flag, mac, alias):
        mac.up_after = 0
        r = run_failover(alias)
        assert r.returncode == 0
        assert flag.read_text() == "local\n"

    def test_cold_start_loads_kickstarts_and_waits(self, run_failover, flag, mac, plist):
        # 1st curl = initial check (down); loop polls i=1..; up once >11 calls.
        mac.up_after = 11
        r = run_failover("local")
        assert r.returncode == 0, r.stderr
        assert flag.read_text() == "local\n"
        assert mac.launchctl_calls == [
            f"load {plist}",
            f"kickstart gui/{_uid()}/com.local.mlxserver",
        ]
        assert "ready (11s)" in r.stdout
        assert ".." in r.stdout  # progress dots at i=5 and i=10

    def test_custom_label_and_port(self, run_failover, mac, home):
        label = "dev.example.llm"
        p = home / "Library" / "LaunchAgents" / f"{label}.plist"
        p.parent.mkdir(parents=True)
        p.write_text("<plist/>")
        mac.up_after = 1
        r = run_failover("local", env={"LLM_LAUNCHAGENT": label, "LLM_PORT": "7777"})
        assert r.returncode == 0, r.stderr
        assert "agent backend now: local (port 7777)" in r.stdout
        assert mac.launchctl_calls == [f"load {p}", f"kickstart gui/{_uid()}/{label}"]
        assert all("127.0.0.1:7777" in c for c in mac.curl_calls)

    def test_missing_plist_exits_2(self, run_failover, flag, mac, home):
        r = run_failover("local")
        assert r.returncode == 2
        assert "LaunchAgent plist not found" in r.stderr
        assert str(home / "Library" / "LaunchAgents" / "com.local.mlxserver.plist") in r.stderr
        assert "com.example.mlxserver.plist.example" in r.stderr
        assert mac.launchctl_calls == []
        # Documented in docs/troubleshooting.md: the flag is already "local" here.
        assert flag.read_text() == "local\n"

    def test_timeout_exits_3_after_180_polls(self, run_failover, flag, mac, plist):
        mac.up_after = None  # never comes up
        r = run_failover("local")
        assert r.returncode == 3
        assert "TIMEOUT" in r.stdout
        # 1 initial check + 180 loop polls + 1 final check
        assert len(mac.curl_calls) == 182
        assert r.stdout.count(".") >= 180 // 5
        assert flag.read_text() == "local\n"
        assert mac.notifications == []

    def test_launchctl_failure_is_tolerated(self, run_failover, mac, plist):
        (mac.bin / "launchctl").write_text("#!/bin/sh\nexit 5\n")
        mac.up_after = 1
        r = run_failover("local")
        assert r.returncode == 0, r.stderr

    def test_notify_on_success(self, run_failover, mac):
        mac.up_after = 0
        run_failover("local", env={"LLM_NOTIFY_CMD": str(mac.notify)})
        assert mac.notifications == [
            "agent backend flipped to LOCAL. claude usage paused. flip back: llm-failover claude"
        ]

    @pytest.mark.parametrize("quiet", ["-q", "--quiet"])
    def test_quiet_suppresses_notify(self, run_failover, mac, quiet):
        mac.up_after = 0
        r = run_failover("local", quiet, env={"LLM_NOTIFY_CMD": str(mac.notify)})
        assert r.returncode == 0
        assert mac.notifications == []

    def test_failing_notify_command_does_not_fail_flip(self, run_failover, mac, tmp_path):
        mac.up_after = 0
        bad = tmp_path / "bad-notify"
        bad.write_text("#!/bin/sh\necho noisy; exit 9\n")
        bad.chmod(0o755)
        r = run_failover("local", env={"LLM_NOTIFY_CMD": str(bad)})
        assert r.returncode == 0
        assert "noisy" not in r.stdout

    def test_missing_notify_command_does_not_fail_flip(self, run_failover, mac, tmp_path):
        mac.up_after = 0
        r = run_failover("local", env={"LLM_NOTIFY_CMD": str(tmp_path / "nope")})
        assert r.returncode == 0


# --------------------------------------------------------------------------- #
# claude
# --------------------------------------------------------------------------- #
class TestClaude:
    def test_flips_flag_and_unloads_loaded_server(self, run_failover, flag, mac, plist):
        flag.parent.mkdir(parents=True)
        flag.write_text("local\n")
        mac.loaded_label = "com.local.mlxserver"
        r = run_failover("claude")
        assert r.returncode == 0, r.stderr
        assert flag.read_text() == "claude\n"
        assert mac.launchctl_calls == ["list", f"unload {plist}"]
        assert r.stdout == "agent backend now: claude\nlocal server unloaded (memory freed)\n"

    def test_no_unload_when_not_loaded(self, run_failover, flag, mac):
        r = run_failover("claude")
        assert r.returncode == 0, r.stderr
        assert flag.read_text() == "claude\n"
        assert mac.launchctl_calls == ["list"]
        assert r.stdout == "agent backend now: claude\n"

    def test_notify_and_quiet(self, run_failover, mac):
        run_failover("claude", env={"LLM_NOTIFY_CMD": str(mac.notify)})
        run_failover("claude", "-q", env={"LLM_NOTIFY_CMD": str(mac.notify)})
        assert mac.notifications == ["agent backend flipped back to CLAUDE."]

    def test_round_trip_local_then_claude(self, run_failover, flag, mac, plist):
        mac.up_after = 1
        assert run_failover("local").returncode == 0
        assert flag.read_text() == "local\n"
        mac.loaded_label = "com.local.mlxserver"
        assert run_failover("claude").returncode == 0
        assert flag.read_text() == "claude\n"
        assert mac.launchctl_calls[-1] == f"unload {plist}"


# --------------------------------------------------------------------------- #
# argument handling
# --------------------------------------------------------------------------- #
class TestUsage:
    @pytest.mark.parametrize("args", [("bogus",), ("-q", "local"), ("LOCAL",)])
    def test_unknown_command_prints_usage_and_exits_1(self, run_failover, flag, args):
        r = run_failover(*args)
        assert r.returncode == 1
        assert r.stderr.startswith("usage: llm-failover")
        assert not flag.exists()


# --------------------------------------------------------------------------- #
# The flag file contract shared by both scripts
# --------------------------------------------------------------------------- #
class TestFlagContract:
    def test_failover_flag_is_honoured_by_agent_llm(
        self, run_failover, run_agent, mac, llm_server, fake_claude
    ):
        mac.up_after = 0
        run_failover("local")
        env = {"CLAUDE_BIN": str(fake_claude.path), "LOCAL_LLM_URL": llm_server.url}
        r = run_agent("-p", "via local", env=env)
        assert r.stdout == "hello from local\n"
        assert fake_claude.call() is None

        run_failover("claude")
        run_agent("-p", "via claude", env=env)
        assert fake_claude.call()["argv"][1:] == ["-p", "via claude"]


@pytest.mark.skipif(sys.platform != "darwin", reason="exercises the stock macOS /bin/bash (3.2)")
def test_runs_under_macos_system_bash(base_env, mac):
    mac._sync()
    env = dict(base_env, PATH=f"{mac.bin}:{base_env['PATH']}")
    r = subprocess.run(["/bin/bash", str(LLM_FAILOVER), "status"], capture_output=True, text=True, env=env)
    assert r.returncode == 0, r.stderr
    assert "current backend: claude" in r.stdout
