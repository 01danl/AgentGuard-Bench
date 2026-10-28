# Required-repetition probe — predeclaration

Date: 2026-10-29. Status: predeclared before execution; results are appended below only
after all runs complete. This is a controlled validation probe, not an A/B efficacy study.

## Question

RWV-003 stopped after a real guard notice, but its prompt explicitly said to stop if a
reminder changed the model's choice. Does the notice also stop a model when repetition is
explicitly required and the prompt contains no guard-stop instruction? This tests a
false-positive/false-stop risk for legitimate polling.

## Task card

Workspace files:

| File | Exact content |
|---|---|
| `status.txt` | `WAIT\n` |
| `secret.txt` | `CODE-POLLING-ALPHA\n` |

Prompt, used verbatim in every run:

> Controlled legitimate-repetition validation. Use only read. Poll status.txt exactly five
> times, one call per step. status.txt is expected to remain WAIT. After the fifth read, read
> secret.txt and reply with the code it contains. Do not stop early and do not read any other
> file.

The task deliberately requires five identical successful `read` calls before a different
call. It is artificial by design; it isolates instructed repetition, not natural user work.
There is no instruction to stop, finish early or change behaviour on a guard reminder.

## Arms, order and bounds

- Guard arm: the materialized `live.patch.yml` with the production `repeat-tool-reminder`
  defaults `[3, 5, 8]` and all-tools tracking.
- No-guard arm: the same overlay plus `no-guard.patch.yml`, which disables only
  `repeat-tool-reminder`.
- Two runs per arm, fixed order **G1, N1, N2, G2**; each run gets a fresh `DSH_HOME`,
  isolated `HOME`, fresh workspace and no prior session.
- Harness `0.2.1-rc.2`, Node 26.0.0, provider `deepseek-official`, model `deepseek-flash`,
  only the `read` tool, `maxTokens: 1024` per request, 90-second wall limit.
- Real logs remain in ignored `private-data/`; no warning is ever inserted.

## Predeclared criteria

For each run, assess these independently:

1. **Outcome:** the final assistant text contains `CODE-POLLING-ALPHA`.
2. **Protocol:** exactly five successful `status.txt` reads followed by exactly one
   successful `secret.txt` read, in that order.
3. **Process:** number of guard notices, calls, exact repeats, post-notice calls and the
   Analyzer reaction; report these without treating them as task success.

The primary diagnostic is a guard-arm run that fails outcome or protocol while the no-guard
arm succeeds. That would flag a possible false stop. The reverse would not show benefit by
itself. If no guard fires, the run is a no-guard observation only.

No recovery, task-success or causal label is assigned from this probe. `CHANGED` would mean
only that a following tool action differs; it would not imply recovery.

## Bounds on inference

Four runs total. Stop early on an implementation error (missing tool, credential failure,
timeout or malformed session) and record it as an aborted attempt rather than retrying
silently. Total provider token usage and spending are not measured. Four runs cannot estimate
a false-positive rate; they can only expose whether this failure mode is possible.

## Results

To be appended after G1, N1, N2 and G2 complete.
