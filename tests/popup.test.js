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

// The shortcut's whole contract: visible, all text inside one link, an exact lookup URL that
// decodes back to the source branch, a new tab, and a tooltip naming the repository.
function branchShortcut(document, { text, repository, branch, href }) {
  const hint = document.getElementById("context-branch");
  const link = hint.querySelector("a");
  assert.equal(hint.hidden, false);
  assert.equal(hint.textContent, text);
  assert.equal(link.textContent, text);
  assert.equal(link.getAttribute("href"), href);
  assert.equal(new URL(link.href).searchParams.get("repository"), repository);
  assert.equal(new URL(link.href).searchParams.get("branch"), branch);
  assert.equal(link.target, "_blank");
  assert.equal(link.rel, "noopener");
  assert.equal(link.title, `Find T3 threads for branch ${branch} in ${repository}`);
  assert.equal(link.hasAttribute("aria-label"), false);
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
  branchShortcut(document, { text: "fork/repo · Feature/foo", repository: "fork/repo", branch: "Feature/foo",
    href: "chrome-extension://test-id/threads.html?repository=fork%2Frepo&branch=Feature%2Ffoo" });
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
      threads: [{ id: "t1", environmentId: "mini", title: "Work", computer: "Mac Mini", matchType: "linked" },
        { id: "t2", environmentId: "mini", title: "Wrap-up", computer: "Mac Mini", matchType: "linked" }] }],
  });
  await tick();
  assert.equal(dom.window.document.getElementById("status").textContent, "1 linked PR");
  assert.equal(dom.window.document.querySelectorAll("#threads .t3code-pr-thread-link").length, 2);
  assert.equal(dom.window.document.querySelector(".t3code-pr-popup-title").href, "https://github.com/owner/repo/pull/42");
  assert.equal(dom.window.document.querySelector("#threads .t3code-pr-thread-link").href, "t3code://threads/mini/t1");
  assert.equal(requests.length, 2);
});

test("compact popup keeps an explicitly linked thread prominent without a match badge and keeps its branch shortcut", async t => {
  const { dom } = popup(t, {
    pr: { repository: "owner/repo", number: 42 }, head: { repository: "owner/repo", branch: "feature/work" },
    result: { ok: true, threads: [{ id: "t1", environmentId: "mini", title: "Work", computer: "Mini", matchType: "linked" }],
      environments: [{ name: "This computer", ok: true }, { name: "Mini", ok: true }] },
  });
  await tick();
  const document = dom.window.document;
  assert.equal(document.getElementById("connection").dataset.state, "connected");
  assert.equal(document.getElementById("details").textContent, "2 computers connected");
  assert.equal(document.getElementById("details").title, "This computer, Mini");
  branchShortcut(document, { text: "feature/work", repository: "owner/repo", branch: "feature/work",
    href: "chrome-extension://test-id/threads.html?repository=owner%2Frepo&branch=feature%2Fwork" });
  assert.equal(document.querySelector(".t3code-pr-match-kind"), null);
  assert.equal(document.querySelector("#threads a").href, "t3code://threads/mini/t1");
  assert.ok(document.querySelector(".t3code-pr-copy button"));
});

test("compact popup still identifies an unavailable computer while retaining available matches", async t => {
  const { dom } = popup(t, {
    pr: { repository: "owner/repo", number: 42 }, result: { ok: true,
      threads: [{ id: "t1", environmentId: "local", title: "Local work", matchType: "linked" }],
      environments: [{ name: "This computer", ok: true }, { name: "Mini", ok: false, error: "Offline" }] },
  });
  await tick();
  const document = dom.window.document;
  assert.equal(document.getElementById("connection").dataset.state, "attention");
  assert.equal(document.getElementById("details").textContent, "Mini: Offline");
  assert.equal(document.getElementById("details").title, "Available: This computer");
  assert.equal(document.getElementById("context-branch").hidden, true);
  assert.ok(document.querySelector("#threads a"));
});

test("popup branch shortcut opens an exact branch lookup for the current branch page", async t => {
  const { dom } = popup(t, {
    branch: { repository: "owner/repo", branch: "Feature/one&two#100%" },
    result: { ok: true, threads: [{ id: "a", environmentId: "env", title: "Work", matchType: "branch" }] },
  });
  await tick();
  branchShortcut(dom.window.document, { text: "Feature/one&two#100%", repository: "owner/repo", branch: "Feature/one&two#100%",
    href: "chrome-extension://test-id/threads.html?repository=owner%2Frepo&branch=Feature%2Fone%26two%23100%25" });
});

test("popup keeps a fork PR's branch shortcut when the lookup has only linked, no, or failed matches", async t => {
  for (const result of [{ ok: true, threads: [{ id: "t1", environmentId: "mini", title: "Work", matchType: "linked" }] },
    { ok: true, threads: [] }, { ok: false, error: "No configured computers could be read.", threads: [] }]) {
    const { dom } = popup(t, { pr: { repository: "owner/repo", number: 42 }, head: { repository: "fork/repo", branch: "Fork/work" }, result });
    await tick();
    branchShortcut(dom.window.document, { text: "fork/repo · Fork/work", repository: "fork/repo", branch: "Fork/work",
      href: "chrome-extension://test-id/threads.html?repository=fork%2Frepo&branch=Fork%2Fwork" });
  }
});
