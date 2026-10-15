"""Shared fixtures for the claude-failover test suite.

Both scripts are exercised as real subprocesses, the way users run them.
Nothing here needs a GPU, a model download, the network, or macOS:

* the real `claude` CLI is replaced by a tiny fake that records its argv/stdin,
* the local LLM server is a stdlib HTTP server on 127.0.0.1 with a random port,
* `launchctl`, `curl` and `sleep` are replaced by fakes on PATH for llm-failover.

Each subprocess gets a minimal environment built from scratch, so settings,
proxies or tokens from the developer's shell cannot leak into a test.
"""
from __future__ import annotations

import json
import os
import shutil
import stat
import subprocess
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
AGENT_LLM = REPO / "bin" / "agent-llm"
LLM_FAILOVER = REPO / "bin" / "llm-failover"
PLIST_EXAMPLE = REPO / "LaunchAgents" / "com.example.mlxserver.plist.example"

# Directories holding the system tools the scripts need (bash, cat, grep, seq...).
_SYSTEM_PATH = os.pathsep.join(
    p for p in ("/usr/local/bin", "/usr/bin", "/bin", "/usr/sbin", "/sbin") if os.path.isdir(p)
)


def write_exe(path: Path, body: str) -> Path:
    path.write_text(body)
    path.chmod(path.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
    return path


@pytest.fixture
def home(tmp_path: Path) -> Path:
    h = tmp_path / "home"
    h.mkdir()
    return h


@pytest.fixture
def base_env(home: Path) -> dict:
    """A clean environment: no proxies, no tokens, HOME pointed at a temp dir."""
    return {
        "PATH": _SYSTEM_PATH,
        "HOME": str(home),
        "LANG": "C.UTF-8",
        "PYTHONDONTWRITEBYTECODE": "1",
    }


@pytest.fixture
def flag(home: Path) -> Path:
    """Default flag-file location the scripts use when LLM_BACKEND_FLAG is unset."""
    return home / ".local" / "state" / "llm-backend"


# --------------------------------------------------------------------------- #
# Fake Claude CLI
# --------------------------------------------------------------------------- #
@pytest.fixture
def fake_claude(tmp_path: Path):
    """A stand-in `claude` binary that dumps its argv and stdin as JSON."""
    record = tmp_path / "claude-call.json"
    script = tmp_path / "fake-claude"
    write_exe(
        script,
        f"""#!{sys.executable}
import json, sys
data = {{"argv": sys.argv, "stdin": "" if sys.stdin.isatty() else sys.stdin.read()}}
open({str(record)!r}, "w").write(json.dumps(data))
print("FAKE CLAUDE OUTPUT")
sys.exit(7)
""",
    )

    class FakeClaude:
        path = script

        @staticmethod
        def call() -> dict | None:
            return json.loads(record.read_text()) if record.exists() else None

    return FakeClaude


# --------------------------------------------------------------------------- #
# Fake OpenAI-compatible server (stands in for mlx_lm.server)
# --------------------------------------------------------------------------- #
class FakeLLMServer:
    def __init__(self) -> None:
        self.requests: list[dict] = []
        self.status = 200
        self.response: object = {"choices": [{"message": {"role": "assistant", "content": "hello from local"}}]}
        self.raw_body: bytes | None = None

        outer = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *a):  # keep pytest output quiet
                pass

            def _reply(self, status: int, body: bytes) -> None:
                self.send_response(status)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def do_GET(self):
                outer.requests.append({"method": "GET", "path": self.path})
                self._reply(200, b'{"data": []}')

            def do_POST(self):
                length = int(self.headers.get("Content-Length", 0))
                raw = self.rfile.read(length)
                outer.requests.append(
                    {
                        "method": "POST",
                        "path": self.path,
                        "headers": dict(self.headers),
                        "json": json.loads(raw),
                    }
                )
                body = outer.raw_body if outer.raw_body is not None else json.dumps(outer.response).encode()
                self._reply(outer.status, body)

        self.httpd = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.port = self.httpd.server_address[1]
        self.thread = threading.Thread(target=self.httpd.serve_forever, kwargs={"poll_interval": 0.05}, daemon=True)

    @property
    def url(self) -> str:
        return f"http://127.0.0.1:{self.port}/v1/chat/completions"

    def __enter__(self):
        self.thread.start()
        return self

    def __exit__(self, *exc):
        self.httpd.shutdown()
        self.httpd.server_close()


@pytest.fixture
def llm_server():
    with FakeLLMServer() as srv:
        yield srv


@pytest.fixture
def free_port() -> int:
    """A port with nothing listening on it (bound then released)."""
    import socket

    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


# --------------------------------------------------------------------------- #
# Runners
# --------------------------------------------------------------------------- #
@pytest.fixture
def run_agent(base_env):
    def _run(*args: str, env: dict | None = None, stdin: str | None = "", timeout: float = 30):
        e = dict(base_env)
        e.update(env or {})
        return subprocess.run(
            [sys.executable, str(AGENT_LLM), *args],
            input=stdin,
            capture_output=True,
            text=True,
            env=e,
            timeout=timeout,
        )

    return _run


class FakeMacTools:
    """Fake `launchctl`, `curl` and `sleep` for llm-failover.

    * curl succeeds (server "up") once it has been called `up_after` times;
      `up_after=None` means never. `up_after=0` means already up.
    * launchctl logs every call; `launchctl list` prints the label when loaded.
    * sleep returns immediately so the 180 s wait loop runs in milliseconds.
    """

    def __init__(self, root: Path) -> None:
        self.bin = root / "fakebin"
        self.bin.mkdir()
        self.state = root / "fakestate"
        self.state.mkdir()
        self.launchctl_log = self.state / "launchctl.log"
        self.curl_log = self.state / "curl.log"
        self.notify_log = self.state / "notify.log"
        self.up_after: int | None = None
        self.loaded_label: str | None = None

        write_exe(
            self.bin / "launchctl",
            f"""#!/bin/sh
echo "$*" >> "{self.launchctl_log}"
if [ "$1" = "list" ] && [ -f "{self.state}/loaded" ]; then
  printf -- '-\\t0\\t%s\\n' "$(cat "{self.state}/loaded")"
fi
exit 0
""",
        )
        write_exe(
            self.bin / "curl",
            f"""#!/bin/sh
echo "$*" >> "{self.curl_log}"
[ -f "{self.state}/up_after" ] || exit 7
n=$(wc -l < "{self.curl_log}")
[ "$n" -gt "$(cat "{self.state}/up_after")" ] && exit 0
exit 7
""",
        )
        write_exe(self.bin / "sleep", "#!/bin/sh\nexit 0\n")
        self.notify = write_exe(
            self.bin / "fake-notify",
            f"""#!/bin/sh
echo "$@" >> "{self.notify_log}"
""",
        )

    def _sync(self) -> None:
        up = self.state / "up_after"
        if self.up_after is None:
            up.unlink(missing_ok=True)
        else:
            up.write_text(str(self.up_after))
        loaded = self.state / "loaded"
        if self.loaded_label is None:
            loaded.unlink(missing_ok=True)
        else:
            loaded.write_text(self.loaded_label)

    @staticmethod
    def _lines(p: Path) -> list[str]:
        return p.read_text().splitlines() if p.exists() else []

    @property
    def launchctl_calls(self) -> list[str]:
        return self._lines(self.launchctl_log)

    @property
    def curl_calls(self) -> list[str]:
        return self._lines(self.curl_log)

    @property
    def notifications(self) -> list[str]:
        return self._lines(self.notify_log)


@pytest.fixture
def mac(tmp_path: Path) -> FakeMacTools:
    return FakeMacTools(tmp_path)


@pytest.fixture
def plist(home: Path) -> Path:
    """Install the example plist at the path llm-failover expects by default."""
    p = home / "Library" / "LaunchAgents" / "com.local.mlxserver.plist"
    p.parent.mkdir(parents=True)
    shutil.copy(PLIST_EXAMPLE, p)
    return p


@pytest.fixture
def run_failover(base_env, mac: FakeMacTools):
    def _run(*args: str, env: dict | None = None, fake_tools: bool = True, timeout: float = 30):
        e = dict(base_env)
        if fake_tools:
            mac._sync()
            e["PATH"] = f"{mac.bin}{os.pathsep}{e['PATH']}"
        e.update(env or {})
        return subprocess.run(
            ["bash", str(LLM_FAILOVER), *args],
            capture_output=True,
            text=True,
            env=e,
            timeout=timeout,
        )

    return _run
