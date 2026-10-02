'use strict';
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');

const root = path.resolve(__dirname, '../..');
const response = value => ({ok:true, json:async () => structuredClone(value)});
const deferred = () => { let resolve; const promise = new Promise(done => { resolve = done; }); return {promise, resolve}; };
const tick = () => new Promise(resolve => setImmediate(resolve));
const metadata = (revision, overrides = {}) => ({configured:true, provider:'deepseek', api_base:'https://api.deepseek.com', model:'deepseek-flash', source:'local', revision, ...overrides});

function environment(initial = metadata('initial')) {
  let active = structuredClone(initial), requestHook = null, nonce = 0;
  const documentHandlers = new Map(), windowHandlers = new Map(), nodes = new Map();
  const storage = new Map(), calls = [], timers = new Set();
  const fieldIds = ['provider','api-base','model','api-key'];
  const add = (handlers, type, listener) => handlers.set(type, [...(handlers.get(type) || []), listener]);
  const node = selector => {
    if (!nodes.has(selector)) {
      const classes = new Set(), handlers = new Map();
      nodes.set(selector, {
        value:'', textContent:'', hidden:true, disabled:false, required:false, dataset:{}, attributes:{}, handlers,
        addEventListener(type, listener) { add(handlers, type, listener); },
        setAttribute(name, value) { this.attributes[name] = value; },
        classList:{toggle(name, value) { if (value) classes.add(name); else classes.delete(name); }, contains:name => classes.has(name)},
        querySelectorAll() { return [...fieldIds.map(id => node(`#llm-${id}`)), node('#save-llm-config'), node('#remove-llm-config'), node('#use-chinese')]; },
        reportValidity() { return fieldIds.every(id => !node(`#llm-${id}`).required || node(`#llm-${id}`).value.trim()); },
      });
    }
    return nodes.get(selector);
  };
  node('#llm-provider').value = 'deepseek';
  node('#llm-api-base').value = 'https://api.deepseek.com';
  node('#llm-model').value = 'deepseek-flash';
  node('#llm-api-base').required = true;
  node('#llm-model').required = true;
  node('#english').dataset.marketLanguage = 'en';
  node('#use-chinese').dataset.marketLanguage = 'zh';
  const context = {
    console, Promise, Map, Set, JSON, String, Date, Math, AbortController, TypeError,
    CustomEvent:class { constructor(type, options) { this.type = type; this.detail = options.detail; } },
    MutationObserver:class { observe() {} },
    setTimeout(callback, delay) { const timer = setTimeout(callback, delay); timers.add(timer); return timer; },
    clearTimeout, setInterval() {},
    localStorage:{getItem:key => storage.get(key) || null, setItem:(key, value) => storage.set(key, value)},
    document:{hidden:false, documentElement:{lang:'en'}, body:{},
      querySelector:node,
      querySelectorAll(selector) {
        if (selector === '[data-market-language]') return [node('#english'), node('#use-chinese')];
        if (selector === '[data-market-language-status]') return [node('#language-status')];
        return [];
      },
      addEventListener(type, listener) { add(documentHandlers, type, listener); },
    },
    window:{
      addEventListener(type, listener) { add(windowHandlers, type, listener); },
      dispatchEvent(event) { for (const listener of windowHandlers.get(event.type) || []) listener(event); },
    },
    fetch:async (url, options = {}) => {
      assert.equal(url, '/api/llm/config', 'The configuration UI must never call a paid provider');
      const call = {url, method:options.method || 'GET', body:options.body};
      calls.push(call);
      if (requestHook) {
        const intercepted = requestHook(call);
        if (intercepted) return intercepted;
      }
      if (call.method === 'PUT') {
        const body = JSON.parse(call.body);
        active = metadata(`saved-${++nonce}`, {provider:body.provider, api_base:body.api_base, model:body.model});
      } else if (call.method === 'DELETE') {
        active = metadata(`removed-${++nonce}`, {configured:false, source:'none'});
      }
      return response(active);
    },
  };
  vm.createContext(context);
  for (const filename of ['site-language.js', 'market-language.js', 'llm-settings.js']) {
    vm.runInContext(fs.readFileSync(path.join(root, 'app/static/js', filename), 'utf8'), context, {filename});
  }
  const fire = async (element, type, event = {}) => {
    for (const listener of element.handlers.get(type) || []) await listener({target:element, preventDefault() {}, ...event});
  };
  return {
    context, storage, calls, node,
    setActive(value) { active = structuredClone(value); },
    hook(value) { requestHook = value; },
    publish(value) { active = structuredClone(value); context.window.MarketLanguage.configurationChanged(value); },
    input(id, value) { node(`#llm-${id}`).value = value; return fire(node('#llm-settings-form'), 'input'); },
    async changeProvider(value) { node('#llm-provider').value = value; await fire(node('#llm-provider'), 'change'); await fire(node('#llm-settings-form'), 'change'); },
    submit:() => fire(node('#llm-settings-form'), 'submit'),
    remove:() => fire(node('#remove-llm-config'), 'click'),
    async start() { for (const listener of documentHandlers.get('DOMContentLoaded') || []) await listener(); await tick(); },
    close() { for (const timer of timers) clearTimeout(timer); },
  };
}

async function saveResponseRace() {
  const env = environment();
  try {
    await env.start();
    await env.input('model', 'earlier-model');
    await env.input('api-key', 'fixture-secret-never-display');
    const writing = deferred();
    env.hook(call => call.method === 'PUT' ? writing.promise : null);
    const save = env.submit();
    await env.submit();
    assert.equal(env.calls.filter(call => call.method === 'PUT').length, 1, 'Busy forms must reject duplicate submissions');
    assert.equal(JSON.parse(env.calls.find(call => call.method === 'PUT').body).api_key, 'fixture-secret-never-display');
    assert.equal(env.node('#llm-api-key').disabled, true);
    const latest = metadata('newer-tab-write', {model:'latest-model'});
    env.publish(latest);
    assert.equal(env.node('#llm-model').value, 'earlier-model', 'Busy cross-tab updates must preserve the pending form');
    writing.resolve(response(metadata('older-put-response', {model:'earlier-model'})));
    await save;
    assert.equal(env.node('#llm-model').value, 'latest-model');
    assert.equal((await env.context.window.MarketLanguage.getConfiguration()).revision, latest.revision);
    assert.equal(env.node('#llm-api-key').value, '', 'Successful saves must clear the password field');
    assert.equal(env.node('#llm-api-key').disabled, false);
    assert.match(env.node('#llm-settings-result').textContent, /changed by another tab/);
    assert.ok([...env.storage.values()].every(value => !String(value).includes('fixture-secret-never-display')));
    assert.ok([...env.context.document.querySelectorAll('[data-market-language-status]'), env.node('#llm-settings-result'), env.node('#llm-config-source')].every(element => !element.textContent.includes('fixture-secret-never-display')));
  } finally { env.close(); }
}

async function deleteResponseRace() {
  const env = environment();
  try {
    await env.start();
    assert.equal(await env.context.window.MarketLanguage.setLanguage('zh'), true);
    const deleting = deferred();
    env.hook(call => call.method === 'DELETE' ? deleting.promise : null);
    const removal = env.remove();
    await env.remove();
    assert.equal(env.calls.filter(call => call.method === 'DELETE').length, 1);
    const latest = metadata('new-key-after-delete', {model:'latest-model'});
    env.publish(latest);
    deleting.resolve(response(metadata('older-delete-response', {configured:false, source:'none'})));
    await removal;
    assert.equal(env.node('#llm-model').value, 'latest-model');
    assert.equal(env.context.window.MarketLanguage.getLanguage(), 'zh', 'An old DELETE response must not hide a newer configured key');
    assert.equal(env.node('#remove-llm-config').disabled, false);
    assert.match(env.node('#llm-settings-result').textContent, /另一标签页/);
  } finally { env.close(); }
}

async function pendingReadAfterSave() {
  const env = environment();
  try {
    await env.start();
    const reading = deferred();
    let delayed = false;
    env.hook(call => {
      if (call.method === 'GET' && !delayed) { delayed = true; return reading.promise; }
      return null;
    });
    const pending = env.context.window.MarketLanguage.getConfiguration();
    await env.input('model', 'saved-model');
    const save = env.submit();
    await tick();
    assert.equal(env.node('#save-llm-config').disabled, true);
    reading.resolve(response(metadata('initial')));
    await pending;
    await save;
    assert.equal(env.node('#llm-model').value, 'saved-model', 'A successful write needs a fresh authoritative read after any older GET');
    assert.equal(env.calls.filter(call => call.method === 'GET').length, 3);
    assert.match(env.node('#llm-settings-result').textContent, /^Saved and active/);
  } finally { env.close(); }
}

async function environmentFallback() {
  const env = environment();
  try {
    await env.start();
    await env.context.window.MarketLanguage.setLanguage('zh');
    const inherited = metadata('environment-active', {source:'environment'});
    env.hook(call => {
      if (call.method !== 'DELETE') return null;
      env.setActive(inherited);
      return response(inherited);
    });
    await env.remove();
    assert.equal(env.context.window.MarketLanguage.getLanguage(), 'zh');
    assert.equal(env.node('#remove-llm-config').disabled, true);
    assert.match(env.node('#llm-config-source').textContent, /环境变量/);
    assert.match(env.node('#llm-settings-result').textContent, /现使用环境/);
    assert.equal(env.node('#llm-api-key').value, '');
    assert.equal(env.node('#llm-api-key').required, false);
  } finally { env.close(); }
}

async function missingKeyRemoval() {
  const env = environment();
  try {
    await env.start();
    await env.context.window.MarketLanguage.setLanguage('zh');
    await env.remove();
    assert.equal(env.context.window.MarketLanguage.getLanguage(), 'en');
    assert.equal(env.context.document.documentElement.lang, 'en');
    assert.equal(env.node('#llm-api-key').required, true);
    assert.equal(env.node('#remove-llm-config').disabled, true);
    assert.match(env.node('#llm-settings-result').textContent, /English is active/);
    assert.equal(await env.context.window.MarketLanguage.setLanguage('zh'), false);
    assert.equal(env.node('#language-notice').hidden, false);
  } finally { env.close(); }
}

async function dirtyForm() {
  const env = environment();
  try {
    await env.start();
    await env.input('model', 'draft-model');
    await env.input('api-key', 'draft-private-fixture-key');
    env.publish(metadata('outside-update', {provider:'openai-compatible', api_base:'https://api.example.com/v1', model:'outside-model'}));
    assert.equal(env.node('#llm-provider').value, 'deepseek');
    assert.equal(env.node('#llm-api-base').value, 'https://api.deepseek.com');
    assert.equal(env.node('#llm-model').value, 'draft-model');
    assert.equal(env.node('#llm-api-key').value, 'draft-private-fixture-key');
    assert.equal(env.node('#llm-api-key').required, true);
    assert.ok([...env.storage.values()].every(value => !String(value).includes('draft-private-fixture-key')));
    assert.equal(env.calls.filter(call => call.method !== 'GET').length, 0);
  } finally { env.close(); }
}

async function newProviderNeedsKey() {
  const env = environment();
  try {
    await env.start();
    await env.input('api-key', 'draft-fixture-key');
    await env.changeProvider('openai-compatible');
    assert.equal(env.node('#llm-api-key').value, '', 'A provider change must clear the draft key');
    assert.equal(env.node('#llm-api-base').value, '');
    assert.equal(env.node('#llm-model').value, '');
    assert.equal(env.node('#llm-api-key').required, true);
    await env.input('api-base', 'https://api.example.com/v1');
    await env.input('model', 'compatible-model');
    await env.submit();
    assert.equal(env.calls.filter(call => call.method === 'PUT').length, 0, 'An empty key cannot be submitted to a new destination');
    assert.ok([...env.storage.values()].every(value => !String(value).includes('draft-fixture-key')));
  } finally { env.close(); }
}

async function failedMutationPreservesDraft() {
  const env = environment();
  try {
    await env.start();
    await env.input('model', 'draft-model');
    await env.input('api-key', 'retry-fixture-key');
    env.hook(call => call.method === 'PUT' ? {ok:false,json:async () => ({detail:'DeepSeek requires its official HTTPS API base URL.'})} : null);
    await env.submit();
    assert.equal(env.node('#llm-model').value, 'draft-model');
    assert.equal(env.node('#llm-api-key').value, 'retry-fixture-key');
    assert.equal(env.node('#save-llm-config').disabled, false);
    assert.equal(env.node('#llm-settings-result').classList.contains('is-error'), true);
    assert.match(env.node('#llm-settings-result').textContent, /official HTTPS/);
    assert.ok(!env.node('#llm-settings-result').textContent.includes('retry-fixture-key'));
    assert.equal(env.calls.filter(call => call.method === 'GET').length, 1, 'A rejected mutation must not claim success or reconcile a nonexistent write');
  } finally { env.close(); }
}

const tests = {saveResponseRace, deleteResponseRace, pendingReadAfterSave, environmentFallback, missingKeyRemoval, dirtyForm, newProviderNeedsKey, failedMutationPreservesDraft};
(async () => {
  const cases = process.argv[2] ? [process.argv[2]] : Object.keys(tests);
  for (const name of cases) { assert.ok(tests[name], `Unknown settings test: ${name}`); await tests[name](); }
  console.log(`LLM settings checks passed: ${cases.join(', ')}`);
})().catch(error => { console.error(error); process.exitCode = 1; });
