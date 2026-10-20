// Execute production functions with isolated dependencies; never contact storage.
const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const crypto = require('node:crypto');
const read = file => fs.readFileSync(path.join(__dirname, file), 'utf8');
const html = read('vercel_frontdoor/index.html');
const start = html.indexOf('      const TUS_VERSION');
const end = html.indexOf('      async function requestUploadTicket', start);
assert.ok(start >= 0 && end > start, 'production upload functions must be present');
const uploadSource = html.slice(start, end);

function harness({ patchOffset, headOffset, lostPatch = 0 } = {}) {
  const ranges = [], progress = [];
  let patches = 0, calls = 0;
  const reply = headers => ({ ok: true, status: 204, headers: { get: key => headers[key] ?? null } });
  const fetch = async (_url, options) => {
    assert.ok(++calls <= 40, 'upload retries must be bounded');
    if (options.method === 'POST') return reply({ Location: '/upload/mock' });
    if (options.method === 'HEAD') return reply({ 'Upload-Offset': headOffset });
    assert.equal(options.method, 'PATCH');
    ranges.push([options.body.start, options.body.end]);
    assert.equal(options.headers['Upload-Offset'], String(options.body.start));
    if (++patches === lostPatch) throw new Error('Simulated lost PATCH response');
    return reply({ 'Upload-Offset': patchOffset === undefined ? String(options.body.end) : patchOffset });
  };
  const context = vm.createContext({ fetch, URL, TextEncoder, btoa, setTimeout: callback => callback() });
  vm.runInContext(uploadSource, context);
  const file = { size: 10, name: 'mock.wav', type: 'audio/wav', slice: (start, end) => ({ start, end, size: end - start }) };
  return { ranges, progress, run: () => context.uploadTusFile(file,
    { token: 'fixture', path: 'mock.wav' },
    { endpoint: 'https://storage.invalid/upload', bucket: 'fixture', chunkSize: 6 },
    bytes => progress.push(bytes)) };
}

test('normal upload sends each byte exactly once', async () => {
  const h = harness();
  assert.equal((await h.run()).size, 10);
  assert.deepEqual(h.ranges, [[0, 6], [6, 10]]);
  assert.deepEqual(h.progress, [6, 10]);
});

test('lost PATCH response resumes from the confirmed offset', async t => {
  for (const offset of ['0', '3', '6']) await t.test(`offset ${offset}`, async () => {
    const h = harness({ lostPatch: 1, headOffset: offset });
    await h.run();
    const expected = offset === '0' ? [[0, 6], [0, 6], [6, 10]]
      : offset === '3' ? [[0, 6], [3, 9], [9, 10]] : [[0, 6], [6, 10]];
    assert.deepEqual(h.ranges, expected);
    assert.equal(h.progress.at(-1), 10);
  });
});

test('invalid offsets cannot manufacture upload completion', async t => {
  for (const value of [null, '', '-1', '1.5', 'NaN', 'Infinity', '1e1', '999', '9007199254740993']) {
    await t.test(`offset ${JSON.stringify(value)}`, async () => {
      const h = harness({ patchOffset: value, headOffset: value });
      await assert.rejects(h.run(), /offset/i);
      assert.deepEqual(h.progress, []);
      assert.equal(h.ranges.length, 5);
    });
  }
  await t.test('HEAD cannot jump beyond submitted bytes', async () => {
    const h = harness({ patchOffset: '10', headOffset: '10' });
    await assert.rejects(h.run(), /offset/i);
    assert.deepEqual(h.progress, []);
  });
  await t.test('HEAD cannot rewind an acknowledged chunk', async () => {
    const h = harness({ lostPatch: 2, headOffset: '0' });
    await h.run();
    assert.deepEqual(h.ranges, [[0, 6], [6, 10], [6, 10]]);
    assert.deepEqual(h.progress, [6, 10]);
  });
});

test('unauthorized queue requests have no storage or job side effects', async t => {
  const auth = read('vercel_frontdoor/api/_upload-auth.js')
    .replace(/^import .*;\n/gm, '').replace(/export function /g, 'function ');
  const queue = read('vercel_frontdoor/api/queue-job.js')
    .replace(/^import .*;\n/gm, '').replace('export const config', 'const config')
    .replace('export default async function handler', 'async function handler');
  for (const [name, env, authorization] of [
    ['missing bearer', { UPLOAD_ACCESS_TOKEN: 'fixture-secret' }, ''],
    ['wrong bearer', { UPLOAD_ACCESS_TOKEN: 'fixture-secret' }, 'Bearer fixture-wrong!'],
    ['unconfigured server', {}, 'Bearer fixture-secret'],
  ]) await t.test(name, async () => {
    let calls = 0, response;
    const unexpected = () => { calls++; throw new Error('Unexpected storage or job access'); };
    const context = vm.createContext({
      Buffer, process: { env }, createHash: crypto.createHash, timingSafeEqual: crypto.timingSafeEqual,
      storageConfig: () => ({ provider: 'supabase' }),
      createJob: unexpected, getJob: unexpected, updateJob: unexpected, uploadObject: unexpected,
    });
    vm.runInContext(auth + '\n' + queue, context);
    const res = { setHeader() {}, end: value => { response = JSON.parse(value); } };
    await context.handler({ method: 'POST', headers: { authorization }, body: {
      permission: true, text: 'Fixture', qualityTarget: 'draft', files: [{ data: 'YQ==', size: 1 }],
    } }, res);
    assert.equal(res.statusCode, 401);
    assert.equal(response.ok, false);
    assert.equal(calls, 0);
  });
});

test('all inline browser scripts parse', () => {
  const scripts = [...html.matchAll(/<script\b[^>]*>([\s\S]*?)<\/script>/gi)];
  assert.ok(scripts.length > 0);
  for (const [index, match] of scripts.entries()) new vm.Script(match[1], { filename: `inline-${index}.js` });
});

test('browser smoke gate treats syntax errors as actionable', () => {
  const filter = read('.github/workflows/full-quality.yml').split('\n')
    .find(line => line.includes('const actionableErrors ='));
  assert.ok(filter, 'browser smoke error gate must be present');
  const errors = ['SyntaxError: Invalid or unexpected token', 'TypeError: broken handler'];
  assert.equal(vm.runInNewContext(filter.trim() + '\nactionableErrors.length', { errors }), errors.length);
});
