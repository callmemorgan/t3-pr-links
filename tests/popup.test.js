const { test } = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const { JSDOM } = require("jsdom");
const extension = path.join(__dirname, "../extension");
const tick = () => new Promise(resolve => setImmediate(resolve));

function popup(t, context, status = { ok: true, threadCount: 2 }) {
  const dom = new JSDOM(fs.readFileSync(path.join(extension, "popup.html"), "utf8"), {
    url: "chrome-extension://test-id/popup.html", runScripts: "outside-only",
  });
  t.after(() => dom.window.close());
  const requests = [];
  dom.window.chrome = {
    tabs: {
      async query() { return [{ id: 42 }]; },
      async sendMessage(id, message) { requests.push({ id, message }); if (!context) throw new Error("No content script"); return context; },
    },
    runtime: { getURL: p => `chrome-extension://test-id/${p}`, async sendMessage(message) { requests.push(message); return status; } },
  };
  for (const file of ["common.js", "ui.js", "settings.js", "popup.js"]) dom.window.eval(fs.readFileSync(path.join(extension, file), "utf8"));
  return { dom, requests };
}

test("popup displays current PR matches and refreshes that page without a second database scan", async t => {
  const { dom, requests } = popup(t, {
    pr: { repository: "owner/repo", number: 42 }, head: { repository: "fork/repo", branch: "Feature/foo" },
    result: { ok: true, threads: [{ id: "t1", environmentId: "mini", title: "Work", computer: "Mac Mini", matchType: "branch" }],
      environments: [{ name: "Mac Mini", ok: true }] },
  });
  await tick();
  const document = dom.window.document;
  assert.equal(document.getElementById("status").textContent, "1 matching thread");
  assert.equal(document.querySelector("#threads a").href, "t3code://threads/mini/t1");
  assert.ok(document.getElementById("context-branch").textContent.includes("fork/repo"));
  assert.equal(requests.length, 1);
  document.getElementById("retry").click();
  await tick();
  assert.equal(requests.at(-1).message.force, true);
});

test("popup explains partial coverage and does not claim no matches when all computers fail", async t => {
  const context = { pr: { repository: "owner/repo", number: 42 }, result: { ok: false, error: "No computers could be read", threads: [],
    environments: [{ name: "Mac Mini", ok: false, error: "Offline" }] } };
  const { dom } = popup(t, context);
  await tick();
  assert.equal(dom.window.document.getElementById("empty").hidden, true);
  assert.ok(dom.window.document.getElementById("details").textContent.includes("Mac Mini: Offline"));
});

test("on other sites popup shows connection diagnostics without requesting page permissions", async t => {
  const { dom, requests } = popup(t, null, { ok: true, threadCount: 7, environments: [{ name: "This computer", ok: true }, { name: "Mac Mini", ok: true }] });
  await tick();
  assert.equal(dom.window.document.getElementById("context").hidden, true);
  assert.equal(dom.window.document.getElementById("status").textContent, "Connected to T3 Code");
  assert.equal(requests.at(-1).type, "status");
});

test("popup groups current-list threads by PR using the shared batch context", async t => {
  const { dom, requests } = popup(t, {
    list: { url: "https://github.com/owner/repo/pulls" }, repository: "owner/repo",
    result: { ok: true, environments: [{ name: "Mac Mini", ok: true }] },
    pullRequests: [{ repository: "owner/repo", number: 42, title: "PR title", url: "https://github.com/owner/repo/pull/42",
      threads: [{ id: "t1", environmentId: "mini", title: "Work", computer: "Mac Mini", matchType: "linked" }] }],
  });
  await tick();
  assert.equal(dom.window.document.getElementById("status").textContent, "1 linked PR");
  assert.equal(dom.window.document.querySelector(".t3-pr-popup-title").href, "https://github.com/owner/repo/pull/42");
  assert.equal(dom.window.document.querySelector("#threads .t3-pr-thread-link").href, "t3code://threads/mini/t1");
  assert.equal(requests.length, 2);
});
