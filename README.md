# AgentGuard Bench

A reproducible evaluation and behavioral analysis toolkit for AI agent guard mechanisms.

**v0.1 implements an offline session analyzer for DeepSeek Harness format v4.** It finds
consecutive identical tool calls, detects structured `repeat-tool-reminder` messages,
and records what the agent does next. It uses only the Python standard library at runtime.

The research question is: **Does a guard help an agent recover from repetitive behavior,
or does it merely cause the agent to change its actions?** This release supplies behavioral
observations for that question. It does not measure recovery or causal effectiveness.

## Install

Python 3.11 or newer:

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -e '.[dev]'
agentguard --version
```

For runtime use alone, install with `python -m pip install .`.

## Use

```bash
agentguard inspect examples/synthetic-session.jsonl
agentguard analyze examples/synthetic-session.jsonl --window 5
agentguard inspect private-data/export.zip
agentguard analyze private-data/export.zip --window 5 --format json > report.json
python -m agentguard analyze examples/synthetic-session.jsonl
```

`inspect` provides an evidence summary; `analyze` also lists individual calls and their
result associations. Both support the same complete JSON report. `--window` must be positive.
Exit codes: `0` means analysis completed, **not** that the agent succeeded; `2` means
invalid, unsupported, inaccessible, or oversized input. Errors go to stderr, reports to stdout.

Accepts one UTF-8 `.jsonl` file, or a Harness `.zip` export containing multiple separate
session logs. The header supplies the session ID; the file supplies provenance.
Multiple headers in one file, duplicate session IDs, unsupported versions, sequence gaps,
and unknown required event types are refused. There is no network access during analysis.
Tool IDs may recur in different steps; pairing uses call IDs, turn/step coordinates and
available `sourceEventSeqs`, rather than assuming session-global ID uniqueness.

Current Harness exports use `session.v4.jsonl` and
`subagents/<id>/session.v4.jsonl`. Attachment trees `files/` and `media/` are never parsed
as session logs, including uploaded JSONL attachments. ZIP members are never extracted.

### What a finding means

- **Repeated call:** the next tool invocation has the same tool name and canonical
  arguments. A new human prompt or an unsupported behavioral boundary resets the chain.
  Returning to an earlier action after a different tool call does not count as consecutive.
- **Possible loop:** an explicitly unvalidated heuristic, starting at three consecutive
  identical calls. It does not establish that those calls were unnecessary.
- **Verified lack of progress:** unknown (`null`). Requires an independent task criterion.
- **Guard reminder:** `user/message.data.source.kind == "repeat-tool-reminder"`.
  Quoted reminder text in arguments or user prompts does not count.
- **IGNORED / CHANGED:** a preliminary comparison of the first subsequent call with the
  inferred preceding action. Each later call in the window also receives its own comparison.
- **UNKNOWN:** no following call, incomplete identities, interrupted observation boundary,
  or ambiguous preceding context. Finishing without another tool call is also unknown.

`CHANGED` does not mean `RECOVERED`. `isError: false` does not prove task success.
`trigger_call_seq` is an inferred representative call, **not an upstream trigger ID**.
Attribution requires an unambiguous completed previous tool step with one action identity
and an observed repetition. See [the exact rules and limitations](docs/limitations.md).

The window ends at K calls, the next reminder, a new user prompt, an unsupported behavioral
boundary, or the end of the log. A short window is explicitly marked incomplete; a reaction
can still be known from its first call. Calls can span turns if there is no intervening prompt.

### Example result

All committed JSONL examples and fixtures are **synthetic**, constructed from the inspected v4
contract. They are not user sessions and do not demonstrate guard effectiveness.

```text
Sessions: 1 | Events: 31 (inherited: 0)
Tool calls: 5 | Exact repeats: 3 | Guard reminders: 1
Missing tool results: 0
Reactions: IGNORED=1, CHANGED=0, UNKNOWN=0
Guard seq 20: IGNORED | trigger=16 (inferred_unique_previous_step)
Following calls: seq 22 = IGNORED, seq 27 = CHANGED
```

Full generated reports: [text](examples/synthetic-report.txt) and
[JSON](examples/synthetic-report.json). Generate a synthetic multi-session ZIP for local checks:

```bash
python examples/make_synthetic_zip.py /tmp/agentguard-synthetic.zip
agentguard analyze /tmp/agentguard-synthetic.zip --format json
```

### Data handling

Reports omit tool arguments, result payloads, message text, internal error details, and
guard source summaries. Comparisons use session-local `action_0001` labels, with no
argument hashes or previews. Raw payloads exist in memory for analysis. Session IDs,
tool names, call IDs, parent IDs and relative source names remain in reports: review
those metadata before sharing. Terminal controls are escaped. There is no raw-output flag.

Keep real exports under ignored `private-data/`; do not commit real logs without explicit
authorization. Ignore rules cannot prevent a deliberate `git add -f`.

Default limits:

| Resource | Limit |
|---|---:|
| Input file / each decoded log | 64 MiB |
| Total declared uncompressed ZIP bytes, including attachments | 128 MiB |
| Line | 2 MiB |
| ZIP members | 2,048 |
| Sessions | 256 |
| Events across sessions | 200,000 |
| Per-member uncompressed/compressed ratio | 200 |

`--max-input-mib` and `--max-total-mib` override the byte budgets. The Python API accepts a
`Limits` instance for all limits. Highly compressible legitimate exports can be refused;
limits are safety policy, not a claim that such data is corrupt.

## Development

```bash
pytest -q
ruff check src tests
ruff format --check src tests
```

Coverage includes parsing failures, multi-session ZIPs, hostile paths, size limits, pairing
nonadjacent results, repetition canonicalization, structured reminders, ambiguous contexts,
interrupted sessions, inherited history, optional/missing fields and safe CLI output.

Compatibility was researched against Harness commit
[`22ddee3792402c3e70ec5f86a63c3e3e895a2f60`](https://github.com/deepseek-ai/deepseek-harness/tree/22ddee3792402c3e70ec5f86a63c3e3e895a2f60),
session package `0.2.1-rc.3`, on 2026-10-25. Format v4 is the persistence version,
not the package version. One user-provided guard-free v4 export has been checked, followed
by actual Harness runtime exports with an explicitly scripted model and native guard
delivery. Natural-model behavior after a real reminder remains unverified; this is not
a general compatibility or recovery guarantee.

Read [architecture](docs/architecture.md), [limitations](docs/limitations.md), and
[upstream source findings](docs/harness-contract.md) before interpreting research results.
The [metric definitions](docs/metrics.md) explain each count and classification;
the [v0.1 engineering audit](docs/audit-v0.1.md) records repairs, executed checks and
the remaining real-data verification gate.
See [controlled runtime validation](docs/controlled-runtime-validation.md) and the
[read-only reproduction example](examples/harness_guard_probe/README.md) for the observed
guard handoff, its regression fix and concrete commands. These runs use a scripted model,
not live inference. The [v0.2 proposal](docs/v0.2-plan.md) is conditional and unimplemented.

## Roadmap

- v0.2: richer behavioral patterns, error signatures, manual incident labels, detector evaluation.
- v0.3: reproducible guard ON/OFF experiments, task checks, token efficiency, paired uncertainty.
- v1.0: multiple guards, evaluation suites, comparative reports and Harness integration.

These capabilities are not implemented in v0.1. No dashboard, experiment runner, LLM judge,
active intervention, inference server, telemetry exporter, or plugin framework is included.

License: [MIT](LICENSE).
