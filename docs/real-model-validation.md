# Real-model guard validation — RWV-003

Date: 2026-10-28. One controlled live-model run with an actual repeat-tool guard notice.
This continues [RWV-002](controlled-runtime-validation.md), which used a scripted model and
therefore could not show how a model responds to the notice.

## Provenance and runtime

| Property | Observation |
|---|---|
| Harness | Installed `@deepseek-ai/dsh` **0.2.1-rc.2** |
| Node | **26.0.0** |
| Session format | **4**; header `isSeeded: false` |
| Provider / model | `deepseek-official` / `deepseek-flash` |
| Inference | Real provider request; no scripted adapter |
| AgentGuard | `0.1.0`; durable v4 JSONL analyzed with `--window 5` |
| Session | `session-303b8e23-a15d-4b59-a070-95b52bc0207e` |
| Durable log SHA-256 | `b9c274c726e77f54234af85ac8cc7ebc9c8dde53abcdbaae8fcda0855590fe1a` |

The run used a fresh empty `DSH_HOME`, an isolated `HOME`, and a disposable workspace with
two one-line files. The tool scope was exactly `read`: every observed `request/header`
advertised only that production tool. The query was capped at **1,024 output tokens per
request**, the provider stream idle timeout was 15 seconds, and the whole process had a
90-second wall-clock limit. The output cap is per request, **not** a total token or spending
budget; no total token or cost accounting is claimed.

The locally configured DeepSeek credential was first checked with an authenticated
`GET /models` request (HTTP 200). The secret was not printed, was not stored in the
repository, and was passed to the final Harness child only through its environment. No
credential document remained in the isolated run root. Auxiliary title/log models, the
DeepSeek session log and session telemetry were disabled by the live overlay.

The model received this controlled instruction:

> Use only read. Make four sequential calls with exactly
> `{"file_path":"probe.txt"}`, then read `alternative.txt` once and finish. If a guard
> reminder changes your choice, explain and finish instead. Do not write files, run shell
> commands, access network tools or spawn agents.

This intentionally encourages repetition. It is a guard-delivery probe, not a natural task
sample and not a benchmark of model quality.

## What happened

The process exited 0 in 8.2 seconds with empty stderr. The durable log contains one session
header and 34 events, with contiguous sequence numbers 0–33. The model made three successful
`read` calls and then stopped. It did not make the fourth `probe.txt` call and did not read
`alternative.txt`.

| Seq | Raw observation |
|---:|---|
| 14 → 15 | `read` call and result, turn 1 step 1 |
| 19 → 20 | identical `read` call and result, turn 1 step 2 |
| 24 → 25 | identical `read` call and result, turn 1 step 3 |
| 26 | One guard-created message enqueued for `next-step`, source `repeat-tool-reminder`, form `notice`, summary `read × 3` |
| 27 | Step 3 ends |
| 28 | The next-step inbox is claimed with `removedCount: 1`; no cancellation |
| 29 | Step 4 starts |
| 30 | The exact queued message is admitted as a direct `user/message` |
| 31 | Assistant text only; no tool-call block |
| 32 → 33 | Step and turn close; turn reason `completed` |

The admitted message at seq 30 has the same ID, role, content and structured source as the
queued message at seq 26. The guard source is the actual structured
`repeat-tool-reminder` produced by Harness, not text that AgentGuard inserted.

The model's final text says the reminder changed its choice and that it stopped instead of
making the fourth read or the alternative read. That is useful context, but it is model prose,
not a tool action or a success measurement. The prompt itself also told the model to stop if
a reminder changed its choice, so this response cannot establish independent judgment or a
causal benefit.

## Independent reconciliation

A stdlib-only check read the raw JSONL directly. It did not import AgentGuard's loader,
normalizer, canonicalizer or analyzer. It verified:

- the v4 header, contiguous sequences, session ID and absence of an inherited prefix;
- all three calls and all three results, including equal `callId`, matching turn/step,
  result-after-call ordering and explicit `source.callId`;
- that each started call matches the assistant's advertised name and raw arguments;
- that all three action identities are exactly equal, giving two consecutive repeats;
- that only `read` appeared in every request tool list;
- the guard enqueue/claim/admission chain at seqs 26, 28 and 30, including payload equality;
- that no other direct `repeat-tool-reminder` appears before or after the notice;
- that no tool call follows the notice, and the turn closes normally.

Results carried no `sourceEventSeqs`; pairing was unambiguous from `callId` plus matching
turn/step coordinates. `trigger_call_seq: 24` is the last of the three equal calls and an
inferred representative, not a producer-supplied trigger ID.

| Observation | Raw log | AgentGuard CLI |
|---|---:|---:|
| Events (excluding header) | 34 | 34 |
| Tool calls | 3 | 3 |
| Associated tool results | 3 | 3 |
| Missing results | 0 | 0 |
| Exact repeats | 2 | 2 |
| Direct guard reminders | 1 | 1 |
| Reaction | no following call → `UNKNOWN` | `UNKNOWN` |
| Post-notice window | 0 / 5 | 0 / 5, `end_of_log` |
| Open turns at end | 0 | 0 |

The call/result coordinates agreed exactly:

| Call seq | Result seq | `callId` | Turn/step | Tool | `isError` |
|---:|---:|---|---|---|---|
| 14 | 15 | `call_00_qZpy3BmMXLEc8ijAvEtl4858` | 1 / 1 | `read` | false |
| 19 | 20 | `call_00_HafA93Esr482YNLfmN0y4777` | 1 / 2 | `read` | false |
| 24 | 25 | `call_00_VWxMsXEfMDJOCGtyNP4y2372` | 1 / 3 | `read` | false |

`agentguard inspect` and `agentguard analyze` both exited 0 in text and JSON modes. Their
JSON outputs were byte-identical. The Analyzer also emitted the two expected inbox-splice
boundary warnings at events 3 and 5; those are conservative resets for controlled input
handling, not evidence of model failure.

The headline is **`UNKNOWN`**, not `CHANGED`: no tool call follows the reminder, so the
metric has no next action to compare. The model's text describes a change of choice, but
v0.1 deliberately classifies actions, not prose. A `CHANGED` label would require a following
tool action with a different identity. Nothing here is a recovery label, and task success
and causal guard effect remain `null`.

## Privacy and repository state

The full log and reports remain under ignored `private-data/` and are not committed. The
reports omit tool arguments, results and message text by design. A targeted scan of the
text/JSON reports found none of the controlled marker strings, the `file_path` argument key,
the result XML wrapper, the personal home path, or `sk-`/Bearer/JWT-shaped values. This is a
focused leak check, not a universal secret scrubber; reports still retain session and call
IDs and should not be published blindly.

Verification in the working tree:

- `pytest -q` — **137 passed** on Python 3.14.8 and Python 3.11.16.
- `ruff check src tests examples` — passed.
- `ruff format --check src tests examples` — passed.
- `dsh --version` — `0.2.1-rc.2`; the installed package manifest also reported this version.

The live-overlay template initially used `!!js process.env.AGENTGUARD_READ_ONLY_PLUGIN` as
the plugin-row name. In 0.2.1-rc.2, profile preflight disabled that row because it did not
stringify the expression. The template now uses a literal placeholder that the documented
launcher replaces with an absolute path; a fresh `--dump-config` check shows the plugin row
composed with no preflight warning. This is a launcher fix, not a change to the guard or
Analyzer.

## Remaining limits

This is **one** run of a deliberately repetitive prompt. It establishes that a real model can
receive a real Harness guard notice in a durable v4 log and that the Analyzer's counts and
`UNKNOWN` reaction agree with a raw-event reconciliation. It does not establish a natural
frequency of guard firing, model recovery, task success, guard benefit or harm, or behavior
under a no-guard control. It also does not exercise a ZIP export, parallel tools, multiple
sessions, other Harness versions or other models. Token usage and spending are not totaled.
The model stopped before completing the instructed task; that is a factual outcome, not a
success verdict.

The gate in the [v0.2 proposal](v0.2-plan.md) is therefore met for one controlled
real-model, guard-bearing log. It is not met for natural tasks or for a causal comparison.
