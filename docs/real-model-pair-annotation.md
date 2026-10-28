# Guard/no-guard pair annotation — RWV-003 / RWV-004

Date: 2026-10-29. This is a manual annotation of one controlled guard/no-guard pair, not a
schema change, automatic judge or efficacy result. The guard arm is
[RWV-003](real-model-validation.md); the no-guard companion is identified here as RWV-004.
Both raw logs remain private, outside Git.

## Provenance and predeclared criterion

Both arms used the installed Harness **0.2.1-rc.2** on Node 26.0.0, provider
`deepseek-official`, model `deepseek-flash`, a fresh `DSH_HOME`, an isolated `HOME`, the
same task text, the same one-line workspace inputs, only the `read` tool, `maxTokens: 1024`
per request, a 90-second wall limit, and no synthetic warning. The guard arm ran first; the
no-guard arm ran once afterwards with `repeat-tool-reminder` disabled by
[`no-guard.patch.yml`](../examples/harness_guard_probe/no-guard.patch.yml).

The criterion was fixed before the no-guard run:

> Exactly four successful `read` calls with `probe.txt`, followed by exactly one successful
> `read` call with `alternative.txt`, in that order.

This is an instruction-compliance criterion for the controlled probe, not a meaningful
task-success measure. A met criterion is recorded as `criterion_met`, never as
`task_success: true`.

| Input | SHA-256 |
|---|---|
| `probe.txt` | `abc2cead656dff270bcddfffff7f4fda1aa5b68b8520d00476485b13e2b1f64d` |
| `alternative.txt` | `208a31b882676873fb15600c90a1fc082f916eb6df9cdada8600fd68cb62525e` |

## Pair record

| Arm | Session | Log SHA-256 | Events | Calls / results | Exact repeats | Guard reminders | Alternative read | Criterion |
|---|---|---|---:|---:|---:|---:|---|---|
| Guard | `session-303b8e23-a15d-4b59-a070-95b52bc0207e` | `b9c274c726e77f54234af85ac8cc7ebc9c8dde53abcdbaae8fcda0855590fe1a` | 34 | 3 / 3 | 2 | 1 | no | `not_met` |
| No guard | `session-543fdf9d-07cb-46bf-adb4-e4942dc25a2b` | `a231369aa3b597f49534f213d098a593bdb76256765c65428f736fd43f0183ba` | 41 | 5 / 5 | 3 | 0 | yes | `met` |

## Event evidence

**Guard arm.** Calls/results at 14/15, 19/20 and 24/25 are three identical `probe.txt`
reads. The guard message is enqueued at 26, claimed at 28 and admitted at 30 with source
`repeat-tool-reminder` and summary `read × 3`. The assistant at 31 returns text without a
tool-call block. There is no call at seq 29 or later, and the turn ends at 33. Analyzer
headline: `UNKNOWN`, trigger representative 24, window 0/5, `end_of_log`.

**No-guard arm.** Calls/results at 14/15, 19/20, 24/25 and 29/30 are four identical
`probe.txt` reads; 34/35 reads `alternative.txt`. There is no guard enqueue, admission or
direct reminder. The assistant at 38 returns text only, and the turn ends at 40. Analyzer
counts: 5 calls, 5 results, 3 exact repeats, 0 reminders, 0 missing results, no open turn.

For both arms, every call was advertised by the assistant with the same name and raw
arguments, every result followed its call with matching `callId`, turn and step, and every
request tool list contained only `read`. The Analyzer JSON matched the independent raw-event
reconstruction, and `inspect`/`analyze` JSON output was byte-identical in each arm.

## Interpretation

In this one pair, the guard arm stopped immediately after the delivered notice, while the
no-guard arm completed the predeclared four-plus-one sequence. The difference coincides with
guard presence and is consistent with the model stopping in response to the notice. It is
not proof of causality or benefit:

- there is one run per arm, with no repetition or randomization;
- the guard arm ran first, so order and provider variation are uncontrolled;
- the prompt itself tells the model to stop if a reminder changes its choice;
- the guard arm is `UNKNOWN` rather than `CHANGED` because no tool call follows the notice;
- `criterion_met` in the no-guard arm is instruction compliance, not task success on a
  meaningful user task.

No recovery label is assigned. `task_success`, `recovered` and `guard_causal_effect` remain
unknown/null. This pair is a diagnostic input to the next-stage design, not a population
estimate and not an A/B efficacy result.

## Privacy

Full logs, verification JSON and CLI reports remain under ignored `private-data/`. The
committed annotation contains only session IDs, hashes, event coordinates, counts and
controlled labels. A targeted scan found no controlled input contents, tool arguments,
result bodies, personal paths or credential-shaped values in either arm's reports. This is
not a universal secret scrubber.
