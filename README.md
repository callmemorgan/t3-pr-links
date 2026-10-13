# T3 PR Links

A Chrome extension that adds **Open in T3 Code** below a GitHub pull request title when that PR is linked to a T3 Code thread on this computer or a configured remote computer. Multiple matching threads appear as separate links.

An independent community extension for [T3 Code](https://github.com/pingdotgg/t3code). Licensed under MIT.

## Install

Requires Google Chrome, T3 Code, Python 3.9 or newer, and Git on macOS or Linux. Windows installation is not currently supported. Node.js is needed only to run development tests.

```sh
git clone https://github.com/callmemorgan/t3-pr-links.git
cd t3-pr-links
```

1. Run `python3 scripts/install.py` from this folder. This installs the local helper for your Chrome profile on macOS or Linux.
2. Open `chrome://extensions` in Google Chrome and turn on **Developer mode**.
3. Click **Load unpacked** and select the `extension` folder in this project.
4. Reload any GitHub tabs you already had open. The extension toolbar popup can check the connection.

Keep the `extension` folder in place while the extension is loaded. The helper is copied into your user application data directory, so it does not need a terminal or server left running. Chrome may ask to open T3 Code the first time you click a thread link.

## What matches

The helper checks explicit PR links on **all threads across all projects** in your configured T3 Code environments. Matching uses GitHub's repository name and PR number, including all PRs linked to a thread. Archived threads are included; deleted threads and dismissed stack links are excluded. PR URLs mentioned only in chat messages do not count as explicit links.

The extension also finds threads whose **recorded branch and Git repository** match the PR's source branch. These are labeled **Branch match** and appear after explicit PR links. For forked PRs it uses the source repository, not the destination. Git's branch tracking remote takes precedence over `origin`; unrelated repositories with the same branch name are excluded. Missing project/worktree directories cannot produce a branch match. If the saved branch is stale, the extension also checks current workspace branches. These appear as **Workspace match**, after recorded-branch matches, and identify the branch observed at lookup time. They associate a thread’s saved workspace with the PR’s source; they do not imply that the thread created the PR. The popup’s live-workspace toggle disables this fallback. Git scans have a five-second budget per computer, with a visible warning if some workspace checks were skipped. Explicit links remain available even when that limit is reached.

A branch match reflects T3's recorded branch and does not independently verify the current checkout or imply that the thread created the PR.

The default data directory is `~/.t3/userdata`. To use another local T3 environment, reinstall with:

```sh
python3 scripts/install.py --userdata /path/to/t3/userdata
```

To include a connected computer, use its existing SSH alias:

```sh
python3 scripts/install.py --ssh-host mac-mini
```

You can manage the local data directory and up to 12 SSH computers from **Computer settings** in the popup, or from Chrome’s extension Options. Each computer has a display name, existing SSH alias, and T3 data directory. **Check saved connections** reports connectivity without changing the form.

Repeat `--ssh-host` to include more computers. This uses your existing SSH keys and known host records, with no password prompts. The remote computer needs Python 3 and T3 Code data at `~/.t3/userdata`. The helper runs a read-only query over SSH; it does not install files or start a T3 server on that computer. Matches show the computer name and open the correct T3 environment.

Remote computers are explicitly configured; the extension does not automatically import T3's encrypted connection catalog. If a computer is offline, available computers still return matches and the toolbar popup reports which computer could not be read. Adding SSH connections does not require any extra Chrome permissions. Reinstalling preserves your saved local directory and remote computers unless you explicitly supply replacements. `--ssh-host` replaces the remote list; `--clear-ssh-hosts` removes it.

Links use T3 Code's `t3code://threads/<environment-id>/<thread-id>` desktop scheme. T3 Code must be installed and recognize that environment. The extension works on github.com, including private PRs and their Files, Commits, and Checks tabs. GitHub Enterprise domains are not currently included.

While a GitHub tab is visible, links refresh every 30 seconds and when you return to the tab. GitHub navigation updates the displayed links automatically. **Refresh** checks again immediately. The PR panel shows the thread link, title, and computer; inferred matches also show the matching branch and an explanatory badge. Workspace paths, related PRs, copying, and checkout checks live in the thread browser or popup. Unavailable computers are called out on the PR so an incomplete search does not look like a complete search. PRs with no matching thread and no connection problems display no extra panel.

The toolbar popup shows matches and source-branch information for the current PR, with direct T3 links and its own Refresh button. On other pages it shows connection diagnostics. It communicates with the existing GitHub content script and needs no additional tab-reading permissions.

PR lists show **T3 ↗** badges beside explicitly linked PRs. A single match opens directly; multiple matches have a menu with a link for each thread. Repository PR lists, GitHub's global PR list, and PR results in issue/search lists are supported. List lookups are batched (up to 100 visible titles), with one read of each configured computer's database. Branch inference is available on PR details, where GitHub exposes the source branch, rather than on list rows.

Branch lookups also work on repository home pages, branch folders, and files. The selected branch comes from GitHub’s branch picker, so file paths are not mistaken for branch names. Tag and commit snapshots are excluded. The toolbar popup follows branch pages too.

The popup’s **Lookup and display filters** lets you include/exclude archived threads or branch matches, select a computer, and turn list badges off. Preferences are saved locally in Chrome and update open GitHub pages immediately. If filters hide all matches, the page offers **Show all threads** so matches do not disappear without explanation. Filters affect display, not which configured computers are checked.

**Copy link** in the thread browser or popup copies the T3 desktop link. If the clipboard is unavailable, a selected text field lets you copy it manually.

The popup links to a **Repository threads** browser. It finds threads associated with that GitHub repository through a linked PR or their workspace Git remote, including threads without a PR. Search the loaded results by thread title, branch, or project. Results show computer coverage and any limit (up to 200 threads); saved display filters apply. You can also enter a repository manually.

In the thread browser, expand **Look up a specific branch** and enter an exact branch name to check recorded and current workspace branches across your configured computers. Branch names are case-sensitive and may contain slashes. Use the fork’s repository for forked branches. Leave Branch blank to browse the repository or look up a pasted PR. The live-workspace preference applies to these lookups, and JSON exports retain the queried branch and observed workspace branch separately.

**Check current checkout** in the thread browser reads Git’s current branch from that thread’s saved workspace. It distinguishes a matching branch, a different branch, detached HEAD, and a missing/unreadable workspace. The check runs only when clicked and never changes the checkout.

The toolbar icon shows the visible match count on PR/branch pages, or the number of linked PRs on a list. An amber **!** means some computers could not be checked; its tooltip includes the count.

**Export shown links** downloads a JSON file containing the repository browser’s displayed threads, their T3 links and associated PR URLs, plus the lookup timestamp and coverage/limit information. Search and display filters determine what is exported.

Use **Alt+Shift+T** (Option+Shift+T on Mac) to open the toolbar popup. Chrome lets you change or assign this shortcut at `chrome://extensions/shortcuts` if it conflicts with another extension.

The popup also groups the current PR list’s linked threads by PR, reusing the list’s in-flight lookup. From any page, **Find threads by repository or PR URL** opens the thread browser. A pasted PR URL checks explicit T3 links; visiting that PR on GitHub also enables source-branch/workspace matching. Thread ordering is saved across the popup, panels, list menus, and thread browser.

## Local data access

Chrome extensions cannot directly open a local SQLite database. A small Python 3 native messaging helper reads the database for them. Chrome launches the helper on demand and only this extension's fixed ID is allowed to call it. The extension needs `nativeMessaging` and local `storage` permissions and a content script on github.com; it needs no GitHub token or T3 authentication token.

The helper opens SQLite in **read-only mode**, including committed changes in its WAL. It reads thread titles, identifiers, project/worktree metadata, and PR links. Responses contain only threads matching the requested PR, branch, visible PR list, or repository. It does not read conversation messages or T3 credentials, modify T3 data, or send your data to an external service. The settings page can write only the helper’s own computer configuration. SSH queries use your existing SSH authentication. The popup reports connection errors for each configured computer.

V2 data (`statev2.sqlite`) takes precedence over legacy `state.sqlite`. Empty current PR lists stay empty, even if a migrated legacy field still contains an old link.

## Remove

Remove the extension from `chrome://extensions`, then run:

```sh
python3 scripts/install.py --uninstall
```

## Development

```sh
npm ci
npm test
```

Tests cover exact matching across projects, unlinking, archived/deleted threads, V1 compatibility, live WAL changes, native message framing, GitHub navigation, safe rendering, and the background message boundary. The extension itself has no build step or runtime dependencies.

Use Node.js 22 or newer for the tests. GitHub Actions runs the suite on Linux. Bug reports and pull requests are welcome; use synthetic examples rather than posting your T3 databases, private thread links, or computer configuration.

## Review map

- `extension/common.js`: GitHub page and branch parsing.
- `extension/content.js` / `list.js`: PR/branch panels, list badges, navigation, and popup context.
- `extension/ui.js` / `settings.js` / `badge.js`: safe DOM rendering, saved preferences, and toolbar indicators.
- `extension/popup.*`, `threads.*`, `options.*`: popup, searchable/exportable thread browser, and computer settings.
- `extension/background.js`: validated extension message boundary and native messaging.
- `native/host.py`: read-only T3/SQLite and Git lookups, SSH aggregation, checkout verification, and helper configuration.
- `scripts/install.py`: per-user helper installation/update.
- `scripts/preview.py`: temporary localhost preview using sample data only; never reads T3 or opens SSH.

For visual checks, run `python3 scripts/preview.py` and open the printed URL. Stop with Ctrl+C.

The same preview server exposes `/pr.html` for the compact GitHub panel, `/popup.html`, and `/options.html`. Every preview uses sample data only.

Version 1.2.0 adds branch and live-workspace lookup, list badges and list-aware popup, details/checkout checks, saved filtering and sorting, repository/manual-PR search, JSON link export, computer settings, toolbar counts, and the keyboard shortcut. Reload the installed extension in `chrome://extensions` after updates, then reload GitHub tabs. The popup shows the version Chrome actually loaded.

Version 1.2.1 simplifies the GitHub panel to thread links, titles, computers, and matching branches for inferred results. Additional tools and workspace metadata remain in the popup and thread browser.

Version 1.3.0 adds manual branch lookup in the thread browser and fixes manual PR lookup when the browser was opened with repository query parameters.
