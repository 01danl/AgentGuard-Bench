import test from 'node:test';
import assert from 'node:assert/strict';
import { parseRequest, tokenize } from './agentguard.mjs';

test('tokenizes quoted POSIX paths with literal backslashes', () => {
  assert.deepEqual(tokenize('"folder with space/session\\copy.jsonl"'), [
    'folder with space/session\\copy.jsonl',
  ]);
  assert.deepEqual(tokenize('"folder with space/session\\\\copy.jsonl"'), [
    'folder with space/session\\copy.jsonl',
  ]);
  assert.deepEqual(tokenize("'folder with space/session\\copy.jsonl'"), [
    'folder with space/session\\copy.jsonl',
  ]);
});

test('tokenizes escaped double quotes and rejects unterminated quotes', () => {
  assert.deepEqual(tokenize('"session\\"copy.jsonl"'), ['session"copy.jsonl']);
  assert.throws(() => tokenize('"unterminated'), /unterminated quote/u);
});

test('parses optional current-session path and window', () => {
  assert.deepEqual(parseRequest(''), { path: undefined, window: 5 });
  assert.deepEqual(parseRequest('--window 7'), { path: undefined, window: 7 });
  assert.deepEqual(parseRequest('"session copy.jsonl" --window 3'), {
    path: 'session copy.jsonl',
    window: 3,
  });
  assert.match(parseRequest('--window 0').error, /--window/u);
  assert.match(parseRequest('a.jsonl b.jsonl').error, /Usage:/u);
});
