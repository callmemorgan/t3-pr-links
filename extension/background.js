importScripts("common.js");

const HOST = "com.callmemorgan.t3code_pr_links";

// Settings (open_in_tab) and the thread browser run in tabs, so Chrome sets
// sender.tab for them as well as for content scripts; it cannot tell them apart.
// sender.url can: a content script reports its github.com page, never this origin.
function isExtensionPage(sender, page) {
  return sender.url?.startsWith(chrome.runtime.getURL(""))
    && (!page || sender.url.split(/[?#]/, 1)[0] === chrome.runtime.getURL(page));
}

chrome.runtime.onMessage.addListener((message, sender, sendResponse) => {
  if (sender.id !== chrome.runtime.id) return false;
  if (message?.type === "badge") {
    let actual, requested;
    try { actual = new URL(sender.tab?.url); requested = new URL(message.url); } catch { return false; }
    if (actual.protocol !== "https:" || actual.hostname !== "github.com" || actual.port || actual.username || actual.password
        || actual.href !== requested.href || !Number.isInteger(message.count) || message.count < 0 || message.count > 200
        || typeof message.problem !== "boolean") return false;
    const supported = message.kind === "none" && message.count === 0 && !message.problem
      || message.kind === "pr" && T3Pr.parsePullRequest(actual.href)
      || message.kind === "branch" && T3Pr.repositoryPage(actual.href)
      || message.kind === "list" && T3Pr.isPullRequestList(actual.href);
    if (!supported) return false;
    const noun = message.kind === "list" ? "linked PRs" : "matching threads";
    const text = message.problem ? "!" : message.count ? String(message.count) : "";
    const title = message.kind === "none" ? "T3Code PR Links" : `T3Code PR Links: ${message.count} ${noun}${message.problem ? " · Lookup incomplete" : ""}`;
    Promise.all([
      chrome.action.setBadgeText({ tabId: sender.tab.id, text }),
      chrome.action.setBadgeBackgroundColor({ tabId: sender.tab.id, color: message.problem ? "#9a6700" : "#6838d9" }),
      chrome.action.setTitle({ tabId: sender.tab.id, title }),
    ]).then(() => sendResponse({ ok: true }), () => sendResponse({ ok: false }));
    return true;
  }
  let request;
  if (message?.type === "status" && isExtensionPage(sender)) {
    request = { type: "status" };
  } else if (["getConfig", "saveConfig"].includes(message?.type) && isExtensionPage(sender, "options.html")) {
    request = message.type === "getConfig" ? { type: "getConfig" } : { type: "saveConfig", config: message.config };
  } else if (message?.type === "repositoryLookup" && isExtensionPage(sender)) {
    if (typeof message.repository !== "string" || !/^[a-z0-9_.-]+\/[a-z0-9_.-]+$/i.test(message.repository)) return false;
    request = { type: "repositoryLookup", host: "github.com", repository: message.repository.toLowerCase() };
  } else if (message?.type === "directBranchLookup" && isExtensionPage(sender, "threads.html")) {
    if (typeof message.repository !== "string" || !/^[a-z0-9_.-]+\/[a-z0-9_.-]+$/i.test(message.repository)
        || typeof message.branch !== "string" || !message.branch || message.branch.length > 1024
        || /[\x00-\x1f\x7f]/.test(message.branch)) return false;
    request = { type: "branchLookup", host: "github.com", repository: message.repository.toLowerCase(),
      branch: message.branch, liveBranches: message.liveBranches !== false };
  } else if (message?.type === "directLookup" && isExtensionPage(sender, "threads.html")) {
    const pr = T3Pr.parsePullRequest(message.url);
    if (!pr) return false;
    request = { type: "lookup", host: pr.host, repository: pr.repository, number: pr.number };
  } else if (message?.type === "checkoutLookup" && (isExtensionPage(sender)
      || T3Pr.parsePullRequest(sender.tab?.url) || T3Pr.repositoryPage(sender.tab?.url))) {
    if ([message.environmentId, message.threadId].some(value => typeof value !== "string" || !value
        || value.length > 256 || /[\x00-\x1f\x7f]/.test(value))) return false;
    request = { type: "checkoutLookup", environmentId: message.environmentId, threadId: message.threadId };
  } else if (message?.type === "batchLookup" && T3Pr.isPullRequestList(sender.tab?.url)) {
    if (!Array.isArray(message.urls) || !message.urls.length || message.urls.length > 100) return false;
    const queries = message.urls.map(T3Pr.parsePullRequest);
    if (queries.some(query => !query)) return false;
    request = { type: "batchLookup", queries: queries.map(({ host, repository, number }) => ({ host, repository, number })) };
  } else if (message?.type === "branchLookup") {
    const page = T3Pr.repositoryPage(sender.tab?.url);
    const branch = message.branch;
    if (!page || typeof message.repository !== "string" || page.repository !== message.repository.toLowerCase()
        || typeof branch !== "string" || !branch || branch.length > 1024 || /[\x00-\x1f\x7f]/.test(branch)
        || (page.path && page.path !== branch && !page.path.startsWith(`${branch}/`))) return false;
    request = { type: "branchLookup", host: "github.com", repository: page.repository, branch, liveBranches: message.liveBranches !== false };
  } else if (message?.type === "lookup") {
    const requested = T3Pr.parsePullRequest(message.url);
    const actual = T3Pr.parsePullRequest(sender.tab?.url);
    if (!requested || !actual || requested.key !== actual.key) {
      sendResponse({ ok: false, error: "The pull request changed. Refresh to try again." });
      return false;
    }
    request = { type: "lookup", host: requested.host, repository: requested.repository, number: requested.number, liveBranches: message.liveBranches !== false };
    if (message.head) {
      const head = message.head;
      if (typeof head.repository !== "string" || !/^[a-z0-9_.-]+\/[a-z0-9_.-]+$/i.test(head.repository)
          || typeof head.branch !== "string" || !head.branch || head.branch.length > 1024 || /[\x00-\x1f\x7f]/.test(head.branch)) {
        sendResponse({ ok: false, error: "Invalid source branch." });
        return false;
      }
      request.head = { repository: head.repository.toLowerCase(), branch: head.branch };
    }
  } else return false;

  chrome.runtime.sendNativeMessage(HOST, request).then(
    (result) => sendResponse(result),
    () => sendResponse({ ok: false, error: "The local T3 helper is not installed or could not start. Set it up using github.com/callmemorgan/t3code-pr-links#install, then retry." }),
  );
  return true;
});
