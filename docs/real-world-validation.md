# Real-world validation — RWV-001

Validation date: 2026-10-25. Scope: an actual user-provided DeepSeek Harness ZIP export.
This is a compatibility check **without an observed guard reminder**, not a recovery
experiment. No research definition, threshold or v0.1 feature was changed.

## Input and provenance

| Property | Observation |
|---|---|
| Archive | One privately supplied ZIP; original name/path and session ID omitted here |
| ZIP bytes | 500,053 |
| ZIP SHA-256 | `c23cd645d7d96921857db739e94314f687eb57ffcee32649b6b7de1979e2177e` |
| Members | One `session.v4.jsonl`; DEFLATE compression |
| JSONL bytes | 1,971,787 |
| JSONL SHA-256 | `bdf300d10dfa6e434a3899ab5933ddc6a008fa63f6dd900dcdac039b468a153f` |
| Encoding | UTF-8; every nonempty line parsed as JSON |
| Session format | **4**, as recorded by the export header |
| Seeded / inherited prefix | `isSeeded: false`; no inherited prefix |
| Actual exporter Harness package/build version | **Unknown**; not identified by this archive |
| Inspected reference Harness | Commit `22ddee3792402c3e70ec5f86a63c3e3e895a2f60`; session package `0.2.1-rc.3` |
| Analyzer | AgentGuard Bench `0.1.0`; committed baseline `ffea3e6` |

The reference package version is **not** attributed to the exporter. Format version 4
alone cannot identify the exact Harness build that produced the session. A fresh fetch
of official `master` still resolved to the reference commit above.

The archive CRC was verified. The original archive SHA-256 was checked again after
validation and remained unchanged. A byte-identical JSONL member was written only to a
private temporary directory outside this repository. The source ZIP, JSONL, CLI reports
and intermediate inspection data were not added to Git or sent to an external service.

The working tree already contained local normalization, test and documentation edits
before validation. They were preserved. To distinguish their effect, the committed
`ffea3e6` tree was exported to a separate temporary directory and all four ZIP CLI modes
were rerun against it. Its text/JSON reports were byte-identical to the working-tree
reports. No analyzer code fix was needed for this sample.

## Event structure and contract checks

The first record is a session header. Its field names are `type`, `version`, `id`,
`createdAt`, `cwd`, `isSeeded`, `delegationDepth` and `agentPreset`. Private values are
omitted here. It is followed by **425 events**, with contiguous seq values **0–424**.
All event types belong to the 62-name inspected Harness vocabulary. Event timestamps
are integer values; interpreted payloads have the expected object shapes.

| Event type | Count |
|---|---:|
| `permission/preset` | 1 |
| `sandbox/mode` | 1 |
| `approval/policy` | 1 |
| `agent/inbox/spliced` | 2 |
| `turn/start` | 1 |
| `step/start` | 46 |
| `system/message` | 2 |
| `user/message` | 5 |
| `request/header` | 2 |
| `request/context` | 1 |
| `session/title` | 2 |
| `session/title-llm-request` | 1 |
| `session-log-deepseek/delivery-accepted` | 47 |
| `assistant/message` | 46 |
| `tool/call` | 70 |
| `job/registered` | 38 |
| `job/settled` | 38 |
| `tool/result` | 70 |
| `step/end` | 46 |
| `developer/message` | 1 |
| `workspace/changes` | 1 |
| `turn/end` | 1 |
| `command/run` | 1 |
| `command/done` | 1 |

The one observed turn and all 46 steps close. Tool starts occur in 45 steps; 24 steps
contain multiple tool starts. Peak simultaneously unanswered started calls is three.
There are no descendant logs, attachments, inherited prefixes or result surface
replacements in this archive.

The shapes were checked against official
[SessionEvent types](https://github.com/deepseek-ai/deepseek-harness/blob/22ddee3792402c3e70ec5f86a63c3e3e895a2f60/packages/core/session/src/types.ts),
[message types](https://github.com/deepseek-ai/deepseek-harness/blob/22ddee3792402c3e70ec5f86a63c3e3e895a2f60/packages/llm/llm/src/message.ts),
[tool batch writer](https://github.com/deepseek-ai/deepseek-harness/blob/22ddee3792402c3e70ec5f86a63c3e3e895a2f60/packages/core/tools/src/batch.ts),
and [ZIP exporter](https://github.com/deepseek-ai/deepseek-harness/blob/22ddee3792402c3e70ec5f86a63c3e3e895a2f60/packages/session-query/session-log-export/src/archive.ts).
This is a focused contract check; the full upstream TypeScript validator was not run.

## Independent pairing and metric verification

A separate stdlib-only inspection read the raw ZIP/JSONL. It did not import AgentGuard's
loader, normalizer, analyzer or canonicalizer. It reconstructed active turn/step markers,
assistant tool advertisements, starts and results directly from the original records.

For **every one of the 70 pairs**, it checked:

1. Call `data.callId` equals result `data.message.toolCallId` and `source.callId`.
2. Known call/result turn and step coordinates agree and match the open lifecycle.
3. The result appears after its call, with no duplicate association or orphan result.
4. Result `sourceEventSeqs` equals the started call's sequence reference.
5. The started tool name and raw argument string match the assistant's advertised call.
6. Analyzer `result_seq`, call coordinates, ID and explicit error flag match raw records.

There are **70 distinct call IDs**. ID reuse across steps is not exercised by this sample.
**53 of 70 results are nonadjacent to their calls.** Thus association could not be
validated by assuming neighboring records.

Selected source references, without tool arguments or result bodies:

| Turn | Step | Call seq | Result seq |
|---:|---:|---:|---:|
| 1 | 1 | 20 | 23 |
| 1 | 1 | 24 | 27 |
| 1 | 3 | 40 | 43 |
| 1 | 3 | 41 | 44 |
| 1 | 3 | 42 | 45 |
| 1 | 45 | 412 | 415 |

Step 3 records three starts before their results. Pairing 42 with 43 by adjacency would
be incorrect: the proper associations are 40→43, 41→44 and 42→45. All multi-call batches
in this sample settle in call order; reversed completion order remains untested here.

An independent type-tagged JSON comparison oracle checked consecutive action identity
and the existing boundary rules. Numeric spelling, object-key order, arrays and raw
fallback follow the published v0.1 definitions; no new threshold was introduced.
It found **zero exact repetition pairs**, matching Analyzer. This validates a real
negative example, not positive detection of repetitive behavior.

| Observation | Independent inspection | Analyzer |
|---|---:|---:|
| Sessions | 1 | 1 |
| Events, excluding header | 425 | 425 |
| Observed tool starts | 70 | 70 |
| Associated tool results | 70 | 70 linked records |
| Missing results | 0 | 0 |
| Exact repeats | 0 | 0 |
| Direct guard reminders | 0 | 0 |
| IGNORED / CHANGED / UNKNOWN reminders | 0 / 0 / 0 | 0 / 0 / 0 |
| Open turns at end | 0 | Empty list |

Of the matched results, 68 explicitly record `isError: false` and two record
`isError: true` (result seq 323 and 325). These are preserved tool flags, not task-success
or usefulness verdicts. Task success, recovery and guard causal effect remain null.

The two warnings at seq 3 and 5 correspond to actual inbox-splice boundaries. They are
expected conservative resets, not corruption warnings or detected agent errors.

## Guard coverage

Direct `user/message` producer counts are:

| `data.source.kind` | Count |
|---|---:|
| `user` | 1 |
| `runtime-context` | 2 |
| `skill-catalog` | 1 |
| `time-context` | 1 |
| `repeat-tool-reminder` | **0** |

The inserted messages of both `agent/inbox/spliced` events were separately checked for
structured reminder provenance; none had the guard kind either. Arbitrary text mentions
were not used to infer firing.

Therefore there is no reminder incident to reconstruct before/after. No synthetic
warning was inserted into the original log or an altered copy. Zero warnings does not
establish whether the guard was installed, enabled, excluded these tools or simply never
reached a trigger condition. Post-reminder classification and recovery remain unvalidated
by this real sample.

## CLI, privacy and test execution

All four ZIP modes completed with exit code 0 and empty stderr:

```bash
agentguard inspect "$AGENTGUARD_PRIVATE_EXPORT" --format text
agentguard inspect "$AGENTGUARD_PRIVATE_EXPORT" --format json
agentguard analyze "$AGENTGUARD_PRIVATE_EXPORT" --format text
agentguard analyze "$AGENTGUARD_PRIVATE_EXPORT" --format json
```

`AGENTGUARD_PRIVATE_EXPORT` denotes the privately supplied archive path. The JSON output
of inspect and analyze was identical. Standalone JSONL analysis also completed with exit
code 0; its report matched ZIP analysis after accounting for the expected source-name
difference. The extracted member bytes themselves were not edited.

Reports were kept in a mode-0700 temporary directory outside Git. A data-minimization
check compared all text/JSON reports and decoded JSON report strings against **921 distinct
payload strings of at least 40 characters**, collected from tool arguments/results,
tool-private metadata, error payloads and user/source content. None appeared in reports.
The checked credential-shaped patterns (OpenAI-style keys, AWS IDs, Google API keys and
JWTs) were absent from report output as well. No matched private value was printed.

This is evidence of payload exclusion for this input, not a universal secret scrubber.
Short or unrecognized secrets embedded in retained metadata cannot be ruled out by
those checks alone. Reports retain session/call IDs, tool names and relative source
names, so complete reports are not committed or presented as automatically shareable.

Verification on Python 3.14.8:

- Preserved current working tree: `pytest -q` — **113 passed**.
- Clean committed baseline `ffea3e6`: `pytest -q` — **110 passed**.
- `ruff check src tests examples` — passed.
- `ruff format --check src tests examples` — passed.

The difference in test counts comes from three pre-existing local tests, not additions
made during this validation. No discrepancy was found requiring a new regression or
code change. If a later real sample reveals one, the regression-before-fix rule remains.

## Confirmed and still open

**Confirmed on this one real export:** ZIP admission/CRC and default size budgets,
UTF-8 JSONL parsing, observed v4 envelope/message shapes, lifecycle coordinates, all 70
tool-result associations (including nonadjacent and overlapping starts), explicit error
flag preservation, JSONL/ZIP report agreement, both report formats, expected inbox
boundaries, and zero-repeat/zero-reminder observations matching independent inspection.

**Not confirmed by this sample:** actual guard firing, positive exact-repeat detection,
trigger attribution, IGNORED/CHANGED/UNKNOWN behavior after a real reminder, recovery,
task success, causal effect, multiple real sessions in one archive, descendant/fork
history, real missing results/repair outcomes, reused call IDs, reversed completion order,
attachment handling on real exports, other Harness builds or realistic upper memory limits.

Compatibility is confirmed for the observed subset of this real v4 session. It is not
a blanket guarantee for every v4 export. Continue real-world validation with a separately
obtained guard-bearing export and representative multi-session/interrupted cases before
broadening scope. No v0.2 functionality is implemented by this validation.

## Follow-up — 2026-10-26

[RWV-002](controlled-runtime-validation.md) now checks actual guard delivery and exports
from the installed Harness runtime with an explicitly scripted model. It exposed and
fixed an inbox-handoff analysis bug. This is a separate controlled integration result;
RWV-001 itself still has no guard notice, and natural-model post-reminder behavior remains
unverified. No original user log was changed or supplemented with fabricated events.
