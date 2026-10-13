const { test } = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const { JSDOM } = require("jsdom");
const extension = path.join(__dirname, "../extension");
const tick = () => new Promise(resolve => setImmediate(resolve));
function browser(t, sendMessage, query = "?repository=owner%2Frepo") {
  const dom = new JSDOM(fs.readFileSync(path.join(extension, "threads.html"), "utf8"), {
    url: `chrome-extension://test-id/threads.html${query}`, runScripts: "outside-only",
  });
  t.after(() => dom.window.close());
  dom.window.chrome = { runtime: { sendMessage } };
  for (const file of ["common.js", "ui.js", "settings.js", "threads.js"]) dom.window.eval(fs.readFileSync(path.join(extension, file), "utf8"));
  return dom;
}

test("repository browser searches title/branch locally and exposes incomplete coverage", async t => {
  let calls = 0;
  const dom = browser(t, async request => {
    calls++; assert.equal(request.repository, "owner/repo");
    return { ok: true, truncated: true, environments: [{ name: "Mac Mini", ok: false, error: "Offline" }], threads: [
      { id: "a", environmentId: "env", title: "<script>Work</script>", branch: "Feature/foo", matchType: "repository" },
      { id: "b", environmentId: "env", title: "Other work", branch: "main", archived: true, matchType: "repository" },
    ] };
  });
  await tick();
  const document = dom.window.document;
  assert.equal(document.querySelectorAll(".thread").length, 2);
  assert.ok(document.getElementById("coverage").textContent.includes("Mac Mini: Offline"));
  assert.ok(document.getElementById("count").textContent.includes("results were limited"));
  const search = document.getElementById("search");
  search.value = "feature/FOO"; search.dispatchEvent(new dom.window.Event("input"));
  assert.equal(document.querySelectorAll(".thread").length, 1);
  assert.equal(document.querySelector(".thread a").textContent, "<script>Work</script> ↗");
  assert.equal(document.querySelector(".thread script"), null);
  search.value = ""; search.dispatchEvent(new dom.window.Event("input"));
  await dom.window.T3Settings.update({ includeArchived: false });
  assert.equal(document.querySelectorAll(".thread").length, 1);
  assert.equal(calls, 1);
});

test("repository browser rejects invalid repository input without contacting the helper", async t => {
  let calls = 0;
  const dom = browser(t, async () => { calls++; return { ok: true, threads: [] }; });
  await tick();
  dom.window.document.getElementById("repository").value = "owner/repo/extra";
  dom.window.document.getElementById("lookup").dispatchEvent(new dom.window.Event("submit", { cancelable: true }));
  await tick();
  assert.equal(calls, 1);
  assert.ok(dom.window.document.getElementById("status").textContent.includes("Enter owner/repository"));
});

test("export contains only displayed threads and preserves incomplete-lookup context", async t => {
  const dom = browser(t, async () => ({ ok: true, truncated: true, environments: [{ name: "Mini", ok: true }], threads: [
    { id: "a", environmentId: "env", title: "Shown", branch: "feature", pullRequests: [{ repository: "owner/repo", number: 42 }] },
    { id: "b", environmentId: "env", title: "Hidden", archived: true },
  ] }));
  await tick();
  await dom.window.T3Settings.update({ includeArchived: false });
  let download;
  let blob;
  dom.window.URL.createObjectURL = value => { blob = value; return "blob:export"; };
  dom.window.URL.revokeObjectURL = () => {};
  dom.window.HTMLAnchorElement.prototype.click = function () { download = this.download; };
  dom.window.document.getElementById("export").click();
  const text = await new Promise(resolve => {
    const reader = new dom.window.FileReader(); reader.onload = () => resolve(reader.result); reader.readAsText(blob);
  });
  const data = JSON.parse(text);
  assert.equal(download, "owner-repo-t3-links.json");
  assert.equal(data.threads.length, 1);
  assert.equal(data.threads[0].title, "Shown");
  assert.equal(data.threads[0].t3Link, "t3code://threads/env/a");
  assert.deepEqual(data.threads[0].pullRequests, ["https://github.com/owner/repo/pull/42"]);
  assert.equal(data.truncated, true);
});

test("invalid navigation cancels an in-flight repository query and leaves export unavailable", async t => {
  let resolve;
  const dom = browser(t, () => new Promise(done => { resolve = done; }));
  await tick();
  dom.window.document.getElementById("repository").value = "invalid";
  dom.window.document.getElementById("lookup").dispatchEvent(new dom.window.Event("submit", { cancelable: true }));
  resolve({ ok: true, threads: [{ id: "a", environmentId: "env", title: "Stale" }] });
  await tick();
  assert.equal(dom.window.document.querySelectorAll(".thread").length, 0);
  assert.equal(dom.window.document.getElementById("export").disabled, true);
});

test("pasted PR URLs perform an exact lookup and label the loaded PR", async t => {
  const requests = [];
  const dom = browser(t, async request => { requests.push(request); return { ok: true, threads: [] }; });
  await tick();
  const document = dom.window.document;
  document.getElementById("repository").value = "https://github.com/Owner/Repo/pull/57/files?diff=split";
  document.getElementById("lookup").dispatchEvent(new dom.window.Event("submit", { cancelable: true }));
  await tick();
  assert.equal(requests[1].type, "directLookup");
  assert.equal(requests[1].url, "https://github.com/owner/repo/pull/57");
  assert.equal(document.getElementById("page-title").textContent, "PR threads");
  assert.equal(document.getElementById("status").textContent, "Threads for owner/repo #57");
});

test("manual branch lookup preserves branch case/slashes, workspace context, and live-workspace preferences", async t => {
  const requests = [];
  const dom = browser(t, async request => {
    requests.push(request);
    return { ok: true, threads: [{ id: "a", environmentId: "env", title: "Branch work", branch: "old", matchedBranch: "Feature/foo", matchType: "checkout" }] };
  }, "?repository=Owner%2FRepo&branch=Feature%2Ffoo");
  await tick();
  const document = dom.window.document;
  assert.equal(document.getElementById("branch-lookup").open, true);
  assert.equal(requests[0].type, "directBranchLookup");
  assert.equal(requests[0].repository, "owner/repo");
  assert.equal(requests[0].branch, "Feature/foo");
  assert.equal(document.getElementById("page-title").textContent, "Branch threads");
  assert.ok(document.querySelector(".thread").textContent.includes("Matching workspace branch: Feature/foo"));
  await dom.window.T3Settings.update({ liveBranches: false });
  await tick();
  assert.equal(requests.length, 2);
  assert.equal(requests[1].liveBranches, false);
  assert.equal(requests[1].branch, "Feature/foo");
  document.getElementById("branch").value = "";
  document.getElementById("lookup").dispatchEvent(new dom.window.Event("submit", { cancelable: true }));
  await tick();
  assert.equal(requests[2].type, "repositoryLookup");
});

test("manual branch lookups discard stale results and reject a branch paired with a PR URL", async t => {
  const pending = [];
  const dom = browser(t, request => new Promise(resolve => pending.push({ request, resolve })), "?repository=owner%2Frepo&branch=old");
  await tick();
  const document = dom.window.document;
  document.getElementById("branch").value = "new";
  document.getElementById("lookup").dispatchEvent(new dom.window.Event("submit", { cancelable: true }));
  await tick();
  pending[0].resolve({ ok: true, threads: [{ id: "old", environmentId: "env", title: "Old" }] });
  await tick();
  assert.equal(document.querySelectorAll(".thread").length, 0);
  pending[1].resolve({ ok: true, threads: [{ id: "new", environmentId: "env", title: "New" }] });
  await tick();
  assert.equal(document.querySelector(".thread a").textContent, "New ↗");
  document.getElementById("repository").value = "https://github.com/owner/repo/pull/42";
  document.getElementById("lookup").dispatchEvent(new dom.window.Event("submit", { cancelable: true }));
  await tick();
  assert.equal(pending.length, 2);
  assert.ok(document.getElementById("status").textContent.includes("Leave Branch blank"));
  assert.equal(document.getElementById("export").disabled, true);
});

test("branch export identifies the query and the workspace branch separately from the recorded branch", async t => {
  const dom = browser(t, async () => ({ ok: true, threads: [{ id: "a", environmentId: "env", title: "Work", branch: "old", matchedBranch: "Feature/foo", matchType: "checkout" }] }), "?repository=owner%2Frepo&branch=Feature%2Ffoo");
  await tick();
  let blob, download;
  dom.window.URL.createObjectURL = value => { blob = value; return "blob:export"; };
  dom.window.URL.revokeObjectURL = () => {};
  dom.window.HTMLAnchorElement.prototype.click = function () { download = this.download; };
  dom.window.document.getElementById("export").click();
  const text = await new Promise(resolve => {
    const reader = new dom.window.FileReader(); reader.onload = () => resolve(reader.result); reader.readAsText(blob);
  });
  const data = JSON.parse(text);
  assert.equal(download, "owner-repo-branch-t3-links.json");
  assert.equal(data.branch, "Feature/foo");
  assert.equal(data.threads[0].branch, "old");
  assert.equal(data.threads[0].matchedBranch, "Feature/foo");
});
