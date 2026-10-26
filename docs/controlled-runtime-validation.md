# Controlled guard runtime validation — RWV-002

Date: 2026-10-26. This continues [RWV-001](real-world-validation.md), which contained a
real user-provided export without a guard notice.

## Provenance: what is real, and what is scripted

The installed **DeepSeek Harness `0.2.1-rc.2`** was run locally with Node **26.0.0**.
Its agent loop executed the production `read` tool, its unmodified guard produced the
notice, its persistence stored a native **v4** log, and its own export library produced
the ZIP. The driver does not construct SessionEvents or inject a guard warning.

The model is an explicitly named **`agentguard-scripted`** test adapter. Its next actions
are predetermined. No live LLM inference occurred, no API key was supplied, and no
token usage was fabricated. This is a real runtime integration session with synthetic
test inputs and a scripted model, **not a natural-model recovery experiment or a new
user-provided guard-bearing session**.

CLI, session, guard and export package versions were read from installed manifests;
all are `0.2.1-rc.2`. They must not be confused with the earlier reference source
checkout's `0.2.1-rc.3` package version. The test adapter's source and configuration are
committed under [examples/harness_guard_probe](../examples/harness_guard_probe/README.md).
The example pins the tested installed version instead of guessing future APIs.

## Isolation and bounds

- Each final run used a fresh empty `DSH_HOME` and a disposable workspace with two
  one-line marker files. Personal profiles and managed credentials were not opened.
- The inherited environment was restricted to ordinary process/path variables plus
  explicit probe settings. `DEEPSEEK_API_KEY` was absent from the launch environment.
- The tool scope exposed only `read`; every adapter request checked that no other
  tool was advertised. The agent-creation hook uses `agent.ctx.tools.restrict()`.
- External model adapters, auxiliary title/log model calls and session telemetry were
  disabled. The script has a six-response budget and a 20-second turn deadline.
- Guard defaults were retained explicitly: thresholds `[3, 5, 8]`, no tool exclusions,
  and the normal argument-preview limit. There is no new detection threshold.
- The one-shot headless driver was disabled, while the production headless profile
  was booted through its published `runProfile()` API. The probe drove one Agent and
  exported its persisted log through `readSessionLogText()` / `streamSessionLogZip()`.
  The browser HTTP/download route was not exercised in this probe.

The reproduction README's exact keyless commands were executed successfully, with
fail-fast shell handling and a checked model-boundary guard receipt. During preparation,
an attempted context-global restriction was rejected by Harness; the final example
uses the documented agent-scoped creation hook and was rerun successfully for all cases.

## Results from the final read-only runs

All native turns closed, tools returned non-error results, every result paired with
its call, and each model adapter's fourth response observed the real structured notice.

| Fixed scenario | Events | Tool calls / results | Exact repeats | Direct guard notices | Reaction |
|---|---:|---:|---:|---:|---|
| `ignored` | 39 | 4 / 4 | 3 | 1 | `IGNORED` |
| `changed` | 39 | 4 / 4 | 2 | 1 | `CHANGED` |
| `unknown` | 34 | 3 / 3 | 2 | 1 | `UNKNOWN` |

`ignored` reads the same marker four times. `changed` reads it three times and then
reads the alternative marker. `unknown` reads it three times, receives the notice,
and emits a final message without another tool call. All use K=5, so their observation
windows are incomplete (one, one and zero following calls respectively).

All three cases were repeated during preparation with the same counts and classifications;
the original pre-fix `ignored` export was reanalyzed after the fix as well. Event timestamps,
message IDs and ZIP hashes vary between invocations; reproducibility here means the
fixed action sequence, guard delivery and independently reconciled classifications.

Final export SHA-256 values:

| Case | ZIP SHA-256 |
|---|---|
| `ignored` | `ded68d9e6f1c5825340eba0fa7f3286bb8744888ac5a3a3c5f322ab961c9f5ed` |
| `changed` | `4c37e344089c063622ff9eea941bd7eb143eed26d7e96a97eaa1f530cfb695d4` |
| `unknown` | `9d4895122160d06af709264753438111e52f6805e247c4179d7da0c65e5bf5aa` |

Complete JSONL/ZIP exports, receipts, reports and a verification manifest are retained
under ignored `private-data/guard-runtime-20261026-z423143w/`, outside Git history.

## Independent source-event reconstruction

A stdlib-only inspection read the raw exports without importing AgentGuard's parser,
normalizer, canonicalizer or analyzer. It verified CRCs and contiguous sequences,
header version, every call/result ID and turn/step, source references, queued/admitted
message equality and the observed action identities. Analyzer output was compared
against those observations, not simply against the scenario's intended label.

All three final cases share this actual prefix:

| Seq | Observation |
|---:|---|
| 14 → 15 | First `read` call and its result, step 1 |
| 19 → 20 | Second identical call/result, step 2 |
| 24 → 25 | Third identical call/result, step 3 |
| 26 | Guard-created UserMessage enqueued in the next-step inbox |
| 27 | Step 3 ends |
| 28 | Entire next-step inbox claimed; no cancellation |
| 29 | Step 4 starts |
| 30 | The exact queued message is admitted as `user/message` |
| 32 → 33 | Fourth call/result in `ignored` and `changed`; absent in `unknown` |

The admitted source is `kind: repeat-tool-reminder`, `form: notice`, with the native
`read × 3` summary. Queue and admitted message IDs and full payloads match. Receipts
confirm that source in response 4's actual `GenerateOptions.messages`.

Independent string-valued JSON argument comparison found that seq 32 matches seq 24
in `ignored`, differs in `changed`, and does not exist in `unknown`. These observations
match the corresponding Analyzer labels. `trigger_call_seq: 24` remains an **inferred
representative**, not a producer-supplied causal link.

For each case, all four inspect/analyze × text/JSON modes exited zero. Standalone JSONL
and ZIP results matched after the expected source-name adjustment; the JSONL bytes
were identical to the ZIP member. Marker contents appeared in real tool results in
the raw logs but never in the reports. Tool argument objects were absent from reports.
The artifacts contain only controlled inputs, but full logs remain private by default.

## Defect discovered and regression-before-fix

Before the fix, AgentGuard counted all inbox splices as opaque behavior boundaries.
The first real guard handoff therefore reset the repetition chain at seq 26 and 28.
The untouched original `ignored` export incorrectly reported two repeats and an
unattributed `UNKNOWN` reaction despite its fourth identical read.

Three new synthetic reproduction cases failed before implementation. The correction
is in the **normalizer**, not in the reaction classifier or repetition identity:

- Follow only known next-step queue coordinates.
- Accept only guard-only append and full claim with unique message IDs, no cancellation,
  followed by admission of the exact messages in the next entering step before model work.
- Mark that verified enqueue/claim handoff transparent. Count only direct messages as
  reminders, so queue records do not double-count the warning.
- Preserve opaque boundaries for mixed input, cancellation, malformed coordinates,
  duplicates, changed payloads, wrong targets and missing admission.

`tests/test_guard_handoff.py` covers these cases and multiple queued notices. It is
explicitly synthetic regression data derived from the observed protocol, not the
runtime export relabeled as a fixture. No original log was modified to make a test pass.
Fix commit: `d3a6ba7`; reproducible example: `d91f677`.

The full working-tree suite passes **137 tests** on Python **3.14.8** and **3.11.16**.
The isolated fix snapshot excluding three existing local tests passes **134 tests** and
classifies all three runtime exports correctly. Ruff lint and formatting checks pass.
The original RWV-001 ZIP is no longer present at its supplied Downloads path. Its cached
JSONL copy still matches the recorded SHA-256, and reanalysis produces the unchanged
no-guard report after the expected source-name adjustment. A fresh rerun of the original
ZIP itself was therefore unavailable during this follow-up.

## Remaining validation boundary

Confirmed here: an actual installed guard firing, notice delivery across the real
inbox, native persistence/export, positive exact-repeat detection and all three
mechanical response classifications on controlled runtime-generated logs.

Not confirmed: how an actual LLM reacts, recovery or task success, causal benefit,
guard ON/OFF comparison, false-positive rates in natural tasks, mixed/parallel real
guard batches, or compatibility with every Harness release.

The script selected its post-notice action in advance. **CHANGED does not imply
RECOVERED**, and neither completing this integration probe nor a non-error read proves
success on a meaningful user task. All task-success/recovery/causal fields remain null.

No live DeepSeek inference was attempted because no API key was available in the launch
environment. The optional live-model overlay was composed successfully; actual inference
is explicitly unrun. [Concrete follow-up commands](../examples/harness_guard_probe/README.md#optional-follow-up-with-a-real-model--inference-not-yet-executed)
use a fresh home, read-only tool scope, a request output cap and a wall-time limit. If
the model never triggers a notice, retain that outcome rather than inserting a warning.

The next gate is a natural-model guard-bearing export reconciled against raw events.
The [v0.2 proposal](v0.2-plan.md) is a plan only, conditional on that gate; nothing from
v0.2 or an A/B runner has been implemented.
