# Inspected Harness contract

Inspected on 2026-10-25 from the official repository, pinned at commit
`22ddee3792402c3e70ec5f86a63c3e3e895a2f60`. Session package version is `0.2.1-rc.3`;
`SESSION_FORMAT_VERSION` is **4**. The branch is rapidly evolving; these are pinned findings,
not claims about every release or a future `master`.

## Primary sources

All links below target that immutable commit.

- [Session types and version](https://github.com/deepseek-ai/deepseek-harness/blob/22ddee3792402c3e70ec5f86a63c3e3e895a2f60/packages/core/session/src/types.ts)
- [MessageSource and message roles](https://github.com/deepseek-ai/deepseek-harness/blob/22ddee3792402c3e70ec5f86a63c3e3e895a2f60/packages/llm/llm/src/message.ts)
- [Session subsystem documentation](https://github.com/deepseek-ai/deepseek-harness/blob/22ddee3792402c3e70ec5f86a63c3e3e895a2f60/docs/subsystems/session.md)
- [JSONL physical header and reader](https://github.com/deepseek-ai/deepseek-harness/blob/22ddee3792402c3e70ec5f86a63c3e3e895a2f60/packages/session/session-persistence-jsonl/src/format.ts)
- [ZIP serialization and archive layout](https://github.com/deepseek-ai/deepseek-harness/blob/22ddee3792402c3e70ec5f86a63c3e3e895a2f60/packages/session-query/session-log-export/src/archive.ts)
- [Guard implementation](https://github.com/deepseek-ai/deepseek-harness/blob/22ddee3792402c3e70ec5f86a63c3e3e895a2f60/packages/guard/repeat-tool-reminder/src/index.ts)
- [Guard documentation](https://github.com/deepseek-ai/deepseek-harness/blob/22ddee3792402c3e70ec5f86a63c3e3e895a2f60/packages/guard/repeat-tool-reminder/README.md)
- [Agent loop: context delivery](https://github.com/deepseek-ai/deepseek-harness/blob/22ddee3792402c3e70ec5f86a63c3e3e895a2f60/packages/core/agent-loop/src/agent.ts)
- [Known event vocabulary](https://github.com/deepseek-ai/deepseek-harness/blob/22ddee3792402c3e70ec5f86a63c3e3e895a2f60/packages/core/session/src/known-event-types.ts)

## Field mapping

| Observation | Verified upstream location |
|---|---|
| Session ID, format | First JSONL header: `type: session`, `id`, `version` |
| Fork classification | Header `isSeeded`; last `session/end-seed.data.inherited: true` marks cut |
| Event position | `seq`, contiguous and zero-based within a complete session |
| Time | `time`, Unix epoch milliseconds |
| Turn / step | Lifecycle `data.turn`, `data.step`; also present on tool events |
| Tool invocation | `type: tool/call`; `data.name`, `data.arguments`, `data.callId` |
| Tool result | `type: tool/result`; `data.message` is a tool-role message |
| Pairing key | Call `data.callId` = result `data.message.toolCallId`, scoped by turn/step |
| Result source | `data.message.source.kind: tool`, `source.callId` duplicates the pairing identity |
| Tool error | Optional `data.message.isError`; optional `data.error` outside model-facing content |
| User message | `data` itself is the UserMessage; there is **no nested `data.message`** |
| Reminder origin | `user/message.data.source.kind: repeat-tool-reminder` |
| Reminder display | Source `form: notice`, `summary`; no explicit triggering call ID |

Arguments arrive as an unparsed JSON string. `MessageSourceMap` is merge-extensible:
producers own their own `kind`, with no universal generic plugin marker. Guard detection
must use that structured kind, not a search over arbitrary payload text.

The guard observes per-agent tool execution in `tools/post-execute`, including denied calls,
and queues context for the next step. It uses recursively sorted JavaScript JSON values,
defaults to thresholds `[3, 5, 8]`, supports tool include/exclude rules and resets on real
user messages. Runtime chains live in a `WeakMap<Agent, Chain>` rather than persisted state.
AgentGuard Bench observes durable events; it does not emulate or configure this runtime.

The upstream V4 relationship validator removes a tool ID when its result settles; it does
not require global uniqueness across the session. The normal batch writer cites the
started call through result `sourceEventSeqs`. Rewritten `tool/result` surface nodes do
not open a new execution lifecycle. The repair implementation can synthesize a result for
an advertised call that never reached `tool/call`; such a result is not an observed start.
These details were checked in `session-format-v3-to-v4/src/relationships.ts`,
`core/tools/src/batch.ts`, and `core/session/src/repair.ts` at the same pinned commit.

The current export has one logical header followed by event lines, canonical
`session.v4.jsonl` naming, descendants under `subagents/<safe-id>/`, plus `media/` and
`files/` attachments, with **no manifest**. Old `v2` wording in serializer comments is stale;
the version constant and actual implementation determine current output. Markdown copy
omits injected guard messages and is therefore unsuitable for this analyzer.

## Related work checked

- [hccccc01333/dsh-eval](https://github.com/hccccc01333/dsh-eval): benchmark orchestration,
  trace harvesting, task checks and comparisons. Its
  [trace parser](https://github.com/hccccc01333/dsh-eval/blob/master/packages/eval/src/trace.ts)
  uses Harness's storage decoder, illustrating why older chunk formats cannot be treated
  as plain modern events without validation. This MVP does not recreate its runner.
- [CatheadOwl/dsh-eval](https://github.com/CatheadOwl/dsh-eval): a different project with a
  similar name, focused on plugin behavior cases, scripted model responses and review
  experiments. The README was inspected; no compatibility with its output is claimed.
- [qlheric/dsh-cvm](https://github.com/qlheric/dsh-cvm): runtime supervision plugins and
  reported A/B observations. Its README separates process outcomes from task outcomes
  and records limitations of small samples. Those findings are not independently
  reproduced here; no runtime guard or experiment runner is duplicated.

Related-project pages were inspected as background, not used as the authority for current
Harness field names. No code from those projects is incorporated. Protocol event names
in the normalizer come from the official MIT-licensed Harness vocabulary.

## Guard source regression check — 2026-10-25

A fresh fetch of official `master` still resolves to the pinned commit above. Both the
guard's current README ("Reminder delivery") and implementation create this native V4
source, inside the flat `user/message.data` UserMessage:

```json
{
  "type": "user/message",
  "data": {
    "role": "user",
    "source": {
      "kind": "repeat-tool-reminder",
      "form": "notice",
      "summary": "read × 3"
    }
  }
}
```

This is a field-location excerpt, not a complete session record. The actual producer
also supplies an identified message, content, sequence, timestamp and surface operation.
The detector reads `event.data.source.kind`; neither `event.source` nor
`event.data.message.source` identifies a native V4 user message. The form and summary
are metadata; the source kind identifies the producer without searching message text.

The older shape `{"kind":"plugin","plugin":"repeat-tool-reminder","form":"notice"}`
is documented by the official V3-to-V4
[source converter](https://github.com/deepseek-ai/deepseek-harness/blob/22ddee3792402c3e70ec5f86a63c3e3e895a2f60/packages/session/session-format-v3-to-v4/src/sources.ts).
It converts that released V3 identity into `kind: repeat-tool-reminder`, preserves form
metadata and removes `plugin`. The native V4
[source validator](https://github.com/deepseek-ai/deepseek-harness/blob/22ddee3792402c3e70ec5f86a63c3e3e895a2f60/packages/session/session-format-v3-to-v4/src/message-sources.ts)
explicitly refuses `kind: plugin`. It is therefore not a second native V4 guard encoding.

AgentGuard's V4-only detector already recognized the current source correctly. The
regression check additionally exposed a validation gap: a retired wrapper in a purported
V4 direct message was silently treated as an unrelated producer, yielding zero reminders.
Interpreted user/result messages now refuse this retired kind with a re-export diagnostic.
Historical V3 headers remain unsupported; no migration or legacy guessing was added.
This is not a complete validation of every nested Harness message slot.

`tests/test_guard_contract.py` specifies a literal current notice independently of the
shared trace builder, checks normalizer/analyzer and inspect/analyze JSON reporting, and
rejects the retired wrapper. Negative cases cover text mentions, incidental `plugin`
fields, source summaries, wrong source nesting and tool-argument decoys. The notice body
does not contain the guard name. These are synthetic contract regressions, not evidence
that a real guard-bearing export has been observed.

Verification: all 12 dedicated cases pass; the full working-tree suite passes 125 tests
on Python 3.14.8 and 3.11.16. The isolated staged snapshot, excluding three pre-existing
local tests and their unrelated fix, passes 122 tests. Ruff lint and formatting checks
pass. Reanalysis of RWV-001 produces the unchanged report: 70 calls and zero reminders.
