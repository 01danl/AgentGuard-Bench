# Required-repetition probe — RWV-005

Date: 2026-10-29. Status: predeclared before execution; four runs executed on 2026-10-29.
Results were appended after all runs completed. This is a controlled validation probe, not
an A/B efficacy study.

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

All four runs exited 0 with empty stderr. The fixed order and durations were:

| Run | Arm | Session | Log SHA-256 | Seconds | Events | Calls | Repeats | Guard | Reaction |
|---|---|---|---|---:|---:|---:|---:|---:|---|
| G1 | guard | `session-b3cf5dbe-bb58-423c-8377-4dc89a9d9395` | `d89bba08c0d18ada822ef7eff2485f28058464b03856c24c2dda36805bd16bb6` | 14.6 | 49 | 6 | 2 | 1 | `CHANGED` |
| N1 | no guard | `session-95c164aa-97aa-413d-869f-4b50868a6c0e` | `b9c8279a056812d95f12c21751cd587cc0ca4c1bb2ff087d6f1f41e77935fc55` | 10.1 | 46 | 6 | 4 | 0 | — |
| N2 | no guard | `session-442ba9a0-abf4-4db9-959b-11c64686c1b0` | `229771b7963c615f8f882ae27dc85344c608a994e99843fd2f21766e3c15f22f` | 9.0 | 46 | 6 | 4 | 0 | — |
| G2 | guard | `session-12dcf7de-c78a-462c-ba93-357fc1950767` | `4ea835657e0cb2d8802e0899313eb1e94ab3829e867c4171513458324ab38bfd` | 14.8 | 49 | 6 | 2 | 1 | `CHANGED` |

Every run made exactly five successful `status.txt` reads followed by one successful
`secret.txt` read, and every final text contained `CODE-POLLING-ALPHA`. Both the protocol and
outcome criteria were met in all four runs. Every request advertised only `read`; every call
had a matching result with the same call ID and coordinates.

### Guard arms

G1 and G2 each enqueue one guard message at seq 26, claim it at 28 and admit it at 30. Calls
at 14, 19 and 24 are identical absolute-path reads of `status.txt`; the guard's
`read × 3` notice arrives before step 4. The next calls deliberately vary the argument
surface:

| Run | Seq 32, fourth poll | Seq 37, fifth poll | Seq 42 |
|---|---|---|---|
| G1 | absolute path + `offset: 1`, `limit: 1` | relative path + `limit: 1` | `secret.txt` |
| G2 | absolute path + `limit: 1` | relative path + `offset: 1`, `limit: 1` | `secret.txt` |

The model's own reasoning shows the adaptation. G1 asks whether it can "read with offset or
limit"; G2 says it can "use limit or offset variation" to satisfy the request for different
arguments "while same file". All five status reads still returned the same `WAIT` content,
and all calls were non-error.

The guard therefore produces a real `CHANGED` reaction in both runs: the first following call
(seq 32) differs from the baseline. The Analyzer reports one reminder, trigger representative
24, following calls 32/37/42, window 3/5 and `end_of_log`. There is no second `read × 5`
notice because the exact-identity chain is broken after the first adaptation.

### No-guard arms

N1 and N2 make five identical absolute-path `status.txt` reads at seqs 14, 19, 24, 29 and 34,
then read `secret.txt` at 39. They record four exact repeats, no guard message and no
reaction. The task outcome and protocol are the same as in the guard arms.

### Reconciled observations

| Observation | G1 | N1 | N2 | G2 |
|---|---:|---:|---:|---:|
| Tool calls / results | 6 / 6 | 6 / 6 | 6 / 6 | 6 / 6 |
| Exact repeats | 2 | 4 | 4 | 2 |
| Guard reminders | 1 | 0 | 0 | 1 |
| Reaction | `CHANGED` | — | — | `CHANGED` |
| Post-notice window | 3 / 5 | — | — | 3 / 5 |
| Five status + secret | yes | yes | yes | yes |
| Outcome code | yes | yes | yes | yes |

The independent raw-event check verified the v4 header, contiguous seqs, all call/result
pairings, advertised calls, tool scope, guard enqueue/claim/admission payloads, the five
`status.txt` reads plus `secret.txt`, and the no-guard absence of guard events. AgentGuard
`inspect` and `analyze` JSON output was byte-identical in each run. The Analyzer counts above
match the independent reconstruction.

## Interpretation

This probe did **not** reproduce the RWV-003 stop. With explicit required repetition and no
stop-on-reminder instruction, both guard runs continued the task and returned the code. The
guard did change the exact action: `CHANGED` is mechanically correct. But the change was an
argument-surface adaptation (`offset`/`limit`/relative path), not a different information need
or a better strategy. All four runs still performed the same semantic polling sequence.

This exposes an important limitation for interpretation:

- `exact_repeats` falls from four to two because identity is
  `(tool name, canonical arguments)`, as defined in [metrics](metrics.md);
- the guard notice itself suggests "different arguments", so the model can comply with the
  notice while continuing the same repeated read;
- `CHANGED` therefore must not be read as recovery, improved progress or causal benefit; here
  it is a *surface-level* action change with an unchanged outcome.

The result is consistent with the RWV-003 stop being prompt-conditioned: that prompt explicitly
said to stop if a reminder changed the model's choice, while this task explicitly required
continued polling. It is not proof of that explanation, and it does not establish a general
model policy. It also does not show guard harm: there was no false stop in this probe.

No recovery, task-success or causal label is assigned. `CHANGED` means only that a following
tool action differs. The outcome code and protocol compliance are controlled probe results,
not a meaningful user-task success measure.

## Limits and privacy

This is four runs of one artificial read-only task, two per arm, with fixed order and no
randomization. It cannot estimate false-positive or false-negative rates, general natural-task
behaviour, other models, other Harness versions, mixed/parallel tool batches or token/cost
totals. The task deliberately requires five identical reads; it is not a natural distribution.
The no-guard arms were run between the two guard arms, but order and provider variation remain
uncontrolled.

Full logs, verification output and CLI reports remain under ignored `private-data/`. The
committed text contains only session IDs, hashes, counts, controlled labels and short model
reasoning excerpts. A targeted scan found no controlled file contents, tool arguments, result
bodies, personal paths or credential-shaped values in the reports. This is not a universal
secret scrubber.
