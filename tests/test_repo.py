"""Static checks: script syntax, the LaunchAgent template, and docs that
quote defaults from the code. These catch drift between files that must agree.
"""
from __future__ import annotations

import os
import plistlib
import py_compile
import re
import shutil
import subprocess
import sys

import pytest

from conftest import AGENT_LLM, LLM_FAILOVER, PLIST_EXAMPLE, REPO


def test_agent_llm_compiles(tmp_path):
    py_compile.compile(str(AGENT_LLM), cfile=str(tmp_path / "agent-llm.pyc"), doraise=True)


def test_llm_failover_bash_syntax():
    r = subprocess.run(["bash", "-n", str(LLM_FAILOVER)], capture_output=True, text=True)
    assert r.returncode == 0, r.stderr


@pytest.mark.parametrize("script", [AGENT_LLM, LLM_FAILOVER], ids=lambda p: p.name)
def test_scripts_are_executable_with_shebang(script):
    assert os.access(script, os.X_OK), f"{script.name} is not executable"
    assert script.read_text().startswith("#!/usr/bin/env ")


# --------------------------------------------------------------------------- #
# LaunchAgent template
# --------------------------------------------------------------------------- #
@pytest.fixture(scope="module")
def plist():
    with PLIST_EXAMPLE.open("rb") as f:
        return plistlib.load(f)


def _arg(args, name):
    return args[args.index(name) + 1]


def test_plist_is_on_demand_only(plist):
    assert plist["RunAtLoad"] is False
    assert plist["KeepAlive"] is False


def test_plist_label_matches_llm_failover_default(plist):
    assert plist["Label"] == "com.local.mlxserver"
    assert 'LABEL="${LLM_LAUNCHAGENT:-com.local.mlxserver}"' in LLM_FAILOVER.read_text()


def test_plist_runs_mlx_lm_server_on_default_host_port_and_model(plist):
    args = plist["ProgramArguments"]
    assert args[1:3] == ["-m", "mlx_lm.server"]
    assert _arg(args, "--host") == "127.0.0.1"
    assert _arg(args, "--port") == "9420"
    agent = AGENT_LLM.read_text()
    assert f'"{_arg(args, "--model")}"' in agent  # same default model as agent-llm
    assert 'PORT="${LLM_PORT:-9420}"' in LLM_FAILOVER.read_text()
    assert "http://127.0.0.1:9420/v1/chat/completions" in agent


@pytest.mark.skipif(sys.platform != "darwin" or not shutil.which("plutil"), reason="plutil is macOS-only")
def test_plist_passes_plutil_lint():
    r = subprocess.run(["plutil", "-lint", str(PLIST_EXAMPLE)], capture_output=True, text=True)
    assert r.returncode == 0, r.stdout + r.stderr


# --------------------------------------------------------------------------- #
# Documentation agrees with the code
# --------------------------------------------------------------------------- #
CODE_DEFAULTS = {
    "LLM_BACKEND_FLAG": "~/.local/state/llm-backend",
    "LOCAL_LLM_URL": "http://127.0.0.1:9420/v1/chat/completions",
    "LOCAL_LLM_MODEL": "mlx-community/Qwen2.5-7B-Instruct-4bit",
    "LOCAL_LLM_MAX_TOKENS": "800",
    "LLM_LAUNCHAGENT": "com.local.mlxserver",
    "LLM_PORT": "9420",
}


def test_code_defaults_are_what_we_think():
    agent = AGENT_LLM.read_text()
    failover = LLM_FAILOVER.read_text()
    assert '"LOCAL_LLM_URL", "http://127.0.0.1:9420/v1/chat/completions"' in agent
    assert '"LOCAL_LLM_MODEL", "mlx-community/Qwen2.5-7B-Instruct-4bit"' in agent
    assert '"LOCAL_LLM_MAX_TOKENS", "800"' in agent
    assert 'Path.home() / ".local" / "state" / "llm-backend"' in agent
    assert 'FLAG="${LLM_BACKEND_FLAG:-$HOME/.local/state/llm-backend}"' in failover


@pytest.mark.parametrize("doc", ["README.md", "docs/configuration.md"])
@pytest.mark.parametrize("var", sorted(CODE_DEFAULTS))
def test_docs_config_table_matches_code(doc, var):
    rows = [l for l in (REPO / doc).read_text().splitlines() if l.startswith(f"| `{var}`")]
    assert rows, f"{var} missing from the config table in {doc}"
    assert CODE_DEFAULTS[var] in rows[0], f"{doc} documents a different default for {var}"


@pytest.mark.parametrize("var", sorted(CODE_DEFAULTS) + ["CLAUDE_BIN", "LLM_NOTIFY_CMD"])
def test_every_env_var_used_in_code_is_documented(var):
    code = AGENT_LLM.read_text() + LLM_FAILOVER.read_text()
    assert var in code
    assert f"`{var}`" in (REPO / "README.md").read_text()


def test_no_undocumented_env_vars():
    code = AGENT_LLM.read_text() + LLM_FAILOVER.read_text()
    used = set(re.findall(r'environ\.get\("([A-Z_]+)"', code)) | set(re.findall(r"\$\{([A-Z_]+):-", code))
    used.discard("HOME")
    readme = (REPO / "README.md").read_text()
    assert used, "regexes found no env vars; did the scripts change shape?"
    missing = sorted(v for v in used if f"`{v}`" not in readme)
    assert not missing, f"env vars read by the code but not in README: {missing}"
