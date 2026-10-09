const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');

const html = fs.readFileSync(path.resolve(__dirname, '../../www/scanner/index.html'), 'utf8');
const scripts = [...html.matchAll(/<script(?:\s[^>]*)?>([\s\S]*?)<\/script>/gi)];
const appScript = scripts.at(-1)?.[1];
assert.ok(appScript, 'main inline app script exists');

function harness(hash = '', session = null, validate = async () => ({name:'PL-1',scans:[],items:[]})) {
  const classes = new Set(['hidden']);
  const elements = new Map();
  const listeners = new Map();
  const element = (id) => {
    if (!elements.has(id)) elements.set(id, {
      id, classList: { add: (...names) => names.forEach(n => classes.add(id + ':' + n)), remove: (...names) => names.forEach(n => classes.delete(id + ':' + n)), toggle: (name, force) => { const key=id+':'+name; if (force) classes.add(key); else classes.delete(key); return !!force; }, contains: name => classes.has(id + ':' + name) },
      addEventListener: (name, callback) => { listeners.set(id + ':' + name, callback); },
      setAttribute() {}, replaceChildren() {}, append() {}, focus() {},
      options: [], value: '', textContent: '', innerHTML: '', disabled: false,
      dataset: {}, style: {}, children: [],
    });
    return elements.get(id);
  };
  let currentHash = hash;
  const windowListeners = {};
  let storageWrites = 0;
  const context = {
    document: { cookie: '', getElementById: element, documentElement: { dataset: {} }, querySelector: () => ({ content: '' }), addEventListener() {} },
    window: { frappe: {}, addEventListener: (name, cb) => { windowListeners[name] = cb; } },
    location: { pathname: '/scanner/', search: '', get hash() { return currentHash; }, set hash(value) { currentHash = value.startsWith('#') ? value : '#' + value; windowListeners.hashchange?.(); } },
    history: { replaceState(_state, _title, url) { currentHash = url.slice(url.indexOf('#')); } },
    navigator: {}, localStorage: { getItem: key => key.startsWith('scanner-session-v1:') ? JSON.stringify(session) : null, setItem: () => { storageWrites++; }, removeItem() {} },
    fetch: async (url) => { if (url.includes('frappe.auth')) return { ok: true, json: async () => ({ message: 'user' }) }; return { ok: true, json: async () => ({ message: await validate() }) }; },
    URLSearchParams, Set, Map, JSON, Date, console, setTimeout, clearTimeout,
  };
  for (const id of ['camera-modal', 'source-modal', 'review-modal']) element(id).classList.add('hidden');
  const instrumented = appScript.replace('init();\n})();', `
const originalCall=call;
call=async (method,...args)=>method==='get_setup'?{companies:['C'],purposes:['Material Receipt'],default_company:'C'}:originalCall(method,...args);
fillPurposes=()=>{};fill=()=>{};updateWarehouses=()=>{};updatePurpose=()=>{};updateSourceTypes=()=>{};
render=()=>{};renderPick=()=>{};pickSummary=()=>'';loadPickNames=()=>{};renderDeliveryHistory=()=>{};
window.test = {
 init, saved:()=>savedSession, restoring:()=>restoringSession,
 ready() { sessionUser='test-user';routeReady=true;loadPickNames=()=>{};renderDeliveryHistory=()=>{}; },
 route: setRoute, current: ()=>lastRoute,
 busy(value) { busy=value; }, camera(value) { camera=value; },
 pending(value) { savedSession=value; },
 restore: restoreSession,
 persist: persistSession,
};
})();`);
  vm.runInNewContext(instrumented, context);
  return { elements, listeners, windowListeners, api: context.window.test,
    browserHash(value) { currentHash=value;windowListeners.hashchange?.(); },
    get hash() { return currentHash; }, get storageWrites() { return storageWrites; } };
}

test('app script is valid JavaScript and binds routing to navigation controls', () => {
  assert.doesNotThrow(() => new vm.Script(appScript));
  const app = harness();
  for (const route of ['stock', 'pick', 'delivery']) assert.equal(typeof app.listeners.get('choose-' + route + ':click'), 'function');
  assert.equal(typeof app.windowListeners.hashchange, 'function');
});

test('hash changes switch top-level visibility and browser refresh preserves active hash', () => {
  const app = harness('#delivery');
  app.api.ready();
  app.api.route('delivery', true);
  assert.equal(app.api.current(), 'delivery');
  assert.equal(app.hash, '#delivery');
  assert.equal(app.elements.get('delivery').classList.contains('hidden'), false);
  assert.equal(app.elements.get('home').classList.contains('hidden'), true);

  app.api.route('home');
  assert.equal(app.api.current(), 'home');
  assert.equal(app.hash, '#home');
  assert.equal(app.elements.get('home').classList.contains('hidden'), false);
  assert.equal(app.elements.get('delivery').classList.contains('hidden'), true);

  app.browserHash('#pick');
  assert.equal(app.api.current(), 'pick');
  assert.equal(app.elements.get('pick').classList.contains('hidden'), false);
  assert.equal(app.elements.get('home').classList.contains('hidden'), true);
});

test('navigation is blocked and hash is rolled back when scanner operations are busy', () => {
  const app = harness('#stock');
  app.api.ready();
  app.api.route('stock', true);
  app.api.busy(true);

  app.api.route('home');
  assert.equal(app.api.current(), 'stock');
  assert.equal(app.hash, '#stock');

  app.api.busy(false);
  app.api.camera({});
  app.api.route('pick');
  assert.equal(app.api.current(), 'stock');
  assert.equal(app.hash, '#stock');
});

const session = { version: 1, mode: 'stock', time: Date.now(), stock: { rows: [], sourceGuide: null, company: 'C', purpose: 'Material Receipt', source: '', target: '' }, pick: { scans: [] } };

test('init automatically restores saved work on the requested route, even if session mode differs', async () => {
  const app = harness('#pick', session);
  await app.api.init();
  assert.equal(app.api.current(), 'pick');
  assert.equal(app.hash, '#pick');
  assert.equal(app.elements.get('session-banner').classList.contains('hidden'), true);
  assert.equal(app.elements.get('stock').inert, false);
});

for (const route of ['home', 'delivery']) test(`automatic restore preserves explicit #${route}`, async () => {
  const app = harness('#'+route, session);
  await app.api.init();
  assert.equal(app.api.current(), route);
  assert.equal(app.hash, '#'+route);
  assert.equal(app.api.saved(), null);
});

test('requested page renders before server validation resolves', async () => {
  let resolveValidation;
  let started;
  const validationStarted = new Promise(resolve => { started=resolve; });
  const pending = new Promise(resolve => { resolveValidation=resolve; });
  const app = harness('#pick', {...session, pick:{scans:[],draft:{name:'PL-1'}}}, () => {started();return pending;});
  const initialization=app.api.init();
  await validationStarted;
  assert.equal(app.api.current(), 'pick');
  assert.equal(app.elements.get('pick').classList.contains('hidden'), false);
  assert.equal(app.elements.get('pick').inert, true);
  assert.equal(app.api.restoring(), true);
  assert.equal(app.elements.get('restore-session').classList.contains('hidden'), true);
  assert.match(app.elements.get('session-info').textContent, /Memeriksa/);
  resolveValidation({name:'PL-1',scans:[],items:[]});
  await initialization;
  assert.equal(app.api.saved(), null);
  assert.equal(app.elements.get('pick').inert, false);
});

test('without a hash, session mode selects the route on refresh', async () => {
  const app = harness('', session);
  await app.api.init();
  assert.equal(app.api.current(), 'stock');
  assert.equal(app.hash, '#stock');
});

test('failed automatic restore keeps requested page visible and saved data protected', async () => {
  const needsValidation = { ...session, pick: { scans: [], draft: { name: 'PL-1', modified: 'old' } } };
  const app = harness('#stock', needsValidation, async () => { throw new Error('Server unreachable'); });
  await app.api.init();
  assert.equal(app.api.current(), 'stock');
  assert.equal(app.elements.get('stock').classList.contains('hidden'), false);
  assert.equal(app.elements.get('stock').inert, true);
  assert.equal(app.elements.get('session-banner').classList.contains('hidden'), false);
  assert.match(app.elements.get('session-info').textContent, /Server unreachable/);
  assert.ok(app.api.saved());
  app.api.persist();
  assert.equal(app.storageWrites, 0);
});



