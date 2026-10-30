import test from 'node:test';
import assert from 'node:assert/strict';
import { apply, parseRequest, tokenize } from './agentguard.mjs';

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

function registered(config) {
  let definition;
  apply({
    commands: {
      register(value) {
        definition = value;
      },
    },
  }, config);
  return definition;
}

test('rejects explicitly invalid executable values', () => {
  for (const executable of [123, null, false, '', '   ']) {
    assert.throws(() => registered({ executable }), /executable must be a non-empty string/u);
  }
});

test('bounds timeoutMs to the Node timer limit', () => {
  assert.equal(registered({ timeoutMs: 2147483647 }).name, 'agentguard');
  assert.throws(
    () => registered({ timeoutMs: 2147483648 }),
    /timeoutMs must be a positive safe integer no greater than 2147483647/u,
  );
  assert.throws(() => registered({ timeoutMs: 0 }), /timeoutMs/u);
  assert.throws(() => registered({ maxOutputBytes: 0 }), /maxOutputBytes/u);
});
