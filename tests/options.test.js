const { test } = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const { JSDOM } = require("jsdom");
const extension = path.join(__dirname, "../extension");
const tick = () => new Promise(resolve => setImmediate(resolve));
function options(t, sendMessage) {
  const dom = new JSDOM(fs.readFileSync(path.join(extension, "options.html"), "utf8"), { url: "chrome-extension://test-id/options.html", runScripts: "outside-only" });
  t.after(() => dom.window.close());
  dom.window.chrome = { runtime: { sendMessage } };
  for (const file of ["common.js", "ui.js", "options.js"]) dom.window.eval(fs.readFileSync(path.join(extension, file), "utf8"));
  return dom;
}

test("computer settings preserve unsaved fields on errors and connection checks use saved configuration", async t => {
  const requests = [];
  const dom = options(t, async message => {
    requests.push(message);
    if (message.type === "getConfig") return { ok: true, config: { userdata: "/local-data", sshHosts: [{ host: "mini", name: "Mini", userdata: "~/.t3/userdata" }] } };
    if (message.type === "saveConfig") return { ok: false, error: "Invalid hostname" };
    return { ok: true, environments: [{ name: "Mini", ok: false, error: "Offline" }] };
  });
  await tick();
  const document = dom.window.document;
  document.getElementById("add").click();
  document.querySelectorAll('[data-field="host"]')[1].value = "new-host";
  document.getElementById("settings-form").dispatchEvent(new dom.window.Event("submit", { cancelable: true }));
  await tick();
  assert.equal(requests[1].config.sshHosts.length, 2);
  assert.equal(document.querySelectorAll('[data-field="host"]')[1].value, "new-host");
  assert.equal(document.getElementById("status").textContent, "Invalid hostname");
  document.getElementById("test").click();
  await tick();
  assert.equal(requests.at(-1).type, "status");
  assert.ok(document.getElementById("connections").textContent.includes("Mini: Offline"));
  assert.equal(document.querySelectorAll('[data-field="host"]')[1].value, "new-host");
  document.querySelectorAll(".computer button")[1].click();
  assert.equal(document.querySelectorAll(".computer").length, 1);
});

test("unavailable helper leaves settings disabled and can be retried", async t => {
  let available = false;
  const dom = options(t, async () => available ? { ok: true, config: { userdata: "/data", sshHosts: [] } } : { ok: false, error: "Missing helper" });
  await tick();
  assert.equal(dom.window.document.getElementById("save").disabled, true);
  assert.equal(dom.window.document.getElementById("reload-config").hidden, false);
  available = true;
  dom.window.document.getElementById("reload-config").click();
  await tick();
  assert.equal(dom.window.document.getElementById("save").disabled, false);
});

test("saving a directory without T3 data keeps the settings and shows the warning", async t => {
  const dom = options(t, async message => message.type === "getConfig"
    ? { ok: true, config: { userdata: "/data", sshHosts: [] } }
    : { ok: true, config: message.config, warning: "T3 Code data was not found in /typo." });
  await tick();
  const document = dom.window.document;
  document.getElementById("userdata").value = "/typo";
  document.getElementById("settings-form").dispatchEvent(new dom.window.Event("submit", { cancelable: true }));
  await tick();
  assert.equal(document.getElementById("userdata").value, "/typo");
  assert.equal(document.getElementById("status").textContent, "Saved, but T3 Code data was not found in /typo.");
});
