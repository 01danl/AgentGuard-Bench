// Controlled scripted-model run. Real Harness loop/tools/guard/persistence/export.
import { createRequire } from 'node:module';
import { pathToFileURL } from 'node:url';
import { join, resolve } from 'node:path';
import { writeFile, mkdir, readdir, readFile } from 'node:fs/promises';
import { apply as installReadOnlyProbe } from './read-only.mjs';
const packageRoot = process.env.AGENTGUARD_DSH_PACKAGE_ROOT;
if (!packageRoot) throw new Error('AGENTGUARD_DSH_PACKAGE_ROOT is required');
const require = createRequire(join(packageRoot, 'package.json'));
const load = name => import(pathToFileURL(require.resolve(name)).href);
const { LlmAdapter, createUserMessage } = await load('@deepseek-ai/dsh-llm');
const { SessionId } = await load('@deepseek-ai/dsh-session');
const { createLaunchEnvironmentSnapshot } = await load('@deepseek-ai/dsh-launch-environment');
const { readSessionLogText, streamSessionLogZip } = await load('@deepseek-ai/dsh-session-log-export');
const installedVersion = require('./package.json').version;
if (installedVersion !== '0.2.1-rc.2') throw new Error('This probe is verified only with dsh 0.2.1-rc.2');
const { runProfile } = await import(pathToFileURL(join(packageRoot, 'lib/profile-boot.js')).href);
const mode = process.argv[2];
if (!['ignored', 'changed', 'unknown'].includes(mode)) throw new Error('Expected ignored|changed|unknown');
if (!process.env.DSH_HOME || !process.env.AGENTGUARD_PROBE_PATCH || !process.env.AGENTGUARD_PROBE_ARTIFACTS) {
  throw new Error('Explicit DSH_HOME, AGENTGUARD_PROBE_PATCH and AGENTGUARD_PROBE_ARTIFACTS are required');
}
await mkdir(process.env.DSH_HOME, { recursive: true, mode: 0o700 });
if ((await readdir(process.env.DSH_HOME)).length !== 0) throw new Error('A fresh empty DSH_HOME is required');
for (const [file, marker] of [['probe.txt', 'CONTROLLED_RUNTIME_READ_ONLY_PROBE\n'], ['alternative.txt', 'CONTROLLED_RUNTIME_ALTERNATIVE\n']]) {
  if (await readFile(file, 'utf8') !== marker) throw new Error('Run only in the prepared disposable workspace');
}
const artifactRoot = resolve(process.env.AGENTGUARD_PROBE_ARTIFACTS);
await mkdir(artifactRoot, { recursive: true, mode: 0o700 });
const receipts = [];
class ScriptedAdapter extends LlmAdapter {
  calls = 0;
  async resolveModel(provider, model) {
    return { provider, id: model, name: 'Scripted runtime validation; no LLM',
      reasoning: { efforts: [{ id: 'off', name: 'Off' }], defaultEffort: 'off' } };
  }
  async *stream(options) {
    this.calls += 1;
    if (this.calls > 6) throw new Error('Scripted response budget exceeded');
    if (!options.tools?.length || options.tools.some(tool => tool.name !== 'read')) {
      throw new Error('Only the production read tool may be exposed during this probe');
    }
    const notices = options.messages.filter(message => message.source?.kind === 'repeat-tool-reminder');
    receipts.push({ response: this.calls, structuredReminderCount: notices.length });
    const repeat = this.calls <= 3 || (this.calls === 4 && mode === 'ignored');
    const changed = this.calls === 4 && mode === 'changed';
    if (repeat || changed) {
      const args = JSON.stringify({ file_path: changed ? 'alternative.txt' : 'probe.txt' });
      const id = `controlled-${this.calls}`;
      yield { type: 'block-start', index: 0, blockType: 'tool-call' };
      yield { type: 'tool-call-delta', index: 0, id, name: 'read', argumentsDelta: args };
      yield { type: 'block-end', index: 0, block: { type: 'tool-call', id, name: 'read', arguments: args } };
      yield { type: 'finish', reason: { kind: 'tool-calls' } };
    } else {
      const text = 'Controlled scripted-model validation finished. No recovery claim.';
      yield { type: 'block-start', index: 0, blockType: 'text' };
      yield { type: 'text-delta', index: 0, text };
      yield { type: 'block-end', index: 0, block: { type: 'text', text } };
      yield { type: 'finish', reason: { kind: 'stop' } };
    }
  }
}
const environment = createLaunchEnvironmentSnapshot([{ source: 'process', values: { ...process.env } }]);
let app;
let timer;
let exitCode = 1;
try {
  app = await runProfile({ environment, profile: 'headless', patchFiles: [process.env.AGENTGUARD_PROBE_PATCH], args: ['Controlled read-only guard validation'] });
  app.ctx.llm.registerAdapter(['agentguard-scripted'], new ScriptedAdapter());
  installReadOnlyProbe(app.ctx);
  const agent = await app.ctx.agentLoop.create(SessionId(`controlled-${mode}`), { provider: 'agentguard-scripted', model: `scripted-${mode}`, reasoningEffort: 'off' }, { cwd: process.cwd() });
  const idle = new Promise((resolveIdle, rejectIdle) => {
    const dispose = app.ctx.on('agent/status', ({ agent: current, status }) => {
      if (current === agent && status === 'idle') { dispose(); resolveIdle(); }
    });
    timer = setTimeout(() => { dispose(); rejectIdle(new Error('Controlled turn exceeded 20 seconds')); }, 20000);
  });
  agent.followup(createUserMessage({ content: [{ type: 'text', text: 'Controlled runtime compatibility probe; no production task.' }], source: { kind: 'user' } }));
  await idle;
  clearTimeout(timer);
  await app.ctx.sessions.flush(agent.session);
  const events = agent.session.snapshotEvents();
  const end = events.findLast(event => event.type === 'turn/end');
  const guardCount = events.filter(event => event.type === 'user/message'
    && event.data.source.kind === 'repeat-tool-reminder').length;
  const starts = events.filter(event => event.type === 'tool/call');
  const results = events.filter(event => event.type === 'tool/result');
  if (end?.data.reason.kind !== 'completed' || guardCount !== 1
    || starts.length !== (mode === 'unknown' ? 3 : 4)
    || results.length !== starts.length || results.some(event => event.data.message.isError)
    || !receipts.some(item => item.structuredReminderCount > 0)) {
    throw new Error('The real runtime did not produce the required controlled guard path');
  }
  const text = await readSessionLogText(app.ctx.sessionPersistence, agent.session.id);
  if (!text) throw new Error('Harness persistence returned no session log');
  await writeFile(join(artifactRoot, `${mode}.jsonl`), text, { mode: 0o600, flag: 'wx' });
  const deps = { sessionQuery: app.ctx.sessionQuery, sessionPersistence: app.ctx.sessionPersistence,
    attachments: app.ctx.attachments, sessions: app.ctx.sessions };
  const stream = streamSessionLogZip(deps, text, agent.session.id, false, 6, new AbortController().signal);
  await writeFile(join(artifactRoot, `${mode}.zip`), Buffer.from(await new Response(stream).arrayBuffer()), { mode: 0o600, flag: 'wx' });
  await writeFile(join(artifactRoot, `${mode}-receipts.json`), JSON.stringify(receipts, null, 2), { mode: 0o600, flag: 'wx' });
  exitCode = 0;
  console.log(JSON.stringify({ harnessVersion: installedVersion, mode, scriptedResponses: receipts.length, responsesSeeingGuard: receipts.filter(item => item.structuredReminderCount > 0).length, provenance: 'real Harness runtime, scripted model, no provider inference' }));
} finally {
  clearTimeout(timer);
  if (app) await app.shutdown.shutdown(exitCode);
}
