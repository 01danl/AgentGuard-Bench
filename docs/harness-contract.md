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
| Pairing key | Call `data.callId` = result `data.message.toolCallId` |
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
