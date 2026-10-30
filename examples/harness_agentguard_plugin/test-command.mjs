// End-to-end smoke test for the local /agentguard command plugin.
// Boots the installed Harness, creates one Agent, exercises command inputs,
// and exits nonzero unless the real command registry returns the expected results.
import { randomUUID } from 'node:crypto';
import { createRequire } from 'node:module';
import { copyFile, mkdtemp, mkdir, readFile, writeFile } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { join, resolve } from 'node:path';
import { pathToFileURL } from 'node:url';

const packageRoot = process.env.AGENTGUARD_DSH_PACKAGE_ROOT;
if (!packageRoot) throw new Error('AGENTGUARD_DSH_PACKAGE_ROOT is required');
const require = createRequire(join(packageRoot, 'package.json'));
const load = (name) => import(pathToFileURL(require.resolve(name)).href);
const { LlmAdapter, createUserMessage } = await load('@deepseek-ai/dsh-llm');
const { SessionId } = await load('@deepseek-ai/dsh-session');
const { createLaunchEnvironmentSnapshot } = await load('@deepseek-ai/dsh-launch-environment');
const { runProfile } = await import(pathToFileURL(join(packageRoot, 'lib/profile-boot.js')).href);

const installedVersion = require(join(packageRoot, 'package.json')).version;
if (installedVersion !== '0.2.1-rc.2') {
  throw new Error(`This smoke test is verified only with dsh 0.2.1-rc.2 (found ${installedVersion})`);
}

const repo = process.cwd();
const fixture = resolve(repo, 'examples/synthetic-session.jsonl');
const cli = resolve(repo, '.venv/bin/agentguard');
const plugin = resolve(repo, 'examples/harness_agentguard_plugin/agentguard.mjs');
const installedHome = process.env.AGENTGUARD_INSTALLED_DSH_HOME;
const root = await mkdtemp(join(tmpdir(), 'agentguard-command-'));
const workspace = join(root, 'workspace');
await mkdir(workspace);
await writeFile(join(workspace, 'probe.txt'), 'PLUGIN_PROBE\n');

let patch;
if (installedHome !== undefined) {
  const userHome = join(root, 'user-home');
  await mkdir(userHome);
  patch = resolve(repo, 'examples/harness_guard_probe/probe.patch.yml');
  process.env.DSH_HOME = installedHome;
  process.env.HOME = userHome;
} else {
  const home = join(root, 'home');
  await mkdir(home);
  const basePatch = await readFile(resolve(repo, 'examples/harness_guard_probe/probe.patch.yml'), 'utf8');
  patch = join(root, 'plugin.patch.yml');
  await writeFile(patch, `${basePatch}\n- insert:\n    - id: agentguard-command-test\n      name: ${JSON.stringify(plugin)}\n`);
  process.env.DSH_HOME = home;
  process.env.HOME = home;
}
process.env.AGENTGUARD_BIN = cli;

class ScriptedAdapter extends LlmAdapter {
  calls = 0;
  async resolveModel(provider, model) {
    return {
      provider,
      id: model,
      name: 'Scripted plugin smoke adapter; no provider inference',
      reasoning: { efforts: [{ id: 'off', name: 'Off' }], defaultEffort: 'off' },
    };
  }
  async *stream() {
    this.calls += 1;
    if (this.calls === 1) {
      const args = JSON.stringify({ file_path: 'probe.txt' });
      yield { type: 'block-start', index: 0, blockType: 'tool-call' };
      yield { type: 'tool-call-delta', index: 0, id: 'plugin-read-1', name: 'read', argumentsDelta: args };
      yield { type: 'block-end', index: 0, block: { type: 'tool-call', id: 'plugin-read-1', name: 'read', arguments: args } };
      yield { type: 'finish', reason: { kind: 'tool-calls' } };
      return;
    }
    yield { type: 'block-start', index: 0, blockType: 'text' };
    yield { type: 'text-delta', index: 0, text: 'PLUGIN_PROBE' };
    yield { type: 'block-end', index: 0, block: { type: 'text', text: 'PLUGIN_PROBE' } };
    yield { type: 'finish', reason: { kind: 'stop' } };
  }
}

const environment = createLaunchEnvironmentSnapshot([{ source: 'process', values: { ...process.env } }]);
let app;
let exitCode = 1;
try {
  app = await runProfile({
    environment,
    profile: 'headless',
    patchFiles: [patch],
    args: ['agentguard command smoke test'],
  });
  const adapter = new ScriptedAdapter();
  app.ctx.llm.registerAdapter(['agentguard-scripted'], adapter);
  const agent = await app.ctx.agentLoop.create(
    SessionId(`agentguard-command-test-${randomUUID()}`),
    { provider: 'agentguard-scripted', model: 'scripted', reasoningEffort: 'off' },
    { cwd: workspace },
  );

  const idle = new Promise((resolveIdle, rejectIdle) => {
    const timer = setTimeout(() => {
      dispose();
      rejectIdle(new Error('scripted turn exceeded 20 seconds'));
    }, 20000);
    const dispose = app.ctx.on('agent/status', ({ agent: current, status }) => {
      if (current === agent && status === 'idle') {
        clearTimeout(timer);
        dispose();
        resolveIdle();
      }
    });
  });
  agent.followup(createUserMessage({
    content: [{ type: 'text', text: 'Read probe.txt and reply with its content.' }],
    source: { kind: 'user' },
  }));
  await idle;
  await app.ctx.sessions.flush(agent.session);

  const run = (line) => app.ctx.commands.execute(agent, line, [], new AbortController().signal);

  const current = await run('/agentguard');
  if (current?.result.kind !== 'success') {
    throw new Error(`expected current-session analysis, got ${JSON.stringify(current)}`);
  }
  if (!current.result.text.includes('Sessions: 1') || !current.result.text.includes('Tool calls: 1')) {
    throw new Error(`current-session report was unexpected: ${current.result.text}`);
  }

  const ok = await run(`/agentguard ${fixture} --window 5`);
  if (ok?.result.kind !== 'success') throw new Error(`expected success, got ${JSON.stringify(ok)}`);
  if (!ok.result.text.includes('Sessions: 1')) throw new Error('report did not include the session count');
  if (!ok.result.text.includes('Tool calls: 5')) throw new Error('report did not include the tool-call count');
  if (!ok.result.text.includes('Guard seq 20: IGNORED')) throw new Error('report did not include the guard incident');

  const spacedDir = join(root, 'folder with space');
  const spacedFixture = join(spacedDir, 'session copy.jsonl');
  await mkdir(spacedDir);
  await copyFile(fixture, spacedFixture);
  const quoted = await run(`/agentguard "${spacedFixture}" --window 5`);
  if (quoted?.result.kind !== 'success' || !quoted.result.text.includes('Sessions: 1')) {
    throw new Error(`expected a quoted spaced path to succeed, got ${JSON.stringify(quoted)}`);
  }

  if (process.platform !== 'win32') {
    // POSIX filenames may contain literal backslashes and double quotes.
    const backslashFixture = join(spacedDir, 'session\\copy.jsonl');
    await copyFile(fixture, backslashFixture);
    const quoteFixture = join(spacedDir, 'session"copy.jsonl');
    await copyFile(fixture, quoteFixture);
    for (const rawPath of [
      `"${backslashFixture}"`,
      `"${backslashFixture.replaceAll('\\', '\\\\')}"`,
      `'${backslashFixture}'`,
      `"${quoteFixture.replaceAll('"', '\\"')}"`,
    ]) {
      const result = await run(`/agentguard ${rawPath} --window 5`);
      if (result?.result.kind !== 'success' || !result.result.text.includes('Sessions: 1')) {
        throw new Error(`expected quoted special characters to survive, got ${JSON.stringify(result)}`);
      }
    }
  }

  const relativeFixture = join(workspace, 'relative-session.jsonl');
  await copyFile(fixture, relativeFixture);
  const relative = await run('/agentguard relative-session.jsonl --window 5');
  if (relative?.result.kind !== 'success' || !relative.result.text.includes('Sessions: 1')) {
    throw new Error(`expected the session cwd to resolve a relative path, got ${JSON.stringify(relative)}`);
  }

  const missing = await run('/agentguard /definitely/not/a/session.jsonl');
  if (missing?.result.kind !== 'error' || !missing.result.text.includes('Cannot read')) {
    throw new Error(`expected a missing-file error, got ${JSON.stringify(missing)}`);
  }

  const badWindow = await run(`/agentguard ${fixture} --window 0`);
  if (badWindow?.result.kind !== 'error' || !badWindow.result.text.includes('--window')) {
    throw new Error(`expected a window error, got ${JSON.stringify(badWindow)}`);
  }

  await app.ctx.sessions.flush(agent.session);
  exitCode = 0;
  console.log(JSON.stringify({
    harnessVersion: installedVersion,
    plugin: installedHome === undefined ? plugin : `installed package in ${installedHome}`,
    fixture,
    installedMode: installedHome !== undefined,
    command: 'agentguard',
    success: true,
    currentSession: current.result.text.split('\n').slice(0, 5),
    external: ok.result.text.split('\n').slice(0, 5),
  }, null, 2));
} finally {
  if (app) await app.shutdown.shutdown(exitCode);
  console.log(`Temporary test root: ${root}`);
}
if (exitCode !== 0) process.exitCode = 1;
