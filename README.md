# T3 PR Links

A Chrome extension that adds **Open in T3 Code** below a GitHub pull request title when that PR is linked to a T3 Code thread on this computer or a configured remote computer. Multiple matching threads appear as separate links.

An independent community extension for [T3 Code](https://github.com/pingdotgg/t3code). Licensed under MIT.

## Install

Requires Google Chrome, T3 Code, Python 3.9 or newer, and Git on macOS or Linux. Windows installation is not currently supported. Node.js is needed only to run development tests.

The extension has two parts: the Chrome extension, and a small local helper that reads T3 Code's data for it. Chrome extensions can't read local files, and the Chrome Web Store can't install the helper, so you set that part up once from a terminal:

```sh
git clone https://github.com/callmemorgan/t3-pr-links.git
cd t3-pr-links
python3 scripts/install.py
```

Then:

1. Install **T3 PR Links** from the Chrome Web Store.
2. Reload any GitHub tabs you already had open. The extension toolbar popup can check the connection.

The installer copies the helper into your user application data directory, so you can delete the cloned folder afterwards and nothing needs to stay running. To update the helper, pull the latest version and run the installer again. Chrome may ask to open T3 Code the first time you click a thread link.

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

You can manage the local data directory and up to 12 SSH computers from **Settings** in the popup, or from Chrome’s extension Options. Each computer has a display name, existing SSH alias, and T3 data directory. **Check saved connections** reports connectivity without changing the form.

Repeat `--ssh-host` to include more computers. This uses your existing SSH keys and known host records, with no password prompts. These connections never forward your SSH agent, X11, or ports, or run a configured `LocalCommand`, even if your SSH config enables them. The remote computer needs Python 3 and T3 Code data at `~/.t3/userdata`. The helper runs a read-only query over SSH; it does not install files or start a T3 server on that computer. Matches show the computer name and open the correct T3 environment.

Remote computers are explicitly configured; the extension does not automatically import T3's encrypted connection catalog. If a computer is offline, available computers still return matches and the toolbar popup reports which computer could not be read. Adding SSH connections does not require any extra Chrome permissions. Reinstalling preserves your saved local directory and remote computers unless you explicitly supply replacements. `--ssh-host` replaces the remote list; `--clear-ssh-hosts` removes it.

Links use T3 Code's `t3code://threads/<environment-id>/<thread-id>` desktop scheme. T3 Code must be installed and recognize that environment. The extension works on github.com, including private PRs and their Files, Commits, and Checks tabs. GitHub Enterprise domains are not currently included.

Opening a new PR, branch, or PR list checks your configured computers. GitHub navigation updates the displayed links automatically. **Refresh** checks again immediately; returning to the same page reuses its results, with no periodic polling. The PR panel shows the thread link, title, and computer; inferred matches also show the matching branch and an explanatory badge. Workspace paths, related PRs, copying, and checkout checks live in the thread browser or popup. Unavailable computers are called out on the PR so an incomplete search does not look like a complete search. PRs with no matching thread and no connection problems display no extra panel.

The toolbar popup shows matches and source-branch information for the current PR, with direct T3 links and its own Refresh button. On other pages it shows connection diagnostics. It communicates with the existing GitHub content script and needs no additional tab-reading permissions.

PR lists show **T3 ↗** badges beside explicitly linked PRs. A single match opens directly; multiple matches have a menu with a link for each thread. Repository PR lists, GitHub's global PR list, and PR results in issue/search lists are supported. List lookups are batched (up to 100 visible titles), with one read of each configured computer's database. Branch inference is available on PR details, where GitHub exposes the source branch, rather than on list rows.

Duplicate PR rows count once in the lookup and popup groups. PR/branch lookups return up to 100 threads; list lookups return up to 10 per PR and 200 total thread entries. If a row or thread limit omits results, the toolbar shows an amber **!** and the popup explains the incomplete coverage. The same warnings appear on PR/branch panels and in thread-browser exports when applicable.

Branch lookups also work on repository home pages, branch folders, and files. The selected branch comes from GitHub’s branch picker, so file paths are not mistaken for branch names. Tag and commit snapshots are excluded. The toolbar popup follows branch pages too.

On branch pages, and on PRs where GitHub shows the source branch, click the branch name in the popup to open a prefilled branch lookup in the thread browser, even when the current lookup found no branch match. For forked PRs this shortcut uses the source repository, preserving the exact branch name.

The popup’s collapsed **Filters** section lets you include/exclude archived threads or branch matches, select a computer, and turn list badges off. Preferences are saved locally in Chrome and update open GitHub pages immediately. If filters hide all matches, the page offers **Show all threads** so matches do not disappear without explanation. Filters affect display, not which configured computers are checked.

**Copy link** in the thread browser or popup copies the T3 desktop link. If the clipboard is unavailable, a selected text field lets you copy it manually.

The popup’s **Browse repository threads** and **Find threads** links open the thread browser. It finds threads associated with that GitHub repository through a linked PR or their workspace Git remote, including threads without a PR. Search the loaded results by thread title, branch, or project. Results show computer coverage and any limit (up to 200 threads); saved display filters apply. You can also enter a repository manually.

In the thread browser, expand **Look up a specific branch** and enter an exact branch name to check recorded and current workspace branches across your configured computers. Branch names are case-sensitive and may contain slashes. Use the fork’s repository for forked branches. Leave Branch blank to browse the repository or look up a pasted PR. The live-workspace preference applies to these lookups, and JSON exports retain the queried branch and observed workspace branch separately.

The thread browser’s **Lookup and display filters** also lets you choose a computer, include archived threads or inferred matches, and control live-workspace lookup. These preferences are shared with the popup and GitHub panels. Display changes filter the loaded results without another computer scan; changing live-workspace lookup rechecks an active branch query. When search or filters hide results, **Show all loaded threads** clears the search and resets display filters without altering lookup settings. Search also checks the observed workspace branch when it differs from T3’s saved branch.

**Check current checkout** in the thread browser reads Git’s current branch from that thread’s saved workspace. It distinguishes a matching branch, a different branch, detached HEAD, and a missing/unreadable workspace. The check runs only when clicked and never changes the checkout.

The toolbar icon shows the visible match count on PR/branch pages, or the number of linked PRs on a list. An amber **!** means some computers could not be checked; its tooltip includes the count.

**Export shown links** downloads a JSON file containing the repository browser’s displayed threads, their T3 links and associated PR URLs, plus the lookup timestamp and coverage/limit information. Search and display filters determine what is exported.

Use **Alt+Shift+T** (Option+Shift+T on Mac) to open the toolbar popup. Chrome lets you change or assign this shortcut at `chrome://extensions/shortcuts` if it conflicts with another extension.

The popup also groups the current PR list’s linked threads by PR, reusing the list’s in-flight lookup. From any page, **Find threads** opens the thread browser. A pasted PR URL checks explicit T3 links; visiting that PR on GitHub also enables source-branch/workspace matching. Thread ordering is saved across the popup, panels, list menus, and thread browser.

## Local data access

Chrome extensions cannot directly open a local SQLite database. A small Python 3 native messaging helper reads the database for them. Chrome launches the helper on demand and only this extension's fixed ID is allowed to call it. The extension needs `nativeMessaging` and local `storage` permissions and a content script on github.com; it needs no GitHub token or T3 authentication token.

The helper opens SQLite in **read-only mode**, including committed changes in its WAL. It reads thread titles, identifiers, project/worktree metadata, and PR links. Responses contain only threads matching the requested PR, branch, visible PR list, or repository. It does not read conversation messages or T3 credentials, modify T3 data, or send your data to an external service. The settings page can write only the helper’s own computer configuration. SSH queries use your existing SSH authentication. The popup reports connection errors for each configured computer.

V2 data (`statev2.sqlite`) takes precedence over legacy `state.sqlite`. Empty current PR lists stay empty, even if a migrated legacy field still contains an old link.

The full privacy policy is in [PRIVACY.md](PRIVACY.md).

## Remove

Remove the extension from `chrome://extensions`, then run this from a clone of the repository:

```sh
python3 scripts/install.py --uninstall
```

## Development

To run your working copy, run `python3 scripts/install.py`, open `chrome://extensions`, turn on **Developer mode**, click **Load unpacked**, and select the `extension` folder. The manifest's `key` gives the unpacked build the same ID as the store build, so the same helper serves both. Disable the store version while the unpacked one is loaded.

```sh
npm ci
npm test
```

To release, bump the version in `extension/manifest.json`, `package.json` and `package-lock.json`, then run `npm run package`. It writes `dist/t3-pr-links-<version>.zip` without the manifest `key`, ready to upload in the [Chrome Web Store developer dashboard](https://chrome.google.com/webstore/devconsole).

Tests cover exact matching across projects, unlinking, archived/deleted threads, V1 compatibility, read-only SQLite access and live WAL changes, native message framing, SSH aggregation, GitHub navigation and stale-response guards, fork/source branch handling, saved filters, manual refresh caching, lookup limits, safe rendering, the background message boundary, and installer config preservation. The extension itself has no build step or runtime dependencies.

Use Node.js 22 or newer for the tests. GitHub Actions runs the suite on Linux. Bug reports and pull requests are welcome; use synthetic examples rather than posting your T3 databases, private thread links, or computer configuration.

## Review map

- `extension/common.js`: GitHub page and branch parsing.
- `extension/content.js` / `list.js`: PR/branch panels, list badges, navigation, and popup context.
- `extension/ui.js` / `settings.js` / `badge.js`: safe DOM rendering, saved preferences, and toolbar indicators.
- `extension/popup.*`, `threads.*`, `options.*`: popup, searchable/exportable thread browser, and computer settings.
- `extension/background.js`: validated extension message boundary and native messaging.
- `native/host.py`: read-only T3/SQLite and Git lookups, SSH aggregation, checkout verification, and helper configuration.
- `scripts/install.py`: per-user helper installation/update.
- `scripts/package.py`: Chrome Web Store upload zip.
- `scripts/preview.py`: temporary localhost preview using sample data only; never reads T3 or opens SSH.

For visual checks, run `python3 scripts/preview.py` and open the printed URL. Stop with Ctrl+C.

The same preview server exposes `/pr.html` for the compact GitHub panel, `/popup.html`, and `/options.html`. Every preview uses sample data only.

Version 1.2.0 adds branch and live-workspace lookup, list badges and list-aware popup, details/checkout checks, saved filtering and sorting, repository/manual-PR search, JSON link export, computer settings, toolbar counts, and the keyboard shortcut. Reload the installed extension in `chrome://extensions` after updates, then reload GitHub tabs. The popup shows the version Chrome actually loaded.

Version 1.2.1 simplifies the GitHub panel to thread links, titles, computers, and matching branches for inferred results. Additional tools and workspace metadata remain in the popup and thread browser.

Version 1.3.0 adds manual branch lookup in the thread browser and fixes manual PR lookup when the browser was opened with repository query parameters.

Version 1.3.1 adds the shared lookup/display filter controls to the thread browser, recovery for hidden results, and search by observed workspace branch.

Version 1.4.0 redesigns the popup as a compact thread launcher and removes periodic polling. New pages and manual Refresh still query the configured computers.

Version 1.4.1 deduplicates PR-list lookup/grouping and reports omitted rows or threads consistently through existing coverage warnings.

Version 1.5.0 makes the popup’s branch name a shortcut to an exact branch lookup (see [What matches](#what-matches)).

Version 1.5.1 fixes the extension message boundary so Settings, the thread browser, the branch shortcut, checkout checks, and saved-connection checks reach the helper when those pages open in a tab. The branch shortcut now appears whenever the PR’s source branch is known, keeps exact branch names, uses the standard link colour, and has one consistent tooltip. Unattended SSH lookups disable agent, X11, and port forwarding; render state no longer leaves lookup data in the GitHub page; the preview adds `/popup.html?fork=1`.

### Verification and review handoff

The v1.5.1 automated checks are both suites, run by `npm test`; [Development](#development) describes their coverage and CI. A throwaway headless Chrome profile with a stub helper confirmed that the Settings page and thread browser reach the helper when opened in a tab; the sample-data previews replace `chrome.runtime.sendMessage`, so they cannot exercise that boundary.

Manual Chrome previews checked the compact PR panel, popup, incomplete-lookup warning, thread-browser filters, and branch shortcut. Use `/popup.html?branch=1` (branch page) and `/popup.html?fork=1` (forked PR, whose shortcut should find the fork’s thread) to exercise the [branch shortcut](#what-matches), and `/popup.html?limited=1` for the warning. Previews verify rendering and interaction with synthetic responses; reload the installed extension and GitHub tabs to verify the actual Chrome/native integration after an update.

Live native-protocol checks on the installed helper verified explicit PR matching and current-workspace branch matching across the local computer and a configured SSH computer, plus deduplication of mixed-case repeated PR queries. Those checks are separate from the sample-data browser preview.

Review areas: GitHub DOM selectors may need updates as GitHub changes its layout. Remote computers require explicitly configured SSH aliases. The CLI installer preserves settings, but its SSH argument validation does not yet share the settings page’s full normalized-config validation, and its config write is not atomic; the native settings save path is atomic.
