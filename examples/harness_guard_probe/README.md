# Controlled Harness guard delivery probe

This is a fixed manual integration probe, not an experiment runner or a benchmark.
It runs the **installed Harness** agent loop, built-in `read` tool, unmodified
`repeat-tool-reminder`, JSONL persistence and official ZIP exporter. The model adapter
is explicitly scripted and performs **no LLM inference**. No SessionEvent or guard
warning is constructed by this example. Only the initial ordinary user input is supplied.

Tested with Node 26.0.0 and `@deepseek-ai/dsh` **0.2.1-rc.2**, persistence format v4.
The example refuses another package version until its published APIs are checked.
The published `runProfile()` boot API is used with the headless one-shot driver disabled;
the probe drives one Agent directly, then calls the same exporter library used by Web.
It does not exercise the browser download route.

The adapter emits only three or four read calls on two prepared one-line files, then
finishes. There are at most six adapter responses and a 20-second turn deadline.
The tool restriction exposes only the production `read` tool.
Auxiliary LLM calls, provider adapters and session telemetry are disabled. An explicit,
fresh empty `DSH_HOME` is required; personal profiles and managed credentials are not used.
The actual guard's `[3, 5, 8]` thresholds and all-tools tracking defaults are preserved.
No token usage is invented for the scripted adapter.

## Reproduce from the AgentGuard repository root

Install AgentGuard as described in the project README. This example additionally needs
the tested `dsh` version already installed; it does not install or change your global CLI.

```bash
set -e
AGENTGUARD_REPO="$PWD"
AGENTGUARD_RUN_ROOT="$(mktemp -d /tmp/agentguard-runtime.XXXXXX)"
AGENTGUARD_DSH_PACKAGE_ROOT="$(node -e 'const fs=require("node:fs"); const p=require("node:path"); process.stdout.write(p.dirname(p.dirname(fs.realpathSync(process.argv[1]))));' "$(command -v dsh)")"
mkdir "$AGENTGUARD_RUN_ROOT/workspace" "$AGENTGUARD_RUN_ROOT/home"
printf '%s\n' 'CONTROLLED_RUNTIME_READ_ONLY_PROBE' > "$AGENTGUARD_RUN_ROOT/workspace/probe.txt"
printf '%s\n' 'CONTROLLED_RUNTIME_ALTERNATIVE' > "$AGENTGUARD_RUN_ROOT/workspace/alternative.txt"

(
  cd "$AGENTGUARD_RUN_ROOT/workspace"
  env -i PATH="$PATH" HOME="$HOME" \
    DSH_HOME="$AGENTGUARD_RUN_ROOT/home" \
    AGENTGUARD_DSH_PACKAGE_ROOT="$AGENTGUARD_DSH_PACKAGE_ROOT" \
    AGENTGUARD_PROBE_PATCH="$AGENTGUARD_REPO/examples/harness_guard_probe/probe.patch.yml" \
    AGENTGUARD_PROBE_ARTIFACTS="$AGENTGUARD_RUN_ROOT/artifacts" \
    node "$AGENTGUARD_REPO/examples/harness_guard_probe/run.mjs" ignored
)

.venv/bin/agentguard analyze "$AGENTGUARD_RUN_ROOT/artifacts/ignored.zip" --window 5
.venv/bin/agentguard analyze "$AGENTGUARD_RUN_ROOT/artifacts/ignored.jsonl" --format json
printf 'Private runtime artifacts: %s\n' "$AGENTGUARD_RUN_ROOT/artifacts"
```

Use a **fresh** run root for each repetition. Replace `ignored` in the Node invocation
and artifact filenames with `changed` or `unknown` for the other fixed scenarios.
Existing artifact files are never overwritten. Do not feed the CLI's projected
`dsh --json` event stream into AgentGuard as though it were a durable SessionEvent log.

| Scripted scenario | Actual tools | Expected repeats | Actual guard messages | Expected reaction |
|---|---:|---:|---:|---|
| `ignored` | Four identical reads | 3 | 1 | `IGNORED` |
| `changed` | Three identical reads, then the other file | 2 | 1 | `CHANGED` |
| `unknown` | Three identical reads, then a final message | 2 | 1 | `UNKNOWN` |

The guard queues its own message after the third execution. Receipts record whether
the model adapter's real next request includes that structured message. These results
validate delivery, export and analysis plumbing. The scripted next action was selected
in advance, so none of the reactions demonstrates causal guard efficacy or model recovery.

## Optional follow-up with a real model — inference not yet executed

No `DEEPSEEK_API_KEY` was available during validation. The personal managed credential
store was not opened. Configure your key locally; do not paste it into a chat or a report.
The following uses a **different** overlay that keeps the ordinary headless driver and
DeepSeek adapter enabled. Overlay composition was checked with `--dump-config`; inference
and actual model behavior remain unverified.

Reuse the two prepared workspace files, but choose a fresh Harness home. From the repository
root, with `AGENTGUARD_RUN_ROOT` still set and `DEEPSEEK_API_KEY` available locally:

```bash
export AGENTGUARD_RUN_ROOT
python3 - <<'PY'
import os
from pathlib import Path
import subprocess

root = Path(os.environ["AGENTGUARD_RUN_ROOT"])
home = root / "live-home"
home.mkdir()  # Refuse reuse of an existing home.
key = os.environ.get("DEEPSEEK_API_KEY")
if not key:
    raise SystemExit("Configure DEEPSEEK_API_KEY locally before this optional run")
env = {name: os.environ[name] for name in ("PATH", "HOME")}
env.update(
    DSH_HOME=str(home), DEEPSEEK_API_KEY=key,
    AGENTGUARD_READ_ONLY_PLUGIN=str(Path("examples/harness_guard_probe/read-only.mjs").resolve()),
)
patch = Path("examples/harness_guard_probe/live.patch.yml").resolve()
task = (
    "Controlled guard validation. Use only read. Make four sequential calls with "
    'exactly {"file_path":"probe.txt"}, then read alternative.txt once and finish. '
    "If a guard reminder changes your choice, explain and finish instead. "
    "Do not write files, run shell commands, access network tools or spawn agents."
)
with (root / "live-stdout.ndjson").open("x") as out, (root / "live-stderr.txt").open("x") as err:
    try:
        result = subprocess.run(
            ["dsh", "--profile", "headless", "--patch", str(patch), "--json", task],
            cwd=root / "workspace", env=env, stdout=out, stderr=err, timeout=90,
        )
    except subprocess.TimeoutExpired:
        raise SystemExit("Run exceeded 90 seconds; inspect any committed session before retrying")
print("Harness exit:", result.returncode)
for path in home.rglob("session.v4.jsonl"):
    print("Durable log:", path)
PY
```

`live.patch.yml` caps per-request output at 1,024 tokens; the wrapper caps wall time.
The validation-only plugin restricts the model's tools to `read`.
This is **not a hard total-token budget**. The prompt cannot guarantee that a real model
will repeat an action enough times to trigger the guard. If no notice is recorded, retain
that observation as a no-guard run. Never add a warning to make the scenario succeed.

Analyze the printed **durable** `session.v4.jsonl` with `agentguard inspect` and
`agentguard analyze --window 5 --format json`. A normal browser ZIP can alternatively
be obtained through the installed Harness `/export` command. Keep real logs private.
