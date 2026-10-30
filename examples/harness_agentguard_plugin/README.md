# AgentGuard DSH plugin

A local DeepSeek Harness **bundle plugin** that registers:

```text
/agentguard [session.jsonl|export.zip] [--window N]
```

With no path it snapshots the current Agent session and analyzes that snapshot. With a path
it analyzes a supplied durable Harness v4 JSONL log or official ZIP. Both paths run the
existing offline `agentguard` CLI. The plugin does not inject warnings, alter the native
guard, or make network calls.

Tested with `@deepseek-ai/dsh` **0.2.1-rc.2** on Node **26.0.0**. The plugin itself uses only
Node built-ins; the analyzer is the Python package in this repository.

## Requirements

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

## Install as a bundle

The package is a local DSH bundle: its `package.json` declares
`dsh.bundle.patch: "./cordis.patch.yml"`, and that patch inserts the
`agentguard-command` row. From this directory:

```bash
pnpm pack
dsh plugin --profile tui add "file:/absolute/path/agentguard-dsh-plugin-0.1.0.tgz"
```

The plugin manager adds the dependency, selects `agentguard-dsh-plugin` in
`dsh.profile.bundles`, and applies its bundle patch. Restart the profile after installation.
`dsh --profile tui --dump-config` should show the `agentguard-command` row without a
preflight warning.

For a manual, non-package install, insert a literal module path instead:

```yaml
- insert:
    - id: agentguard-command
      name: /absolute/path/to/agentguard.mjs
```

The `name` must be a literal string. In 0.2.1-rc.2, a `!!js process.env...` expression in a
plugin-row `name` is not stringified by profile preflight and the row is disabled.

## Configure

The bundle works without configuration. Optional fields can be set by overriding the row in
the profile patch:

```yaml
- id: agentguard-command
  config:
    executable: /absolute/path/to/.venv/bin/agentguard
    window: 5
    timeoutMs: 15000
    maxOutputBytes: 2097152
```

`executable` defaults to `AGENTGUARD_BIN`, then `agentguard` on `PATH`. `window` defaults to
5 and must be between 1 and 1000. `timeoutMs` and `maxOutputBytes` must be positive safe
integers. Invalid configuration fails plugin startup rather than silently falling back.

## Use

```text
/agentguard
/agentguard /path/to/session.v4.jsonl --window 5
/agentguard "/path/with spaces/export.zip"
```

- No path: the plugin reads `session.header` and `session.snapshotEvents()`, writes a
  mode-0600 temporary JSONL file, runs the analyzer, and removes the file in `finally`.
- Path: a relative path resolves against the session's `cwd`; the file must be readable and
  end in `.jsonl` or `.zip`.
- Quoted paths support spaces, literal POSIX backslashes and escaped double quotes.
- Usage, missing-file, window and analyzer errors return command errors.

The output is the safe text report: counts, session IDs, call/result coordinates and
guard-reminder observations, without tool arguments, tool results or message text. The
current-session snapshot can include the in-progress `command/run` event; the analyzer
recognizes that v4 event and counts it only as an unrelated event.

## Tests

Unit tests cover the tokenizer, quoted special characters and command parsing:

```bash
node --test test-unit.mjs
```

The end-to-end smoke test boots the installed Harness with the one-shot driver disabled and
a scripted adapter, creates one Agent, performs one real tool turn, then exercises the real
command registry. It checks current-session analysis, external JSONL analysis, quoted paths
with spaces/backslashes/quotes, relative paths, missing files, invalid windows and malformed
input. No provider inference occurs.

Source-tree mode:

```bash
export AGENTGUARD_DSH_PACKAGE_ROOT="$(node -e 'const fs=require("node:fs"); const p=require("node:path"); process.stdout.write(p.dirname(p.dirname(fs.realpathSync(process.argv[1]))));' "$(command -v dsh)")"
node examples/harness_agentguard_plugin/test-command.mjs
```

Installed-bundle mode, after installing the tarball into a headless test profile:

```bash
AGENTGUARD_INSTALLED_DSH_HOME="$PWD/private-data/plugin-install-headless" \
  node examples/harness_agentguard_plugin/test-command.mjs
```

The installed mode loads the package through the profile's `dsh.profile.bundles` rather than
a literal module path.

## Limits

- This is a local, installable bundle package, not a package published to a registry.
- The analyzer remains an external Python dependency; the plugin is not self-contained.
- The current-session path snapshots the live event graph into a temporary file. Large
  sessions increase temporary disk and memory use; the analyzer output remains capped.
- The plugin is pinned to DSH `0.2.1-rc.2` through `engines.dsh`; update the range only after
  checking the plugin API.
- It does not run an A/B experiment, control guard enablement or produce task-success or
  recovery labels.
- The user chooses the path to analyze. Run it only in a trusted local DSH profile; it can
  read any `.jsonl`/`.zip` file the DSH process can read.
