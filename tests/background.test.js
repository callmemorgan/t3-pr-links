const { test } = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");
const T3Pr = require("../extension/common.js");
const tick = () => new Promise(resolve => setImmediate(resolve));
function background() {
  let handler;
  const calls = [];
  const badges = [];
  vm.runInNewContext(fs.readFileSync(path.join(__dirname, "../extension/background.js"), "utf8"), {
    URL, T3Pr, importScripts() {}, chrome: { action: {
      async setBadgeText(data) { badges.push(data); }, async setBadgeBackgroundColor() {}, async setTitle() {},
    }, runtime: {
      id: "test-id", getURL: p => `chrome-extension://test-id/${p}`,
      onMessage: { addListener(fn) { handler = fn; } },
      async sendNativeMessage(host, request) { calls.push(request); return { ok: true }; },
    } },
  });
  return { handler, calls, badges };
}

test("only the computer settings page can read or write helper configuration", async () => {
  const { handler, calls } = background();
  const options = { id: "test-id", url: "chrome-extension://test-id/options.html" };
  const config = { userdata: "/data", sshHosts: [] };
  for (const sender of [{ ...options, url: "chrome-extension://test-id/popup.html" },
    { ...options, tab: { url: "https://github.com/owner/repo/pull/42" } }, { ...options, id: "wrong-id" }]) {
    assert.equal(handler({ type: "saveConfig", config }, sender, () => {}), false);
  }
  assert.equal(handler({ type: "saveConfig", config }, options, () => {}), true);
  await tick();
  assert.equal(calls.length, 1);
  assert.equal(calls[0].type, "saveConfig");
});

test("branch lookup accepts only branches compatible with the sender's repository/file page", async () => {
  const { handler, calls } = background();
  const sender = { id: "test-id", tab: { url: "https://github.com/owner/repo/blob/Feature/foo/src/app.js" } };
  const request = { type: "branchLookup", repository: "owner/repo", branch: "Feature/foo" };
  assert.equal(handler({ ...request, repository: "other/repo" }, sender, () => {}), false);
  assert.equal(handler({ ...request, branch: "wrong" }, sender, () => {}), false);
  assert.equal(handler(request, sender, () => {}), true);
  await tick();
  assert.equal(calls.length, 1);
  assert.equal(calls[0].branch, "Feature/foo");
});

test("toolbar badges remain scoped to the sender's current GitHub page and never invoke native lookup", async () => {
  const { handler, calls, badges } = background();
  const sender = { id: "test-id", tab: { id: 9, url: "https://github.com/owner/repo/pull/42" } };
  const request = { type: "badge", url: sender.tab.url, kind: "pr", count: 2, problem: false };
  assert.equal(handler({ ...request, url: "https://github.com/owner/repo/pull/43" }, sender, () => {}), false);
  assert.equal(handler({ ...request, kind: "list" }, sender, () => {}), false);
  assert.equal(handler({ ...request, count: -1 }, sender, () => {}), false);
  assert.equal(handler(request, sender, () => {}), true);
  await tick();
  assert.equal(badges[0].tabId, 9);
  assert.equal(badges[0].text, "2");
  handler({ ...request, problem: true }, sender, () => {});
  await tick();
  assert.equal(badges[1].text, "!");
  assert.equal(calls.length, 0);
});

test("manual PR lookups are restricted to the thread browser and canonical GitHub PR URLs", async () => {
  const { handler, calls } = background();
  const sender = { id: "test-id", url: "chrome-extension://test-id/threads.html?repository=owner%2Frepo" };
  const message = { type: "directLookup", url: "https://github.com/Owner/Repo/pull/42/files" };
  assert.equal(handler(message, { ...sender, url: "chrome-extension://test-id/popup.html" }, () => {}), false);
  assert.equal(handler({ ...message, url: "https://evil.test/Owner/Repo/pull/42" }, sender, () => {}), false);
  assert.equal(handler(message, sender, () => {}), true);
  await tick();
  assert.equal(calls[0].repository, "owner/repo");
  assert.equal(calls[0].number, 42);
});

test("manual branch lookup permits query-bearing thread pages and rejects other senders or invalid input", async () => {
  const { handler, calls } = background();
  const sender = { id: "test-id", url: "chrome-extension://test-id/threads.html?repository=owner%2Frepo&branch=Feature%2Ffoo#results" };
  const message = { type: "directBranchLookup", repository: "Owner/Repo", branch: "Feature/foo", liveBranches: false };
  for (const url of ["chrome-extension://test-id/popup.html", "chrome-extension://test-id/threads.html/other", "https://github.com/owner/repo"]) {
    assert.equal(handler(message, { ...sender, url }, () => {}), false);
  }
  assert.equal(handler(message, { ...sender, tab: { url: "https://github.com/owner/repo" } }, () => {}), false);
  for (const invalid of [{ branch: "" }, { branch: "feature\nfoo" }, { branch: "x".repeat(1025) }, { repository: "owner/repo/extra" }]) {
    assert.equal(handler({ ...message, ...invalid }, sender, () => {}), false);
  }
  assert.equal(handler(message, sender, () => {}), true);
  await tick();
  assert.equal(calls.length, 1);
  assert.equal(calls[0].type, "branchLookup");
  assert.equal(calls[0].repository, "owner/repo");
  assert.equal(calls[0].branch, "Feature/foo");
  assert.equal(calls[0].liveBranches, false);
});
