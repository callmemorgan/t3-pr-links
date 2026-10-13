(function (root) {
  let signature = null;
  function set(kind, count = 0, problem = false) {
    const next = JSON.stringify([location.href, kind, count, problem]);
    if (next === signature) return;
    signature = next;
    void chrome.runtime.sendMessage({ type: "badge", url: location.href, kind, count, problem }).catch(() => {});
  }
  root.T3Badge = { set };
})(globalThis);
