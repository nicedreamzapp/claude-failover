# Contributing

Thanks for taking a look. claude-failover is two small scripts, and most of what can go wrong
depends on your Mac, your local model and your scripts, so a clear bug report is useful even if
you never send code.

## Reporting a problem

Open an [issue](https://github.com/nicedreamzapp/claude-failover/issues/new/choose). The things
that make it quick to fix:

- your Mac (chip and RAM), macOS version and Python version
- the local model and the `mlx-lm` version
- what `llm-failover status` prints
- the exact `agent-llm` command your script ran, and the output or error
- any env vars you changed from the defaults (`LOCAL_LLM_URL`, `LLM_PORT`, `LLM_LAUNCHAGENT` and so on)

## Running it locally

```bash
git clone https://github.com/nicedreamzapp/claude-failover.git
cd claude-failover

mkdir -p ~/.local/bin
cp bin/agent-llm bin/llm-failover ~/.local/bin/
chmod +x ~/.local/bin/agent-llm ~/.local/bin/llm-failover

python3 -m venv ~/.local/share/mlx-server/.venv
~/.local/share/mlx-server/.venv/bin/pip install mlx-lm

cp LaunchAgents/com.example.mlxserver.plist.example ~/Library/LaunchAgents/com.local.mlxserver.plist
# then replace /PATH/TO/VENV in the plist

llm-failover status
llm-failover local
echo "say hello in one word" | agent-llm -p
llm-failover claude
```

## Tests

The suite runs both scripts against a fake `claude`, a loopback server in place of
`mlx_lm.server`, and fake `launchctl`, `curl` and `sleep`, so it runs on Linux with no model and
no network. CI runs it on every push and pull request.

```bash
pip install -r requirements-dev.txt
pytest
```

## Pull requests

Small and focused is easiest to review. For big changes, open an issue first so we can talk it
through. The scripts use only the Python standard library and plain Bash, so please keep it that
way. If you change how a flag or argument is handled, add a test for it.

Please follow the [code of conduct](CODE_OF_CONDUCT.md).
