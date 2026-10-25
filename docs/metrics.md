# v0.1 metric definitions

These are descriptive observations, not measures of task success or causal guard efficacy.
The implementation is `analyze_session()` / `analyze_sessions()` in `src/agentguard/analyzer.py`.
All aggregate counts are sums of independent session counts. Duplicate session IDs are
refused, including when calling the analyzer directly rather than through the loader.

## Scope and counts

Let E be all normalized event envelopes in a complete input file, excluding its session
header. If a seeded session has last tagged inherited boundary at seq c, its inherited
prefix is the events with seq < c. The boundary event itself is outside the prefix.
Let C be the ordered `tool/call` events outside the inherited prefix.

| Field | Definition | Interpretation / limitation |
|---|---|---|
| `sessions` | Number of distinct supplied session logs | A log is not a task or an independent experimental trial |
| `events` | Length of E | Includes inherited, ignored and unrelated events; excludes header and attachments |
| `inherited_events` | Count of events with seq < c, otherwise zero | A storage prefix, not the child's actions |
| `tool_calls` | Length of C | Counts observed starts, not assistant advertisements, PTC subcalls or result-only repairs |
| `missing_tool_results` | Number of calls in C without an unambiguously associated execution result | Missing observation, not failure or lack of progress |
| `guard_reminders` | Number of non-inherited direct `user/message` events whose structured source kind is `repeat-tool-reminder` | Does not count text mentions, spliced copies or inferred threshold crossings |
| `reactions[label]` | Number of direct reminders with headline reaction equal to label | Exactly one headline per reminder; the three counts sum to `guard_reminders` |
| `open_turns_at_end` | Set of observed started turns minus their observed ended turns, outside inherited history | Export during execution and crash can look identical; absent markers cannot establish a complete lifecycle |

Calls correlate by call ID **within their session and turn/step**, using explicit result
`sourceEventSeqs` when they cite a call. Known coordinates and IDs must agree. Missing
coordinates permit only an unambiguous association. Result `surfaceOp: replace` rewrites
are not additional executions. Result-only Harness repairs can legitimately be orphans.

## Exact repetition

The identity of a call is `(tool name, canonical_arguments(raw argument string))`.
Missing name or arguments gives unknown identity. Tool-call IDs identify invocations;
they are deliberately not part of action equality.

`canonical_arguments()` parses JSON with duplicate-key and non-finite-constant checks,
recursively sorts object keys, preserves array order and tags node types to avoid collisions.
Whitespace outside strings and Unicode escape spelling do not affect equality. String
contents do: `"a b"` and `"a  b"` differ. Number lexemes are preserved: `1` and `1.0`
differ. This conservative numeric policy differs from JavaScript's JSON number semantics
and can miss equivalent calls, while avoiding rounding distinct large integers together.

Malformed, duplicate-key, non-finite-constant or excessively nested arguments use a tagged
raw Unicode string fallback. Raw strings are not trimmed. Equal invalid strings are an
observed repeated attempted action, not evidence that the tool executed successfully.

Scan C in event order, resetting at a human prompt, resume/fork marker or unsupported
behavioral boundary. A known identity equal to the previous call's identity increments
the streak; a different/unknown identity starts a new streak. Non-call lifecycle/result
events do not break a chain unless marked as boundaries.

For maximal known-identity runs of lengths L1, L2, ...:

`exact_repeats = sum(max(Lj - 1, 0))`

Each repeated call has one evidence record with `previous_seq`, `seq`, `action_id` and
`streak_length`. This is a count of repeated invocations, **not a count of loop incidents**.
`possible_loop = (streak_length >= 3)` is an unvalidated per-event heuristic. It is never
an error flag. A polling sequence of five identical calls has four repeats and three
events marked as possible loops; it may still be correct and useful work.

## Reminder baseline and reactions

For a direct reminder at g, consider the preceding tool step after the latest boundary.
Candidate sequences are reported up to 20 entries, with their full count and a truncation
flag; the checks cover every candidate, including entries beyond the evidence cap.

An inferred baseline requires all of the following:

1. The prior tool step and reminder have known turn/step coordinates, and the reminder
   enters a different step.
2. The prior step closed before g.
3. Every candidate call has a matched result before g.
4. Every candidate has the same known action identity. This is checked directly through
   a per-group identity-change prefix index, independently of the global repetition streak.
5. The last candidate has an observed consecutive streak of at least two calls.
6. No human prompt or unsupported behavioral boundary separates candidates from g.

`trigger_call_seq` is the last candidate, used as a representative of that inferred action.
It is **not** an upstream trigger ID. The plugin does not persist such an ID. Missing
configuration, batch completion order and delayed delivery prevent definitive attribution.
When these conditions fail, attribution and reaction are unknown.

Starting strictly after g, observe up to K tool calls, stopping before the next direct
reminder, human prompt/behavioral boundary or end of log. K must be a positive integer.
Each observed call is compared with the same baseline:

| Reaction | Rule |
|---|---|
| `IGNORED` | Both identities are known and exactly equal |
| `CHANGED` | Both identities are known and different |
| `UNKNOWN` | Baseline or next identity is unknown, or no following call is available |

The headline reaction is the **first** observed call's reaction. It does not summarize
all later behavior. Every later call retains its individual classification. Thus an
`IGNORED` headline can coexist with a later `CHANGED` action in the same window.

`window_observed` is the number of retained calls; `window_complete` is true iff that
number equals K. `window_stop_reason` reports `window_limit` for a full window, otherwise
`next_reminder`, `behavioral_boundary` or `end_of_log`. A short window can still have a
known first-call reaction. No following call, including legitimate task completion,
gives `UNKNOWN` rather than an invented success verdict.

## Evidence fields and deliberately unknown outcomes

- `timestamp_ms`, `turn`, `step`, `call_id` and `result_seq` identify the source observation.
  Missing timestamps remain null; time and token metrics are not inferred.
- `action_id` is a deterministic session-local equality label, not a hash or a globally
  comparable action ID. `argument_mode` is `json`, `raw`, or null for missing arguments.
- `is_error` copies the matched result's optional explicit `isError` flag, or null.
  `has_error_metadata` records only presence of `data.error`, without disclosing details;
  it is null when no result is associated. No shell exit-code success metric is computed.
- `verified_lack_of_progress`, `task_success`, `recovered` and `guard_causal_effect` are
  always null in v0.1. No formula for them is claimed. A changed action or non-error result
  cannot substitute for an independent task-success criterion or a controlled comparison.

The synthetic example has calls at seq 6, 11, 16, 22, 27 and results at 7, 12, 17, 23, 28.
The first four calls share one identity, giving three repeat records. Reminder seq 20
uses seq 16 as an inferred representative; seq 22 is `IGNORED`, seq 27 is `CHANGED`.
The headline is therefore `IGNORED`, with an incomplete 2/5 window. Recovery remains null.
