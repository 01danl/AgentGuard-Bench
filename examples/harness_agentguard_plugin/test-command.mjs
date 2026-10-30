// End-to-end smoke test for the local /agentguard command plugin.
// Boots the installed Harness, creates one Agent, exercises command inputs,
// and exits nonzero unless the real command registry returns the expected results.
import { createRequire } from 'node:module';
import { copyFile, mkdtemp, mkdir, readFile, writeFile } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { join, resolve } from 'node:path';
import { pathToFileURL } from 'node:url';

const packageRoot = process.env.AGENTGUARD_DSH_PACKAGE_ROOT;
if (!packageRoot) throw new Error('AGENTGUARD_DSH_PACKAGE_ROOT is required');
const require = createRequire(join(packageRoot, 'package.json'));
const load = (name) => import(pathToFileURL(require.resolve(name)).href);
const { LlmAdapter } = await load('@deepseek-ai/dsh-llm');
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
const root = await mkdtemp(join(tmpdir(), 'agentguard-command-'));
const home = join(root, 'home');
const workspace = join(root, 'workspace');
await mkdir(home);
await mkdir(workspace);

const basePatch = await readFile(resolve(repo, 'examples/harness_guard_probe/probe.patch.yml'), 'utf8');
const patch = join(root, 'plugin.patch.yml');
await writeFile(patch, `${basePatch}\n- insert:\n    - id: agentguard-command-test\n      name: ${JSON.stringify(plugin)}\n`);

process.env.DSH_HOME = home;
process.env.HOME = home;
process.env.AGENTGUARD_BIN = cli;

class NoopAdapter extends LlmAdapter {
  async resolveModel(provider, model) {
    return { provider, id: model, name: 'Noop adapter; model calls are forbidden' };
  }
  async *stream() {
    throw new Error('The command smoke test must not invoke the model');
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
  app.ctx.llm.registerAdapter(['agentguard-noop'], new NoopAdapter());
  const agent = await app.ctx.agentLoop.create(
    SessionId('agentguard-command-test'),
    { provider: 'agentguard-noop', model: 'noop', reasoningEffort: 'off' },
    { cwd: workspace },
  );

  const run = (line) => app.ctx.commands.execute(agent, line, [], new AbortController().signal);

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

  const noArgs = await run('/agentguard');
  if (noArgs?.result.kind !== 'error' || !noArgs.result.text.includes('Usage:')) {
    throw new Error(`expected usage, got ${JSON.stringify(noArgs)}`);
  }

  await app.ctx.sessions.flush(agent.session);
  exitCode = 0;
  console.log(JSON.stringify({
    harnessVersion: installedVersion,
    plugin,
    fixture,
    command: 'agentguard',
    success: true,
    result: ok.result.text.split('\n').slice(0, 5),
  }, null, 2));
} finally {
  if (app) await app.shutdown.shutdown(exitCode);
  console.log(`Temporary test root: ${root}`);
}
if (exitCode !== 0) process.exitCode = 1;
