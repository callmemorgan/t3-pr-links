const { test } = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");
const source = fs.readFileSync(path.join(__dirname, "../extension/settings.js"), "utf8");

test("saved preferences filter by archive, match kind, and computer and follow local changes", async () => {
  let onChanged;
  const writes = [];
  const context = { chrome: { storage: {
    local: { async get() { return { preferences: { includeArchived: false, includeBranch: false, computer: "Mac Mini" } }; },
      async set(value) { writes.push(value); } },
    onChanged: { addListener(fn) { onChanged = fn; } },
  } } };
  vm.runInNewContext(source, context);
  const settings = context.T3Settings;
  await settings.ready;
  const records = [{ id: "right", computer: "Mac Mini", matchType: "linked" },
    { id: "archived", computer: "Mac Mini", archived: true },
    { id: "branch", computer: "Mac Mini", matchType: "branch" }, { id: "local" }];
  assert.deepEqual(Array.from(settings.filter(records), thread => thread.id), ["right"]);
  assert.equal(settings.filter([{ computer: "Mac Mini", matchType: "checkout" }]).length, 0);
  await settings.update({ computer: "all", includeBranch: true });
  assert.equal(writes[0].preferences.includeArchived, false);
  assert.equal(settings.filter(records).length, 3);
  onChanged({ preferences: { newValue: {} } }, "sync");
  assert.equal(settings.filter(records).length, 3);
  onChanged({ preferences: { newValue: {} } }, "local");
  assert.equal(settings.filter(records).length, 4);
});

test("failed preference writes do not silently change the current filters", async () => {
  const context = { chrome: { storage: { local: { async get() { return {}; }, async set() { throw Error("Storage unavailable"); } } } } };
  vm.runInNewContext(source, context);
  await assert.rejects(context.T3Settings.update({ includeArchived: false }));
  assert.equal(context.T3Settings.get().includeArchived, true);
});

test("thread sorting is stable, preserves explicit PR priority, and does not mutate responses", async () => {
  const context = {};
  vm.runInNewContext(source, context);
  const settings = context.T3Settings;
  const records = [
    { id: "workspace", title: "A workspace", matchType: "checkout", updatedAt: "2026-10-13" },
    { id: "linked", title: "Z linked", matchType: "linked", updatedAt: "2026-10-11" },
    { id: "archived", title: "B archived", matchType: "linked", archived: true, updatedAt: "2026-10-12" },
  ];
  assert.deepEqual(Array.from(settings.sort(records), t => t.id), ["linked", "archived", "workspace"]);
  await settings.update({ sort: "recent" });
  assert.deepEqual(Array.from(settings.sort(records, { repository: true }), t => t.id), ["workspace", "archived", "linked"]);
  await settings.update({ sort: "title" });
  assert.deepEqual(Array.from(settings.sort(records, { repository: true }), t => t.id), ["workspace", "archived", "linked"]);
  assert.equal(records[0].id, "workspace");
});
