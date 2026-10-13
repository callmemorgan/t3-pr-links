# Privacy policy

T3Code PR Links is an independent community extension for [T3 Code](https://github.com/pingdotgg/t3code), not affiliated with, endorsed by, or sponsored by T3 Code or its developers. It processes the information described below on your configured computers to find and open matching threads. It does not sell your data or send it to the developer, analytics services, or other third-party services.

## What the extension reads

- **GitHub pages.** On github.com, the extension reads the current page URL and repository, pull request, and source branch information. For pull request lists, it also reads visible pull request links and titles. It uses this page context to find matching T3 Code threads. It does not maintain a browsing history or use a GitHub token.
- **T3 Code data on your computers.** A local helper, which you install yourself, reads T3 Code's database in read-only mode. It reads thread titles, identifiers, project and workspace metadata, and pull request links. It does not read conversation messages or T3 Code credentials. When asked, it also reads the current Git branch of a thread's workspace.

## Where data goes

- The extension and the helper communicate only through Chrome's native messaging, on your computer.
- If you add SSH computers in Settings, the helper runs a read-only query on those computers over your existing SSH connection, using your own SSH configuration and keys. Results come back to your computer only.
- Nothing is sent to the developer, to analytics services, or to any other server.

## What is stored

- **Chrome local storage:** your display preferences, such as filters and thread ordering. These stay in your Chrome profile and are not synced.
- **Helper configuration:** your T3 data directory and the SSH computers you add, saved in the helper's own folder on your computer.

Uninstalling the extension removes its Chrome storage. Running `python3 scripts/install.py --uninstall` removes the helper and its configuration.

## Changes

Changes to this policy are published in this file in the [GitHub repository](https://github.com/callmemorgan/t3-pr-links).

## Contact

Open an issue at https://github.com/callmemorgan/t3-pr-links/issues.
