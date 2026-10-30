# AgentGuard command plugin for DeepSeek Harness

This directory contains a **local DSH command plugin**, not a second analyzer and not a
guard plugin. It registers:

```text
/agentguard <session.jsonl|export.zip> [--window N]
```

The command runs the existing offline `agentguard` CLI on a **durable** Harness v4 JSONL
log or official ZIP and returns the same text report. It does not read the live session
automatically, does not inject warnings and does not make network calls.

Tested with `@deepseek-ai/dsh` **0.2.1-rc.2** on Node **26.0.0**. The plugin uses only Node
built-ins, so it has no package dependencies.

## Prerequisites

- DeepSeek Harness `0.2.1-rc.2`.
- AgentGuard installed in a Python 3.11+ environment, with an `agentguard` executable.
- A command-capable profile (`tui` or `web`); the headless one-shot profile has no user
  command UI.

If `agentguard` is not on `PATH`, set an absolute executable before starting DSH:

```bash
export AGENTGUARD_BIN="$PWD/.venv/bin/agentguard"
```

The plugin launches only that executable, with a minimal environment (`PATH`, `HOME`,
`LANG`); it does not pass provider API keys to the child.

## Install as a local plugin

Add a literal absolute module path to the profile patch, for example
`~/.dsh/profiles/tui/cordis.patch.yml`:

```yaml
- insert:
    - id: agentguard-command
      name: /absolute/path/to/AgentGuard-Bench/examples/harness_agentguard_plugin/agentguard.mjs
```

The `name` must be a literal string. In 0.2.1-rc.2, a `!!js process.env...` expression in a
plugin-row `name` is not stringified by profile preflight and the row is disabled. A
per-run `--patch` overlay works the same way. Restart the profile after editing.

## Use

```text
/agentguard /path/to/session.v4.jsonl --window 5
/agentguard "/path/with spaces/export.zip"
```

A relative path resolves against the session's `cwd`. The command accepts `.jsonl` and
`.zip` only, requires a readable regular file, and reports usage, missing-file and
window errors as command errors. `--window` defaults to 5 and is bounded to 1–1000.

The output is the safe text report: counts, session IDs, call/result coordinates and
guard-reminder observations, without tool arguments, tool results or message text.

## Smoke test

From the repository root, with the tested `dsh` installed and AgentGuard's venv present:

```bash
export AGENTGUARD_DSH_PACKAGE_ROOT="$(node -e 'const fs=require("node:fs"); const p=require("node:path"); process.stdout.write(p.dirname(p.dirname(fs.realpathSync(process.argv[1]))));' "$(command -v dsh)")"
node examples/harness_agentguard_plugin/test-command.mjs
```

The test boots the real installed Harness with the one-shot driver disabled and a no-op
model adapter, creates one Agent, and executes the real command registry. It checks:

- analysis of `examples/synthetic-session.jsonl` returns the expected counts and
  `Guard seq 20: IGNORED`;
- a quoted path containing spaces works;
- quoted POSIX paths preserve literal backslashes and support escaped double quotes;
- a relative path resolves against the session `cwd`;
- missing files, an invalid `--window`, and no arguments return errors.

No model inference occurs.

## Limits

- This is a command wrapper around the offline analyzer, not a live session observer. To
  analyze the current session, export its durable log/ZIP first.
- It is a local module, not an npm package or a plugin-manager entry.
- It does not implement an A/B runner, guard enable/disable, or task-success/recovery
  labels.
- The user chooses the path to analyze. Run it only in a trusted local DSH profile; it can
  read any `.jsonl`/`.zip` file the DSH process can read.
- The plugin API is pinned to the tested release. Check `--dump-config` after upgrading.
