(function (root) {
  function parsePullRequest(value) {
    try {
      const url = new URL(value);
      if (url.protocol !== "https:" || url.hostname !== "github.com" || url.port || url.username || url.password) return null;
      const match = /^\/([a-z0-9_.-]+)\/([a-z0-9_.-]+)\/pull\/([1-9]\d*)(?:\/.*)?$/i.exec(url.pathname);
      if (!match || !Number.isSafeInteger(Number(match[3]))) return null;
      const repository = `${match[1]}/${match[2]}`.toLowerCase();
      const number = Number(match[3]);
      return { host: "github.com", repository, number, key: `${repository}#${number}` };
    } catch { return null; }
  }

  function threadUrl(environmentId, threadId) {
    if (typeof environmentId !== "string" || !environmentId || typeof threadId !== "string" || !threadId) return null;
    return `t3code://threads/${encodeURIComponent(environmentId)}/${encodeURIComponent(threadId)}`;
  }

  function parseBranchLink(value) {
    try {
      const url = new URL(value, "https://github.com");
      if (url.protocol !== "https:" || url.hostname !== "github.com" || url.port) return null;
      const match = /^\/([a-z0-9_.-]+)\/([a-z0-9_.-]+)\/tree\/(.+)$/i.exec(url.pathname);
      if (!match) return null;
      const branch = decodeURIComponent(match[3]);
      if (!branch || branch.length > 1024 || /[\x00-\x1f\x7f]/.test(branch)) return null;
      return { repository: `${match[1]}/${match[2]}`.toLowerCase(), branch };
    } catch { return null; }
  }

  function headBranch(document) {
    const header = document.querySelector('[data-component="PageHeader"][data-has-nav]')
      || document.querySelector("#partial-discussion-header") || document.querySelector(".gh-header");
    if (!header) return null;
    const links = Array.from(header.querySelectorAll('a[data-component="BranchName"], .commit-ref a[href], a.commit-ref[href]'));
    // PR headers list the destination first and source second. Never infer from
    // arbitrary /tree/ links in comments, which may point at unrelated branches.
    if (links.length < 2) return null;
    return parseBranchLink(links.at(-1).getAttribute("href"));
  }

  function isPullRequestList(value) {
    try {
      const url = new URL(value);
      return url.protocol === "https:" && url.hostname === "github.com" && !url.port
        && /^\/(?:pulls(?:\/.*)?|issues(?:\/.*)?|search|[a-z0-9_.-]+\/[a-z0-9_.-]+\/(?:pulls|issues)(?:\/.*)?)\/?$/i.test(url.pathname);
    } catch { return false; }
  }

  function repositoryPage(value) {
    try {
      const url = new URL(value);
      if (url.protocol !== "https:" || url.hostname !== "github.com" || url.port || url.username || url.password) return null;
      const match = /^\/([a-z0-9_.-]+)\/([a-z0-9_.-]+)(?:\/(tree|blob)\/(.+))?\/?$/i.exec(url.pathname);
      if (!match) return null;
      return { repository: `${match[1]}/${match[2]}`.toLowerCase(), path: match[4] ? decodeURIComponent(match[4]) : null };
    } catch { return null; }
  }

  function branchPage(document, value) {
    const page = repositoryPage(value);
    if (!page) return null;
    const picker = document.querySelector('main button[data-icv-name="Switch branches/tags"]')
      || document.querySelector('main button[id^="ref-picker-"]');
    // The URL also contains folders/files and may identify a tag or commit.
    // Read the actual branch selector, and reject a stale selector during SPA navigation.
    if (!picker || picker.dataset.loading === "true" || !picker.querySelector(".octicon-git-branch")) return null;
    const label = picker.getAttribute("aria-label") || "";
    const branch = label.endsWith(" branch") ? label.slice(0, -7) : null;
    if (!branch || branch.length > 1024 || /[\x00-\x1f\x7f]/.test(branch)) return null;
    if (page.path && page.path !== branch && !page.path.startsWith(`${branch}/`)) return null;
    return { repository: page.repository, branch };
  }

  function pageContext(document, value) {
    const pr = parsePullRequest(value);
    const head = pr ? headBranch(document) : null;
    const branch = pr ? null : branchPage(document, value);
    const key = pr?.key || (branch ? `branch:${branch.repository}:${branch.branch}` : null);
    let repository = pr?.repository || branch?.repository || repositoryPage(value)?.repository || null;
    if (!repository && isPullRequestList(value)) {
      const match = /^\/([a-z0-9_.-]+)\/([a-z0-9_.-]+)\/(pulls|issues)(?:\/|$)/i.exec(new URL(value).pathname);
      if (match) repository = `${match[1]}/${match[2]}`.toLowerCase();
    }
    return { pr, head, branch, repository, key, query: key ? JSON.stringify([key, head]) : null };
  }

  root.T3Pr = { parsePullRequest, threadUrl, parseBranchLink, headBranch, isPullRequestList, repositoryPage, branchPage, pageContext };
  if (typeof module !== "undefined") module.exports = root.T3Pr;
})(globalThis);
