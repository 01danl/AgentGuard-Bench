# v0.1 engineering audit — 2026-10-25

Scope: verify and repair existing offline analysis. No v0.2 feature was added.

## Findings and repairs

The initial suite passed 81 tests. Additional independent cases exposed real gaps:

| Finding | Repair / regression evidence |
|---|---|
| Session-global call-ID uniqueness rejected valid ID reuse in later steps | Pair by session-local coordinates and explicit call references; reused-ID regression |
| Result coordinates and cited call could disagree without rejection | Validate both ID and coordinate agreement; negative pairing cases |
| Rewritten result nodes looked like duplicate executions | Keep the original execution association and count rewrites as boundaries |
| Historical positioned events could overwrite current context | Only lifecycle markers update active context; historical replacement regression |
| Contradictory message roles/sources or error metadata were accepted | Reject contradictory discriminators and require `isError: true` with error metadata |
| Unknown reminder step was treated as a different step | Require known reminder coordinates before inferring a baseline |
| A global action streak could conceal mixed candidates in malformed step groups | Check candidate homogeneity directly using per-group identity changes |
| Direct analyzer API allowed duplicate session aggregates / invalid empty-input windows | Validate these invariants before aggregation |

Nine new normalizer cases failed before their fixes. Three initial analyzer audit cases
and the mixed-group regression also failed before their respective fixes. The added
regressions demonstrate problems the original green suite did not cover.

Fix commits: `5b79104`, `c15dc96`, `e011259`.

## Executed verification

- Python 3.14.8: full pytest suite, **110 passed**; Ruff lint and formatting checks pass.
- Python 3.11.16: separately installed interpreter and virtual environment, full suite,
  **110 passed**; Ruff and installed CLI JSON smoke check pass.
- All README shell commands executed in an isolated copy, including editable developer
  installation and normal runtime installation. `private-data/export.zip` was explicitly
  populated by the synthetic ZIP generator, since it is an input prerequisite, not a
  committed real export. All command exit codes were zero.
- JSONL inspect/analyze, ZIP inspect/analyze, K window option, JSON redirection and
  `python -m agentguard` were exercised. Existing text/JSON example reports reproduce.
- Cross-session tests use matching call IDs/coordinates with an unfinished parent call
  and an orphan child result: no association crosses the session boundary. A parent
  reminder with no following call cannot borrow child actions.
- Privacy regressions inspect both JSONL and ZIP reports in text/JSON form. Synthetic
  secrets in arguments, result content, private tool metadata, error reasons, reminder
  summaries and user content never appear in reports. Metadata is still preserved and
  is not covered by a universal secret-scrubbing guarantee.
- Negative cases cover invalid JSON/UTF-8, unsupported formats, missing required headers,
  absent optional/incomplete fields, unknown events, gaps, missing/orphan results, open
  turns, ZIP traversal/symlinks/duplicates/CRC failures and resource budgets.

Detailed metric algorithms and limitations are in [metrics.md](metrics.md). This audit
uses independent count/equality oracles in addition to assertions about output shape.

## Harness evidence

An actual `git fetch --depth 1 origin master` returned commit
`22ddee3792402c3e70ec5f86a63c3e3e895a2f60`, identical to the original inspected source.
Session format remains v4; the normalizer's vocabulary exactly matches all 62 upstream
known event names. Types, message sources, batch writer, V4 relationship validator,
recovery implementation, reminder implementation and export serializer were inspected.
See [harness-contract.md](harness-contract.md) for sources.

Two independent, upstream-maintained V4 demonstration fixtures were analyzed in place
from the official checkout; their bytes were not copied into this repository:

| Fixture under `packages/experimental/webworker-runtime/tests/fixtures/vfs-example/` | Events | Calls | Missing results |
|---|---:|---:|---:|
| `home/sessions/--dsh-workspace--/preview-showcase/session.v4.jsonl` | 203 | 11 | 0 |
| `home/sessions/--dsh-workspace--/preview-turn-spacing/session.v4.jsonl` | 43 | 6 | 0 |

Raw event/call counts were checked independently. Every associated result was checked
against raw ID and turn/step coordinates. Both fixtures have zero direct repeat reminders;
they do not validate post-reminder behavior on independently produced exports.

**No real user JSONL or Harness-generated export archive was available in the workspace.**
These are source-contract checks and upstream fixture checks, not a successful real-export
integration test. A Harness runtime was not launched, and its complete TypeScript schema
validator was not executed by this audit. Our normalizer remains a partial projection.

## Required real-data pilot before expansion

With explicit permission to use a private export, check:

1. A root log and actual exported ZIP, including descendants and JSONL attachments.
2. A real reminder incident: manually verify source kind, delivery step, preceding batch,
   all result associations, first next call and remaining window against the raw log.
3. Parallel tool batches, reused IDs, missing/interrupted outcomes and result-only repairs.
4. Resumed/forked sessions and inherited cuts: child metrics must exclude ancestor actions.
5. Legitimate polling and validation retries: repeated calls must not become task failures.
6. Report privacy, representative input size and actual peak memory on realistic logs.

Keep data out of Git. Record the Harness commit/package version and analysis window.
Manually reconcile the report before using it as research evidence.

## Readiness

The implementation is ready for a controlled real-data pilot: the offline pipeline is
installable, regressions cover the discovered defects, and the supported Python floor
was exercised. Full real-export compatibility and recovery/causal validity remain unproven.
Complete that pilot before treating v0.1 as a validated research benchmark or broadening
scope to v0.2. Passing unit tests alone is insufficient evidence of those stronger claims.
