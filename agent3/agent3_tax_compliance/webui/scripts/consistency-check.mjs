// Pure client contract tests. No browser, live server, workspace or account writes.
import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { createHash } from 'node:crypto';
import { money, compareDecimal, state, decisionContext, decide, api, beginPage } from '../src/core.js';

assert.equal(money('9007199254740993'), '9.007.199.254.740.993 đ');
assert.equal(money('-1234.50'), '-1.234,5 đ');
assert.equal(money(null), '—');
assert.equal(compareDecimal('9007199254740993', '9007199254740992'), 1);
assert.equal(compareDecimal('-1.05', '-1.050'), 0);
assert.equal(compareDecimal('-0.1', '0'), -1);

state.ws = 'temporary-a'; state.platform = {profile_revision:'revision-a'};
state.report = {meta:{report_revision:'report-a'}};
const writes = []; let lost = true;
globalThis.fetch = async (path, opts) => {
  if (opts.method === 'POST') {
    assert.equal(opts.headers.get('If-Match'), '"events-a"');
    const body = JSON.parse(opts.body); writes.push(body);
    if (lost) { lost = false; throw new Error('Synthetic lost response'); }
    return Response.json({saved:true, report_pending:false});
  }
  return Response.json({events:[]}, {headers:{ETag:'"events-a"'}});
};
const context = await decisionContext();
const body = {invoice_key:'invoice-a', action:'NOT_CLAIMED', evidence:'Synthetic', by:'Test'};
await assert.rejects(decide('/api/workspaces/temporary-a/decisions', body, context));
await decide('/api/workspaces/temporary-a/decisions', body, context);
assert.equal(writes[0].request_id, writes[1].request_id);
assert.equal(writes[1].report_revision, 'report-a');
state.ws = 'temporary-b'; state.platform.profile_revision = 'revision-b';
await assert.rejects(decide('/api/workspaces/temporary-b/decisions', body, context));
assert.equal(writes.length, 2);
let release;
globalThis.fetch = () => new Promise(resolve => { release = () => resolve(Response.json({old:true})); });
const pending = api('/api/test-delayed'); beginPage(); release();
await assert.rejects(pending, {name:'AbortError'});
console.log('PASS exact money, decimal sorting, decision preconditions, idempotent retry, company boundary and stale response cancellation');

const build = fileURLToPath(new URL('../../src/assistant/static/', import.meta.url));
const html = fs.readFileSync(path.join(build, 'index.html'), 'utf8');
const local = [...html.matchAll(/(?:src|href)="(\/assets\/[^"?]+)(?:\?v=([a-f0-9]+))?"/g)];
assert.ok(local.length >= 5);
for (const [, name, hash] of local) {
  const bytes = fs.readFileSync(path.join(build, name));
  if (hash) assert.equal(createHash('sha256').update(bytes).digest('hex').slice(0, hash.length), hash);
}
for (const css of ['platform-theme.css', 'agent3-product.css', ...fs.readdirSync(path.join(build, 'assets')).filter(n => /^index-.*\.css$/.test(n))]) {
  const text = fs.readFileSync(path.join(build, 'assets', css), 'utf8');
  for (const [, url] of text.matchAll(/url\(["']?(\/assets\/[^)'"?]+)["']?\)/g)) assert.ok(fs.existsSync(path.join(build, url)), url);
}
assert.ok(html.indexOf('/assets/agent3-product.css') > html.indexOf('/assets/platform-theme.css'));
assert.deepEqual(fs.readFileSync(path.join(build, 'assets/agent3-product.css')), fs.readFileSync(new URL('../src/product.css', import.meta.url)));
console.log('PASS build assets, content hashes, local fonts and Agent 3 stylesheet order');
