// AgentGuard command plugin: analyze a durable Harness v4 log from inside DSH.
//
// This module is a local DSH plugin, not part of the Python package. It registers
// one human command and runs the offline `agentguard` CLI. It never injects a
// guard reminder and never opens the network.
import { execFile } from 'node:child_process';
import { access, stat } from 'node:fs/promises';
import { constants } from 'node:fs';
import { resolve } from 'node:path';
import { parseArgs, promisify } from 'node:util';

const execFileAsync = promisify(execFile);
const DEFAULT_WINDOW = 5;
const MAX_WINDOW = 1000;
const MAX_OUTPUT_BYTES = 2 * 1024 * 1024;
const DEFAULT_TIMEOUT_MS = 15000;

export const name = 'agentguard-command';
export const inject = ['commands'];

function usage() {
  return 'Usage: /agentguard <session.jsonl|export.zip> [--window N]';
}

function failure(text) {
  return { kind: 'error', text };
}

/** Split one command line while preserving quoted paths; malformed quotes are rejected. */
function tokenize(rawInput) {
  const tokens = [];
  let current = '';
  let quote;
  let escaped = false;
  for (let index = 0; index < rawInput.length; index += 1) {
    const character = rawInput[index];
    if (escaped) {
      current += character;
      escaped = false;
      continue;
    }
    if (quote !== undefined) {
      if (character === quote) quote = undefined;
      else if (character === '\\' && quote === '"') escaped = true;
      else current += character;
      continue;
    }
    if (character === '"' || character === "'") {
      quote = character;
      continue;
    }
    if (character === '\\') {
      const next = rawInput[index + 1];
      if (next !== undefined && (next === '\\' || next === '"' || next === "'" || /\s/u.test(next))) {
        escaped = true;
      } else {
        current += character;
      }
      continue;
    }
    if (/\s/u.test(character)) {
      if (current.length > 0) {
        tokens.push(current);
        current = '';
      }
      continue;
    }
    current += character;
  }
  if (escaped) current += '\\';
  if (quote !== undefined) throw new Error('unterminated quote');
  if (current.length > 0) tokens.push(current);
  return tokens;
}

function parseRequest(rawInput) {
  let parsed;
  try {
    parsed = parseArgs({
      args: tokenize(rawInput.trim()),
      options: { window: { type: 'string', short: 'w' } },
      allowPositionals: true,
      strict: true,
    });
  } catch {
    return { error: usage() };
  }
  if (parsed.positionals.length !== 1) return { error: usage() };
  const rawWindow = parsed.values.window ?? String(DEFAULT_WINDOW);
  if (!/^\d+$/u.test(rawWindow)) return { error: '--window must be a positive integer.\n' + usage() };
  const window = Number(rawWindow);
  if (!Number.isSafeInteger(window) || window < 1 || window > MAX_WINDOW) {
    return { error: `--window must be between 1 and ${MAX_WINDOW}.\n${usage()}` };
  }
  return { path: parsed.positionals[0], window };
}

function outputText(value) {
  const text = String(value ?? '').trim();
  return text.length === 0 ? 'AgentGuard returned no output.' : text;
}

function commandFailure(error, timeoutMs) {
  if (error?.name === 'AbortError') return 'AgentGuard request was cancelled.';
  if (error?.killed === true || error?.signal === 'SIGTERM') {
    return `AgentGuard exceeded its ${timeoutMs} ms limit.`;
  }
  if (error?.code === 'ENOENT') {
    return 'AgentGuard executable was not found. Install it and/or set AGENTGUARD_BIN.';
  }
  const detail = String(error?.stderr ?? '').trim();
  if (detail.length > 0) return `AgentGuard failed:\n${detail.slice(0, 4000)}`;
  return `AgentGuard failed (${String(error?.code ?? error?.name ?? 'unknown error')}).`;
}

export function apply(ctx, config = {}) {
  const executable = typeof config.executable === 'string' && config.executable.length > 0
    ? config.executable
    : (process.env.AGENTGUARD_BIN || 'agentguard');
  const timeoutMs = Number.isSafeInteger(config.timeoutMs) && config.timeoutMs > 0
    ? config.timeoutMs
    : DEFAULT_TIMEOUT_MS;

  ctx.commands.register({
    name: 'agentguard',
    description: 'Analyze a Harness v4 session log or ZIP with AgentGuard (offline)',
    input: { hint: '<session.jsonl|export.zip> [--window N]' },
    handler: async (invocation) => {
      const request = parseRequest(invocation.rawInput);
      if (request.error !== undefined) return failure(request.error);

      const session = invocation.agent?.session;
      const sessionCwd = session?.header?.cwd ?? session?.cwd;
      const cwd = typeof sessionCwd === 'string' && sessionCwd.length > 0 ? sessionCwd : process.cwd();
      const target = resolve(cwd, request.path);
      if (!/\.(jsonl|zip)$/iu.test(target)) {
        return failure('Expected a .jsonl session log or .zip export.\n' + usage());
      }
      try {
        const info = await stat(target);
        if (!info.isFile()) return failure(`Not a file: ${target}`);
        await access(target, constants.R_OK);
      } catch {
        return failure(`Cannot read: ${target}`);
      }

      try {
        const { stdout } = await execFileAsync(
          executable,
          ['analyze', target, '--window', String(request.window), '--format', 'text'],
          {
            cwd,
            env: {
              PATH: process.env.PATH ?? '',
              HOME: process.env.HOME ?? '',
              LANG: process.env.LANG ?? 'C.UTF-8',
            },
            timeout: timeoutMs,
            maxBuffer: MAX_OUTPUT_BYTES,
            encoding: 'utf8',
            windowsHide: true,
            signal: invocation.signal,
          },
        );
        return { kind: 'success', text: outputText(stdout) };
      } catch (error) {
        return failure(commandFailure(error, timeoutMs));
      }
    },
  });
}
