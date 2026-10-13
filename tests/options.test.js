const { test } = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const { JSDOM } = require("jsdom");
const extension = path.join(__dirname, "../extension");
const tick = () => new Promise(resolve => setImmediate(resolve));
const connection = { id: "local", name: "My T3", endpoint: "http://localhost:3773", environmentId: "env", expiresAt: "2026-11-01T00:00:00Z" };
function options(t, sendMessage, permissionsRequest = async () => true) {
  const dom = new JSDOM(fs.readFileSync(path.join(extension, "options.html"), "utf8"), { url: "chrome-extension://test-id/options.html", runScripts: "outside-only" });
  t.after(() => dom.window.close());
  dom.window.chrome = { runtime: { sendMessage }, permissions: { request: permissionsRequest } };
  for (const file of ["common.js", "ui.js", "api.js", "options.js"]) dom.window.eval(fs.readFileSync(path.join(extension, file), "utf8"));
  return dom;
}
function submit(dom) { dom.window.document.getElementById("settings-form").dispatchEvent(new dom.window.Event("submit", { cancelable: true })); }

test("first setup requests only the selected endpoint and clears the pairing code on success", async t => {
  const messages = [], grants = [];
  let saved = [];
  const dom = options(t, async message => {
    messages.push(message);
    if (message.type === "getConfig") return { ok: true, config: { connections: saved } };
    saved = [connection];
    return { ok: true, connection };
  }, async grant => { grants.push(grant); return true; });
  await tick();
  const document = dom.window.document;
  assert.equal(document.getElementById("endpoint").value, "http://127.0.0.1:3773");
  assert.equal(document.getElementById("test").disabled, true);
  document.getElementById("endpoint").value = "https://t3.example.test/backend/";
  document.getElementById("pairing-code").value = "one-time-code";
  submit(dom);
  await tick();
  assert.deepEqual(Array.from(grants[0].origins), ["https://t3.example.test/*"]);
  assert.equal(messages[1].config.endpoint, "https://t3.example.test/backend");
  assert.equal(messages[1].config.pairingCode, "one-time-code");
  assert.equal(document.getElementById("pairing-code").value, "");
  assert.match(document.getElementById("status").textContent, /Connected/);
  assert.match(document.getElementById("computers").textContent, /My T3/);
});

test("permission denial and pairing failure preserve the unsaved endpoint", async t => {
  const requests = [];
  let granted = false;
  const dom = options(t, async message => {
    requests.push(message);
    return message.type === "getConfig" ? { ok: true, config: { connections: [] } } : { ok: false, error: "Pairing code expired" };
  }, async () => granted);
  await tick();
  const document = dom.window.document;
  document.getElementById("endpoint").value = "http://localhost:7940";
  document.getElementById("pairing-code").value = "code";
  submit(dom);
  await tick();
  assert.equal(requests.length, 1);
  assert.match(document.getElementById("status").textContent, /not granted/);
  granted = true;
  submit(dom);
  await tick();
  assert.equal(document.getElementById("endpoint").value, "http://localhost:7940");
  assert.equal(document.getElementById("status").textContent, "Pairing code expired");
  assert.equal(document.getElementById("save").disabled, false);
});

test("editing can keep an existing pairing, connection checks use saved endpoints, and removal forgets it", async t => {
  const requests = [];
  let saved = [connection];
  const dom = options(t, async message => {
    requests.push(message);
    if (message.type === "getConfig") return { ok: true, config: { connections: saved } };
    if (message.type === "removeConnection") { saved = []; return { ok: true }; }
    if (message.type === "saveConfig") return { ok: true, connection };
    return { ok: false, environments: [{ name: "My T3", ok: false, error: "Offline" }] };
  });
  await tick();
  const document = dom.window.document;
  document.querySelector(".computer button").click();
  document.getElementById("name").value = "Renamed";
  document.getElementById("test").click();
  await tick();
  assert.equal(requests.at(-1).type, "status");
  assert.match(document.getElementById("connections").textContent, /My T3: Offline/);
  assert.equal(document.getElementById("name").value, "Renamed");
  submit(dom);
  await tick();
  const save = requests.find(message => message.type === "saveConfig");
  assert.equal(save.config.id, "local");
  assert.equal(save.config.pairingCode, "");
  document.querySelectorAll(".computer button")[1].click();
  await tick();
  assert.equal(requests.at(-2).type, "removeConnection");
  assert.equal(document.querySelectorAll(".computer").length, 0);
});

test("new endpoints require a code and invalid URIs never request site access", async t => {
  let permissionCalls = 0;
  const dom = options(t, async () => ({ ok: true, config: { connections: [] } }), async () => { permissionCalls++; return true; });
  await tick();
  submit(dom);
  assert.equal(permissionCalls, 0);
  assert.match(dom.window.document.getElementById("status").textContent, /pairing code/);
  dom.window.document.getElementById("endpoint").value = "http://user:secret@localhost:3773";
  submit(dom);
  assert.equal(permissionCalls, 0);
  assert.match(dom.window.document.getElementById("status").textContent, /without credentials/);
});

test("stored token remains usable when API verification fails after pairing", async t => {
  let saved = [];
  const dom = options(t, async message => {
    if (message.type === "getConfig") return { ok: true, config: { connections: saved } };
    saved = [connection];
    return { ok: true, warning: "T3 closed the connection." };
  });
  await tick();
  dom.window.document.getElementById("pairing-code").value = "code";
  submit(dom);
  await tick();
  assert.match(dom.window.document.getElementById("status").textContent, /Pairing saved.*T3 closed/);
  assert.equal(dom.window.document.getElementById("pairing-code").value, "");
});
