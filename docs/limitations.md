# Limitations and interpretation rules

## Evidence, not outcomes

- Exact repetition can be legitimate polling, a verification retry, or work after the
  environment changed. It does not prove wasted effort or an agent error.
- `possible_loop` means a streak reached at least three identical calls. This threshold
  is an unvalidated analyzer heuristic, not the guard's configured threshold.
- `verified_lack_of_progress`, task success, recovery and guard causal effect remain `null`.
- A nonzero command exit code can be useful debugging evidence. We never parse one as a
  task verdict. `is_error` preserves the explicit Harness tool flag, including unknown.
- A single trajectory supplies no counterfactual. Do not infer a guard's causal effect
  from this report, or compare summary counts as though tasks and environments were controlled.

## Compatibility

- Only the inspected Harness persistence format **v4** is supported. Versions 0–3 and
  future versions are explicitly refused. Package version `0.2.1-rc.3` is a separate concept.
- No legacy storage chunk decoder, migration engine, `.jsonl.zstd` reader, SQLite reader,
  or Markdown transcript importer is implemented. Use the current Harness ZIP export.
- No real exported session was available. Tests use explicitly synthetic fixtures derived
  from source. Integration compatibility with real sessions has **not** been verified.
- This is a focused envelope/message projection, not complete Harness validation or replay.
  Missing timestamps, call IDs, arguments, tool names and tool flags can be represented as
  unknown with warnings. Wrong types in the fields we interpret are rejected. Sequence
  numbers and v4 identity/seed headers remain required; missing values are not invented.
  Conflicting message roles/sources and error metadata without `isError: true` are refused.
- Call IDs are scoped by turn/step; explicit source references take precedence and must
  agree with known coordinates and IDs. Reuse in different steps is supported. Ambiguous
  missing coordinates and duplicate call IDs within one scope are refused. A result
  without a matching started `tool/call` is retained as an orphan warning; Harness can
  legitimately synthesize `TOOL_NOT_STARTED` repair results, so an orphan is not a task error.
- `tool/result` surface replacements are presentation history, not new execution results.
  Tool flags in reports describe the original matched execution result, not a later rewrite.
- Unknown required events are refused; unknown `ignorable: true` events are retained
  as counted envelopes without interpreting their payload. Known unrelated events count
  toward totals without being interpreted as behavioral evidence.
- PTC-dispatched actions and inbox-spliced or compacted messages are not reconstructed as
  additional tool calls or guard reminders. These events / surface replacements create
  analysis boundaries with warnings. Thus reminder counts cover direct committed
  `user/message` records only, not every historical or indirect presentation of a message.
- Inherited fork history is excluded from behavioral metrics and listed separately in
  event totals. It is never attributed to the child agent. Ordinary untagged resume markers
  reset context, but exports do not prove the lifetime of the guard's in-memory state.

## Repetition identity

- Only consecutive tool invocations in log sequence count as repetitions. Results and
  ordinary lifecycle events between calls are allowed; another tool action breaks a streak.
- Real user prompts, resume/fork markers and unsupported behavioral boundaries reset chains.
- The analyzer does not know guard `include` / `exclude` patterns or configured thresholds.
  Its all-tools sequence therefore need not reproduce the guard's internal counters.
- Object-key order and JSON formatting whitespace are ignored. Arrays remain ordered;
  whitespace **inside strings** matters. There is no cosmetic-change heuristic in v0.1.
- Numeric lexemes are conservative: `1`, `1.0`, `1e0`, `-0` and `0` are distinct. Large
  integers do not collapse through IEEE-754 rounding. This differs from JavaScript guard
  canonicalization and can miss equivalent calls; it avoids falsely merging different values.
- Invalid JSON, duplicate argument keys, non-finite constants and excessive nesting use a
  tagged exact raw-string fallback. Raw input is not trimmed or otherwise normalized.
  Duplicate keys or non-finite/out-of-range numbers in the JSONL envelope itself are refused.
- Same actions can have different results or environmental consequences. Results are
  correlated and their explicit error flags recorded, not used as proof of progress.

## Reminder attribution and observation window

The detector accepts only `user/message.data.source.kind == "repeat-tool-reminder"`.
It ignores reminder strings in content and arbitrary nested data. This establishes what
the producer recorded; it cannot authenticate a tampered session file.

The current plugin queues reminders as additional context, with a producer kind, form
and display summary, but **no explicit triggering call ID**. It can queue several contexts
after a tool batch. Summary text is neither a stable identity contract nor sufficient
evidence of which parallel call caused a warning.

An inferred baseline is available only if the preceding observed tool step has known
turn/step IDs, has closed before the reminder, every candidate call has a completed
result, all candidates share one action identity, and that identity has an observed
consecutive streak of at least two. The reminder must have known turn/step coordinates
and enter another step; absent coordinates cannot prove a step transition. Intervening
human input or unsupported boundaries invalidate the context. Candidate sequences are
reported up to 20 entries with explicit count/truncation; the identity check covers all.

Even then, `trigger_call_seq` is a representative of an **inferred context**, not proof
of the exact internal trigger. Missing guard configuration, excluded calls, delivery delays,
parallel completion order and guard state across restarts can reduce attribution coverage.
Ambiguity gives `trigger_attribution: "unknown"` and reaction `UNKNOWN`.

Headline reaction compares the **first** subsequent tool call with that baseline. An exact
match is `IGNORED`; a different complete identity is `CHANGED`; incomplete evidence is
`UNKNOWN`. Each call in the window gets its own comparison with the same baseline.
These labels do not diagnose whether the model read or understood the reminder.

Observation stops at K calls, next direct reminder, behavioral boundary or end of log.
User input prevents later actions from being attributed to an earlier warning. An incomplete
window can still have a known first-call reaction. No later call means unknown, including
an agent that legitimately completed the task. `open_turns_at_end` reports observed open
turns; it does not distinguish a crash from an export made while an agent was running.

## Resource and privacy boundaries

ZIP paths, duplicate names, symlinks, encryption, compression methods and expansion ratios
are checked. Nothing is extracted. Member CRCs are checked for consumed logs; unused
attachments are never decompressed and their CRCs are not verified. Declared attachment
sizes still count toward archive limits. Extremely compressible valid logs can exceed
the ratio policy. ZIP metadata is read by stdlib `zipfile` within the input file-size bound.

Byte/event budgets bound input, not Python process memory or CPU. JSON objects, canonical
strings, indexes and report objects increase memory usage beyond source bytes. Use smaller
limits for constrained environments. There is no streaming output database or process sandbox.

Reports intentionally omit argument/result bodies, message text, guard summaries, internal
error payloads and argument hashes. Metadata (session IDs, parent IDs, tool names, call IDs,
relative paths) is preserved and may itself be sensitive if the producer put secrets there.
This is data minimization, not a universal secret scrubber. Raw payloads remain in memory.
Do not share unreviewed reports or commit real logs. Corruption diagnostics do not echo lines.
