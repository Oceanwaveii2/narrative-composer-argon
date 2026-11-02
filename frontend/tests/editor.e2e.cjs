const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs/promises');
const path = require('node:path');
const os = require('node:os');
const net = require('node:net');
const { spawn } = require('node:child_process');
const { chromium } = require('playwright');

const root = path.resolve(__dirname, '..', '..');
const fixture = path.join(root, 'narrative_composer', 'tests', 'fixtures', 'recovery_project');
const pause = ms => new Promise(resolve => setTimeout(resolve, ms));

async function freePort() {
  return new Promise((resolve, reject) => {
    const server = net.createServer();
    server.once('error', reject);
    server.listen(0, '127.0.0.1', () => {
      const port = server.address().port;
      server.close(() => resolve(port));
    });
  });
}

async function ready(url, process) {
  for (let i = 0; i < 150; i++) {
    if (process.exitCode !== null) throw new Error('Editor server exited before it became ready');
    try { const response = await fetch(url); await response.arrayBuffer(); if (response.ok) return; } catch (_) {}
    await pause(100);
  }
  throw new Error('Editor server did not become ready');
}

test('rich editing, review, undo, save and graph preserve authored text', { timeout: 90000 }, async () => {
  const temporary = await fs.mkdtemp(path.join(os.tmpdir(), 'narrative-e2e-'));
  const project = path.join(temporary, 'project');
  let server, browser;
  try {
    await fs.cp(fixture, project, { recursive: true });
    const manifestPath = path.join(project, 'manifest.json');
    const initialManifest = JSON.parse(await fs.readFile(manifestPath, 'utf8'));
    initialManifest.beats = {};
    await fs.writeFile(manifestPath, JSON.stringify(initialManifest));
    const story = path.join(project, 'story.md');
    await fs.appendFile(story, '\nThe Kardashian poster hangs.\n');
    const original = await fs.readFile(story);
    const port = await freePort();
    const base = `http://127.0.0.1:${port}`;
    server = spawn(process.env.PYTHON || 'python', ['-m', 'narrative_composer.editor',
      '--file', story, '--manifest', path.join(project, 'manifest.json'),
      '--entity-dir', path.join(project, 'characters'), '--canon', 'recovery', '--port', String(port),
      '--provider', 'venice'],
      { cwd: root, stdio: 'ignore', windowsHide: true });
    await ready(base + '/', server);
    const executablePath = process.env.PLAYWRIGHT_CHROMIUM_EXECUTABLE_PATH ||
      (process.platform === 'win32' ? 'C:/Program Files/Google/Chrome/Application/chrome.exe' : undefined);
    browser = await chromium.launch({ headless: true, executablePath });
    const page = await browser.newPage({ viewport: { width: 1600, height: 1000 }, acceptDownloads: true });
    const pageErrors = [];
    page.on('pageerror', error => pageErrors.push(error.message));
    await page.goto(base + '/', { waitUntil: 'domcontentloaded' });
    await page.locator('#rich-editor .tiptap').waitFor();
    await page.waitForFunction(() => document.querySelector('#state').textContent === 'Saved draft');
    await page.evaluate(() => openNode('st:dana.state.alert'));
    await page.locator('#state-appearances').click();
    await page.getByText('Form appearances · dana.state.alert').waitFor();
    await page.getByRole('button', { name: 'Inspect source block' }).first().click();
    await page.waitForFunction(() => document.querySelector('#node-label').textContent.includes('block'));
    await page.locator('#node-cancel').click();
    await page.evaluate(() => openNode('port:dana.state.alert.port.data'));
    await page.locator('#node-text').fill('{invalid');
    await page.locator('#node-apply').click();
    await page.waitForFunction(() => /invalid JSON/i.test(document.querySelector('#node-error').textContent));
    assert.equal(await page.locator('#node-dialog').getAttribute('aria-labelledby'), 'node-label');
    await page.locator('#node-cancel').click();
    assert.equal(await page.locator('#provider').inputValue(), 'venice');
    await page.locator('#provider').selectOption('mock');

    async function save() {
      const response = page.waitForResponse(r => r.url().endsWith('/api/save') && r.request().method() === 'POST');
      await page.locator('#save').click();
      assert.equal((await response).status(), 200);
      await page.waitForFunction(() => document.querySelector('#state').textContent === 'Saved draft');
    }

    await save();
    assert.deepEqual(await fs.readFile(story), original);
    const target = page.locator('#rich-editor .tiptap p').filter({ hasText: 'The Kardashian poster hangs.' }).last();
    const targetId = await target.getAttribute('data-id');
    await target.evaluate(element => {
      const range = document.createRange();
      range.setStart(element.firstChild, 4); range.setEnd(element.firstChild, 14);
      const selection = getSelection(); selection.removeAllRanges(); selection.addRange(range);
      document.dispatchEvent(new Event('selectionchange'));
    });
    await page.locator('#bold').click();
    await save();
    assert.deepEqual(await fs.readFile(story), original);
    await page.reload({ waitUntil: 'domcontentloaded' });
    await page.locator('#rich-editor .tiptap').waitFor();
    await page.locator('#provider').selectOption('mock');
    const stable = page.locator(`#rich-editor .tiptap p[data-id="${targetId}"]`);
    assert.equal(await stable.locator('strong').innerText(), 'Kardashian');

    const plan = page.waitForResponse(r => r.url().endsWith('/api/recook'));
    await page.locator('#recook').click();
    assert.equal((await plan).status(), 200);
    await stable.locator('strong').evaluate(element => {
      const range = document.createRange(); range.selectNodeContents(element);
      const selection = getSelection(); selection.removeAllRanges(); selection.addRange(range);
      document.dispatchEvent(new Event('selectionchange'));
    });
    await page.locator('#italic').click();
    const before = await page.locator('#src').inputValue();
    await page.getByRole('button', { name: 'Apply reviewed proposal' }).click();
    assert.match(await page.locator('#status').innerText(), /changed after planning/i);
    assert.equal(await page.locator('#src').inputValue(), before);

    const secondPlan = page.waitForResponse(r => r.url().endsWith('/api/recook'));
    await page.locator('#recook').click();
    assert.equal((await secondPlan).status(), 200);
    await page.getByRole('button', { name: 'Apply reviewed proposal' }).click();
    await page.waitForFunction(() => document.querySelector('#side-title').textContent === 'Proposal applied');
    const after = await page.locator('#src').inputValue();
    assert.notEqual(after, before);
    assert.equal(await stable.locator('strong em, em strong').innerText(), 'Reality Queen');
    await page.locator('#undo').click();
    assert.equal(await page.locator('#src').inputValue(), before);
    await page.locator('#redo').click();
    assert.equal(await page.locator('#src').inputValue(), after);

    const graph = page.waitForResponse(r => r.url().endsWith('/api/graph'));
    await page.locator('#graph').click();
    const graphResponse = await graph;
    assert.equal(graphResponse.status(), 200);
    assert.match(JSON.parse(graphResponse.request().postData()).text, /Reality Queen/);
    assert.ok((await graphResponse.json()).html.includes('dana'), 'character graph did not render');
    await page.locator('#focus').click();
    await save();
    await page.reload({ waitUntil: 'domcontentloaded' });
    await page.locator('#rich-editor .tiptap').waitFor();
    await page.locator('#provider').selectOption('mock');
    assert.equal(await stable.locator('strong em, em strong').innerText(), 'Reality Queen');
    const beforeSplit = await page.locator('#src').inputValue();
    await stable.click();
    await page.keyboard.press('End');
    await page.keyboard.press('Enter');
    const splitIds = await page.locator('#rich-editor .tiptap p').evaluateAll(nodes => nodes.map(n => n.getAttribute('data-id')));
    assert.equal(new Set(splitIds).size, splitIds.length);
    await page.keyboard.press('Backspace');
    assert.equal(await page.locator('#src').inputValue(), beforeSplit);
    assert.equal(await stable.locator('strong em, em strong').innerText(), 'Reality Queen');
    await page.context().grantPermissions(['clipboard-read', 'clipboard-write'], { origin: base });
    await page.evaluate(() => navigator.clipboard.writeText('Alpha 😀\n第二行'));
    const beforePaste = await page.locator('#src').inputValue();
    await page.locator('#rich-editor .tiptap p').last().click();
    await page.keyboard.press('Control+V');
    assert.ok((await page.locator('#src').inputValue()).includes('Alpha 😀\n第二行'));
    await page.locator('#undo').click();
    assert.equal(await page.locator('#src').inputValue(), beforePaste);
    const download = page.waitForEvent('download');
    await page.locator('#export-format').selectOption('rich-html');
    await page.locator('#export').click();
    const html = await fs.readFile(await (await download).path(), 'utf8');
    assert.match(html, /Reality Queen/);
    assert.match(html, /<strong>/);

    const beforeCondition = await page.locator('#src').inputValue();
    const condition = page.waitForResponse(r => r.url().endsWith('/api/condition'));
    await page.locator('#condition').click();
    assert.equal((await condition).status(), 200);
    assert.equal(await page.locator('#src').inputValue(), beforeCondition);
    const beforePlanManifest = await fs.readFile(manifestPath);
    await page.locator('#new-beat').click();
    await page.locator('#beat-heading').fill('INT. HALL - DAY');
    await page.locator('#beat-goal').fill('Dana considers the next step.');
    await page.locator('#beat-actors').selectOption(['dana']);
    const createBeat = page.waitForResponse(r => r.url().endsWith('/api/beat/create'));
    await page.locator('#beat-create').click();
    assert.equal((await createBeat).status(), 200);
    await page.waitForFunction(() => !document.querySelector('#beat-dialog').open);
    await page.waitForFunction(() => document.querySelector('#beat-select').value !== '');
    assert.deepEqual(await fs.readFile(manifestPath), beforePlanManifest);
    assert.equal(await page.locator('#src').inputValue(), beforeCondition);
    await page.locator('#beat-forms').click();
    await page.locator('#forms-fields select[data-actor="dana"]').selectOption('dana.state.alert');
    await page.locator('#forms-apply').click();
    const compose = page.waitForResponse(r => r.url().endsWith('/api/compose'));
    await page.locator('#compose').click();
    const composeResponse = await compose;
    assert.equal(composeResponse.status(), 200);
    const composeData = await composeResponse.json();
    assert.ok(composeData.patches?.length, 'composer did not return a proposal');
    assert.deepEqual(composeData.patches[0].state_overrides, { dana: 'dana.state.alert' });
    await page.getByRole('button', { name: 'Apply reviewed proposal' }).click();
    await page.waitForFunction(() => document.querySelector('#side-title').textContent === 'Proposal applied');
    const withBeat = await page.locator('#src').inputValue();
    assert.ok(withBeat.startsWith(beforeCondition), 'composition altered existing text');
    assert.ok(withBeat.length > beforeCondition.length);
    assert.equal(await stable.locator('strong em, em strong').innerText(), 'Reality Queen');
    await page.locator('#undo').click();
    assert.match(await page.locator('#status').innerText(), /paused while unsaved graph or beat/i);
    assert.equal(await page.locator('#src').inputValue(), withBeat);
    await save();
    await page.reload({ waitUntil: 'domcontentloaded' });
    await page.locator('#rich-editor .tiptap').waitFor();
    await page.locator('#provider').selectOption('mock');
    assert.equal(await page.locator('#src').inputValue(), withBeat);

    await page.locator('#rich-editor .tiptap p').last().click();
    await page.keyboard.type('The Kardashian poster stands.');
    const mixed = page.locator('#rich-editor .tiptap p').filter({ hasText: 'The Kardashian poster stands.' }).last();
    await mixed.evaluate(element => {
      const range = document.createRange(); range.setStart(element.firstChild, 4); range.setEnd(element.firstChild, 8);
      const selection = getSelection(); selection.removeAllRanges(); selection.addRange(range);
      document.dispatchEvent(new Event('selectionchange'));
    });
    await page.locator('#bold').click();
    const mixedPlan = page.waitForResponse(r => r.url().endsWith('/api/recook'));
    await page.locator('#recook').click();
    assert.equal((await mixedPlan).status(), 200);
    const beforeMixedRepair = await page.locator('#src').inputValue();
    await page.locator('.row').filter({ hasText: 'The Kardashian poster stands.' })
      .getByRole('button', { name: 'Apply reviewed proposal' }).click();
    await page.waitForFunction(() => /mixed formatting/i.test(document.querySelector('#status').textContent));
    assert.equal(await page.locator('#src').inputValue(), beforeMixedRepair);
    assert.deepEqual(pageErrors, []);
  } finally {
    if (browser) await browser.close();
    if (server) server.kill();
    const resolved = path.resolve(temporary);
    const allowed = path.resolve(os.tmpdir()) + path.sep;
    if (!resolved.startsWith(allowed) || !path.basename(resolved).startsWith('narrative-e2e-')) {
      throw new Error('Refusing to remove an unexpected test directory');
    }
    await fs.rm(resolved, { recursive: true, force: true });
  }
});

test('character trace, author-added form and selected conditioning stay reviewable', { timeout: 90000 }, async () => {
  const temporary = await fs.mkdtemp(path.join(os.tmpdir(), 'narrative-form-e2e-'));
  const project = path.join(temporary, 'project');
  let server, browser;
  try {
    await fs.cp(fixture, project, { recursive: true });
    const story = path.join(project, 'story.md');
    await fs.appendFile(story, '\nThe lamp hummed in the dark room.\n');
    const original = await fs.readFile(story);
    const port = await freePort();
    const base = `http://127.0.0.1:${port}`;
    server = spawn(process.env.PYTHON || 'python', ['-m', 'narrative_composer.editor', '--file', story,
      '--manifest', path.join(project, 'manifest.json'), '--entity-dir', path.join(project, 'characters'),
      '--canon', 'recovery', '--port', String(port), '--provider', 'mock'],
      { cwd: root, stdio: 'ignore', windowsHide: true });
    await ready(base + '/', server);
    const executablePath = process.env.PLAYWRIGHT_CHROMIUM_EXECUTABLE_PATH ||
      (process.platform === 'win32' ? 'C:/Program Files/Google/Chrome/Application/chrome.exe' : undefined);
    browser = await chromium.launch({ headless: true, executablePath });
    const page = await browser.newPage({ viewport: { width: 1280, height: 800 } });
    await page.goto(base + '/', { waitUntil: 'domcontentloaded' });
    await page.locator('#rich-editor .tiptap').waitFor();
    await page.waitForFunction(() => document.querySelector('#state').textContent === 'Saved draft');
    const offscreen = await page.evaluate(() => [...document.querySelectorAll('nav button, nav select')]
      .filter(el => { const r = el.getBoundingClientRect(); return r.left < 0 || r.right > innerWidth || r.bottom > innerHeight; })
      .map(el => el.id));
    assert.deepEqual(offscreen, [], 'navigation controls must remain visible at 1280×800');
    await page.evaluate(() => openNode('ent:dana'));
    await page.getByRole('button', { name: 'Inspect character trace' }).click();
    await page.getByText('Character trace · Dana').waitFor();
    await page.getByText('cue_attributed_dialogue', { exact: false }).first().waitFor();
    await page.evaluate(() => openNode('ent:dana'));
    await page.getByRole('button', { name: 'Add form to character' }).click();
    await page.locator('#add-form-name').fill('Optional halfway form');
    await page.locator('#add-form-slug').fill('halfway');
    await page.getByRole('button', { name: 'Add unsaved form' }).click();
    await page.waitForFunction(() => document.querySelector('#state').textContent === 'Unsaved draft');
    await page.evaluate(() => openNode('ent:dana'));
    await page.getByRole('button', { name: 'Connect character forms' }).click();
    await page.locator('#add-link-from').selectOption('dana.state.base');
    await page.locator('#add-link-to').selectOption('dana.state.halfway');
    await page.getByRole('button', { name: 'Add provisional link' }).click();
    await page.waitForFunction(() => document.querySelector('#status').textContent.includes('dana.xform.base__halfway'));
    const save = page.waitForResponse(r => r.url().endsWith('/api/save'));
    await page.locator('#save').click();
    assert.equal((await save).status(), 200);
    await page.reload({ waitUntil: 'domcontentloaded' });
    await page.locator('#rich-editor .tiptap').waitFor();
    await page.evaluate(() => openNode('ent:dana'));
    await page.getByRole('button', { name: 'Inspect character trace' }).click();
    await page.getByText('dana.state.halfway', { exact: false }).waitFor();
    await page.getByRole('button', { name: 'Close workspace panel' }).click();
    await page.locator('#graph').click();
    const graph = page.frameLocator('iframe[title="Formatted story preview"]');
    await graph.getByText('Possible form links').waitFor();
    await graph.getByText('Optional halfway form · provisional / review', { exact: false }).waitFor();
    await page.locator('#reader').click();
    await page.locator('#rich-editor .tiptap p').filter({ hasText: 'The lamp hummed in the dark room.' }).click();
    const condition = page.waitForResponse(r => r.url().endsWith('/api/condition'));
    await page.getByRole('button', { name: 'Condition selected paragraph' }).click();
    const response = await condition;
    assert.equal(response.status(), 200);
    const body = await response.json();
    assert.equal(body.patches.length, 1);
    assert.equal(body.patches[0].original, 'The lamp hummed in the dark room.');
    assert.ok(body.patches[0].graph_context.source_sha256);
    assert.deepEqual(await fs.readFile(story), original);
  } finally {
    if (browser) await browser.close();
    if (server) server.kill();
    const resolved = path.resolve(temporary), allowed = path.resolve(os.tmpdir()) + path.sep;
    if (!resolved.startsWith(allowed) || !path.basename(resolved).startsWith('narrative-form-e2e-'))
      throw new Error('Refusing to remove an unexpected test directory');
    await fs.rm(resolved, { recursive: true, force: true });
  }
});

test('Codex session panel sends chosen context and inserts only a reviewed reply', { timeout: 60000 }, async () => {
  const temporary = await fs.mkdtemp(path.join(os.tmpdir(), 'narrative-chat-e2e-'));
  const project = path.join(temporary, 'project');
  let server, browser;
  try {
    await fs.cp(fixture, project, { recursive: true });
    const story = path.join(project, 'story.md');
    const original = await fs.readFile(story);
    const port = await freePort();
    const base = `http://127.0.0.1:${port}`;
    const bootstrap = `
import sys,json
from pathlib import Path
from http.server import ThreadingHTTPServer
from narrative_composer.editor import EditorHandler
class FakeSession:
 def __init__(self): self.messages=[]
 def start_connect(self): pass
 def start_chat(self,message,context):
  info=json.loads(context) if context else {}
  metadata={'context_section':info.get('section'),'context_revision':info.get('revision')}
  self.messages.extend([{'role':'user','text':message,**metadata},{'role':'assistant','text':'A reviewable reply.',**metadata}])
 def snapshot(self): return {'running':False,'connected':True,'messages':self.messages,'stream':'','error':''}
s=ThreadingHTTPServer(('127.0.0.1',int(sys.argv[1])),EditorHandler)
s.screenplay_path=Path(sys.argv[2]);s.manifest_path=Path(sys.argv[3]);s.entity_dir=Path(sys.argv[4]);s.canon='recovery';s.store=None;s.store_text=None;s.codex_session=FakeSession()
s.serve_forever()
`;
    server = spawn(process.env.PYTHON || 'python', ['-c', bootstrap, String(port), story,
      path.join(project, 'manifest.json'), path.join(project, 'characters')],
      { cwd: root, stdio: 'ignore', windowsHide: true });
    await ready(base + '/', server);
    const executablePath = process.env.PLAYWRIGHT_CHROMIUM_EXECUTABLE_PATH ||
      (process.platform === 'win32' ? 'C:/Program Files/Google/Chrome/Application/chrome.exe' : undefined);
    browser = await chromium.launch({ headless: true, executablePath });
    const page = await browser.newPage({ viewport: { width: 1600, height: 1000 } });
    await page.goto(base + '/', { waitUntil: 'domcontentloaded' });
    await page.locator('#rich-editor .tiptap').waitFor();
    await page.getByRole('button', { name: 'Codex session' }).click();
    await page.getByText('Session ready').waitFor();
    await page.setViewportSize({ width: 1280, height: 800 });
    await page.waitForFunction(() => document.querySelector('#side').getBoundingClientRect().top >= document.querySelector('nav').getBoundingClientRect().bottom);
    const layout = await page.evaluate(() => ({ navBottom: document.querySelector('nav').getBoundingClientRect().bottom,
      panelTop: document.querySelector('#side').getBoundingClientRect().top,
      searchHidden: document.querySelector('#node-search').hidden }));
    assert.ok(layout.panelTop >= layout.navBottom, 'session panel obscures the toolbar');
    assert.equal(layout.searchHidden, true);
    await page.getByLabel('Context to send').selectOption('document');
    await page.getByLabel('Message to Codex').fill('Discuss this scene.');
    const send = page.waitForResponse(r => r.url().endsWith('/api/codex/send'));
    await page.getByRole('button', { name: 'Send to Codex' }).click();
    const request = await send;
    assert.equal(request.status(), 200);
    assert.equal(JSON.parse(request.request().postData()).context, 'document');
    await page.getByText('A reviewable reply.').waitFor();
    assert.deepEqual(await fs.readFile(story), original);
    await page.getByRole('button', { name: 'Add reviewed reply to draft' }).click();
    assert.match(await page.locator('#src').inputValue(), /A reviewable reply\./);
    assert.deepEqual(await fs.readFile(story), original);
    await page.waitForFunction(() => /Reply added to the unsaved draft/.test(document.querySelector('#status').textContent));
    await page.getByRole('button', { name: 'Add reviewed reply to draft' }).click();
    await page.waitForFunction(() => /changed since this reply/i.test(document.querySelector('#status').textContent));
    assert.equal((await page.locator('#src').inputValue()).split('A reviewable reply.').length - 1, 1);
  } finally {
    if (browser) await browser.close();
    if (server) server.kill();
    const resolved = path.resolve(temporary), allowed = path.resolve(os.tmpdir()) + path.sep;
    if (!resolved.startsWith(allowed) || !path.basename(resolved).startsWith('narrative-chat-e2e-')) {
      throw new Error('Refusing to remove an unexpected test directory');
    }
    await fs.rm(resolved, { recursive: true, force: true });
  }
});
