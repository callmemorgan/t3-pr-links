import importlib.util
import io
import json
import sqlite3
import struct
import subprocess
import tempfile
import unittest
from unittest.mock import patch
from pathlib import Path

SPEC = importlib.util.spec_from_file_location("host", Path(__file__).resolve().parents[1] / "native/host.py")
host = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(host)


def link(repository="owner/repo", number=42, source="manual"):
    return {"host": "github.com", "repository": repository, "number": number, "source": source}


class HostTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.userdata = Path(self.temp.name)
        (self.userdata / "environment-id").write_text("environment-1\n")
        self.config = {"userdata": str(self.userdata)}
        self.db = sqlite3.connect(self.userdata / "statev2.sqlite")
        self.addCleanup(self.db.close)
        self.db.execute("PRAGMA journal_mode=WAL")
        self.db.execute("""CREATE TABLE orchestration_v2_projection_threads
            (thread_id TEXT PRIMARY KEY, project_id TEXT, title TEXT, archived_at TEXT,
             updated_at TEXT, deleted_at TEXT, payload_json TEXT)""")
        self.db.commit()

    def add(self, identity, payload, project="project-1", archived=None, deleted=None):
        self.db.execute("INSERT INTO orchestration_v2_projection_threads VALUES (?, ?, ?, ?, ?, ?, ?)",
                        (identity, project, "Title " + identity, archived, "2026-10-12", deleted, json.dumps(payload)))
        self.db.commit()

    def lookup(self, repository="owner/repo", number=42):
        return host.handle_request({"type": "lookup", "host": "github.com", "repository": repository, "number": number}, self.config)

    def test_matches_all_projects_and_archived_but_excludes_deleted_and_dismissed(self):
        self.add("first", {"pullRequests": [link("Owner/Repo")]})
        self.add("archived", {"pullRequests": [link()]}, project="other-project", archived="yesterday")
        self.add("deleted", {"pullRequests": [link()]}, deleted="today")
        self.add("dismissed", {"pullRequests": [link(source="stack-dismissed")]})
        self.add("wrong-repo", {"pullRequests": [link("other/repo")]})
        self.add("wrong-number", {"pullRequests": [link(number=43)]})
        matches = self.lookup()["threads"]
        self.assertEqual({thread["id"] for thread in matches}, {"first", "archived"})
        self.assertTrue(next(t for t in matches if t["id"] == "archived")["archived"])
        self.assertEqual(matches[0]["environmentId"], "environment-1")

    def test_empty_current_links_override_legacy_and_branch_is_not_explicit_link(self):
        legacy = {"repository": "owner/repo", "number": 42, "url": "https://github.com/owner/repo/pull/42"}
        self.add("legacy", {"linkedPullRequest": legacy})
        self.add("unlinked", {"pullRequests": [], "linkedPullRequest": legacy})
        self.add("branch-only", {"branchPullRequest": legacy})
        self.assertEqual([t["id"] for t in self.lookup()["threads"]], ["legacy"])

    def test_multiple_links_and_duplicates_do_not_duplicate_thread(self):
        self.add("multi", {"pullRequests": [link(), link(), link("other/repo", 99)]})
        self.assertEqual(len(self.lookup()["threads"]), 1)
        self.assertEqual(len(self.lookup("other/repo", 99)["threads"]), 1)

    def test_live_wal_and_unlink_are_read_on_each_lookup(self):
        self.assertEqual(self.lookup()["threads"], [])
        self.add("live", {"pullRequests": [link()]})
        self.assertEqual(len(self.lookup()["threads"]), 1)
        self.db.execute("UPDATE orchestration_v2_projection_threads SET payload_json = ?", ('{"pullRequests": []}',))
        self.db.commit()
        self.assertEqual(self.lookup()["threads"], [])

    def test_database_is_opened_read_only(self):
        real_connect = sqlite3.connect
        from unittest.mock import patch
        uris = []
        def connect(database_uri, **kwargs):
            uris.append(database_uri)
            return real_connect(database_uri, **kwargs)
        with patch.object(host.sqlite3, "connect", connect):
            self.lookup()
        self.assertTrue(all(uri.endswith("?mode=ro") for uri in uris))

    def test_v2_is_authoritative_over_stale_v1(self):
        self.db.execute("CREATE TABLE projection_threads (thread_id TEXT, title TEXT, updated_at TEXT, deleted_at TEXT, linked_pull_request_json TEXT)")
        self.db.execute("INSERT INTO projection_threads VALUES ('stale', 'stale', 'today', NULL, ?)",
                        (json.dumps({**link(), "url": "https://github.com/owner/repo/pull/42"}),))
        self.db.commit()
        self.assertEqual(self.lookup()["threads"], [])

    def test_v1_legacy_and_normalized_links(self):
        self.db.execute("DROP TABLE orchestration_v2_projection_threads")
        self.db.execute("CREATE TABLE projection_threads (thread_id TEXT, title TEXT, updated_at TEXT, deleted_at TEXT, linked_pull_request_json TEXT)")
        self.db.execute("INSERT INTO projection_threads VALUES ('legacy', 'legacy', 'today', NULL, ?)",
                        (json.dumps({"repository": "owner/repo", "number": 42, "url": "https://github.com/owner/repo/pull/42"}),))
        self.db.commit()
        self.assertEqual(len(self.lookup()["threads"]), 1)
        self.db.execute("CREATE TABLE projection_thread_pull_requests (thread_id TEXT, host TEXT, repository TEXT, number INTEGER, source TEXT)")
        self.db.execute("INSERT INTO projection_thread_pull_requests VALUES ('legacy', 'github.com', 'owner/repo', 42, 'manual')")
        self.db.commit()
        self.assertEqual(len(self.lookup()["threads"]), 1)
        self.db.execute("DELETE FROM projection_thread_pull_requests")
        self.db.commit()
        self.assertEqual(self.lookup()["threads"], [])

    def test_rejects_invalid_identity_and_non_github_host(self):
        for number in [True, -1, 0, "42", 2**60]:
            with self.assertRaises(ValueError): self.lookup(number=number)
        with self.assertRaises(ValueError): self.lookup(repository="owner/repo/extra")
        with self.assertRaises(ValueError):
            host.handle_request({"type": "lookup", "host": "evil.test", "repository": "owner/repo", "number": 42}, self.config)

    def test_branch_lookup_ignores_unrelated_explicit_pr_links(self):
        self.add("right", {"branch": "Feature/foo", "worktreePath": "/workspace", "pullRequests": [link()]})
        self.add("unrelated", {"branch": "main", "pullRequests": [link()]})
        with patch.object(host, "git_branch_repository", return_value="owner/repo"):
            result = host.handle_request({"type": "branchLookup", "host": "github.com",
                                          "repository": "owner/repo", "branch": "Feature/foo"}, self.config)
        self.assertEqual([t["id"] for t in result["threads"]], ["right"])
        self.assertEqual(result["threads"][0]["matchType"], "branch")
        for branch in [None, "", "bad\n", 123]:
            with self.assertRaises(ValueError):
                host.handle_request({"type": "branchLookup", "host": "github.com",
                                     "repository": "owner/repo", "branch": branch}, self.config)

    def test_repository_browser_combines_pr_links_and_git_remotes(self):
        self.add("linked", {"pullRequests": [link()], "branch": "main"})
        self.add("branch-work", {"branch": "Feature/foo", "worktreePath": "/workspace"})
        self.add("wrong", {"pullRequests": [link("other/repo")], "worktreePath": "/other"})
        with patch.object(host, "git_branch_repository", side_effect=lambda workspace, branch, cache: "owner/repo" if workspace == "/workspace" else None):
            result = host.handle_request({"type": "repositoryLookup", "host": "github.com", "repository": "owner/repo"}, self.config)
        self.assertEqual({t["id"] for t in result["threads"]}, {"linked", "branch-work"})
        self.assertEqual(result["threadCount"], 2)
        self.assertFalse(result["truncated"])
        self.assertTrue(all(t["matchType"] == "repository" for t in result["threads"]))

    def test_matched_thread_metadata_includes_project_workspace_and_safe_prs(self):
        self.db.execute("CREATE TABLE projection_projects (project_id TEXT, title TEXT, workspace_root TEXT, deleted_at TEXT)")
        self.db.execute("INSERT INTO projection_projects VALUES ('project-1', 'Project name', '/workspace', NULL)")
        self.add("metadata", {"pullRequests": [link(), link("other/repo", 43), link("evil/repo/extra", 44)], "worktreePath": "/worktree"})
        thread = self.lookup()["threads"][0]
        self.assertEqual(thread["project"], "Project name")
        self.assertEqual(thread["workspace"], "/worktree")
        self.assertEqual(thread["workspaceType"], "worktree")
        self.assertEqual(thread["pullRequests"], [{"repository": "other/repo", "number": 43}, {"repository": "owner/repo", "number": 42}])

    def test_configuration_saves_atomically_without_touching_t3_data(self):
        config_path = self.userdata / "installed-config.json"
        original = {"userdata": str(self.userdata), "sshHosts": []}
        config_path.write_text(json.dumps(original))
        desired = {"userdata": str(self.userdata), "sshHosts": [{"host": "mac-mini", "name": "Mac Mini"}]}
        with patch.object(host, "CONFIG_PATH", config_path), patch.object(host, "read_remote") as remote:
            loaded = host.handle_request({"type": "getConfig"}, original)
            self.assertEqual(loaded["config"], {**original, "userdata": str(self.userdata.resolve())})
            saved = host.handle_request({"type": "saveConfig", "config": desired}, original)
            self.assertEqual(json.loads(config_path.read_text()), saved["config"])
            self.assertEqual(saved["config"]["sshHosts"][0]["userdata"], "~/.t3/userdata")
            self.assertNotIn("warning", saved)
            missing = self.userdata / "missing"
            moved = host.handle_request({"type": "saveConfig", "config": {**desired, "userdata": str(missing)}}, original)
            self.assertEqual(json.loads(config_path.read_text())["userdata"], str(missing.resolve()))
            self.assertIn(f"T3 Code data was not found in {missing.resolve()}", moved["warning"])
            self.assertIn("Settings", moved["warning"])
            saved = host.handle_request({"type": "saveConfig", "config": desired}, original)
            remote.assert_not_called()
            for bad in [{"userdata": ""}, {"userdata": str(self.userdata), "sshHosts": [{"host": "-oProxyCommand=evil", "name": "Mini"}]},
                        {"userdata": str(self.userdata), "sshHosts": [{"host": "mini", "name": "This computer"}]}]:
                with self.assertRaises(ValueError): host.handle_request({"type": "saveConfig", "config": bad}, original)
            self.assertEqual(json.loads(config_path.read_text()), saved["config"])
        self.assertEqual(list(self.userdata.glob(".config-*")), [])
        self.assertEqual(config_path.stat().st_mode & 0o777, 0o600)

    def test_checkout_checks_only_the_requested_live_thread_workspace(self):
        workspace = self.userdata / "workspace"
        workspace.mkdir()
        subprocess.run(["/usr/bin/git", "init", "-q", "-b", "Feature/foo", str(workspace)], check=True)
        self.add("checkout", {"branch": "Feature/foo", "worktreePath": str(workspace)})
        self.add("deleted-checkout", {"branch": "Feature/foo", "worktreePath": str(workspace)}, deleted="today")
        request = {"type": "checkoutLookup", "environmentId": "environment-1", "threadId": "checkout"}
        checkout = host.handle_request(request, self.config)["threads"][0]["checkout"]
        self.assertEqual(checkout, {"state": "branch", "branch": "Feature/foo", "matchesRecorded": True})
        self.db.execute("UPDATE orchestration_v2_projection_threads SET payload_json = ? WHERE thread_id = 'checkout'",
                        (json.dumps({"branch": "other", "worktreePath": str(workspace)}),))
        self.db.commit()
        checkout = host.handle_request(request, self.config)["threads"][0]["checkout"]
        self.assertFalse(checkout["matchesRecorded"])
        for patch_values in [{"environmentId": "wrong-env"}, {"threadId": "deleted-checkout"}, {"threadId": "missing"}]:
            self.assertEqual(host.handle_request({**request, **patch_values}, self.config)["threads"], [])
        self.assertEqual(host.workspace_checkout({"workspace": str(workspace / "missing")})["state"], "missing")
        self.assertEqual(host.workspace_checkout({})["state"], "unavailable")
        subprocess.run(["/usr/bin/git", "-C", str(workspace), "-c", "core.hooksPath=/dev/null", "-c", "user.name=Test", "-c", "user.email=test@example.test", "commit", "-q", "--allow-empty", "-m", "Test"], check=True)
        subprocess.run(["/usr/bin/git", "-C", str(workspace), "checkout", "-q", "--detach"], check=True)
        self.assertEqual(host.handle_request(request, self.config)["threads"][0]["checkout"]["state"], "detached")

    def test_live_workspace_branch_finds_stale_recorded_branch_and_can_be_disabled(self):
        workspace = self.userdata / "live-workspace"
        workspace.mkdir()
        subprocess.run(["/usr/bin/git", "init", "-q", "-b", "Feature/live", str(workspace)], check=True)
        subprocess.run(["/usr/bin/git", "-C", str(workspace), "config", "remote.origin.url", "https://github.com/owner/repo.git"], check=True)
        self.add("stale-record", {"branch": "old-branch", "worktreePath": str(workspace)})
        request = {"type": "lookup", "host": "github.com", "repository": "owner/repo", "number": 42,
                   "head": {"repository": "owner/repo", "branch": "Feature/live"}}
        result = host.handle_request(request, self.config)
        self.assertEqual(result["threads"][0]["matchType"], "checkout")
        self.assertEqual(result["threads"][0]["branch"], "old-branch")
        self.assertEqual(result["threads"][0]["matchedBranch"], "Feature/live")
        self.assertEqual(host.handle_request({**request, "liveBranches": False}, self.config)["threads"], [])
        self.assertEqual(host.handle_request({**request, "head": {"repository": "other/repo", "branch": "Feature/live"}}, self.config)["threads"], [])

    def test_git_scan_limit_preserves_explicit_matches_and_reports_incomplete_lookup(self):
        self.add("explicit", {"pullRequests": [link()]})
        self.add("candidate", {"branch": "Feature/foo", "worktreePath": "/workspace"})
        moments = iter([0, 10])
        with patch.object(host.time, "monotonic", side_effect=lambda: next(moments, 10)), patch.object(host, "git_branch_repository") as git:
            result = host.handle_request({"type": "lookup", "host": "github.com", "repository": "owner/repo", "number": 42,
                                          "head": {"repository": "owner/repo", "branch": "Feature/foo"}}, self.config)
        self.assertEqual([t["id"] for t in result["threads"]], ["explicit"])
        self.assertEqual(len(result["lookupWarnings"]), 1)
        git.assert_not_called()

    def test_missing_database_returns_error_without_creating_it(self):
        missing = self.userdata / "missing"
        with self.assertRaises(ValueError): host.read_threads(missing)
        self.assertFalse(missing.exists())

    def test_framing_handles_multiple_messages_and_malformed_json(self):
        self.add("linked", {"pullRequests": [link()]})
        messages = [b'{bad', json.dumps({"type": "status"}).encode(),
                    json.dumps({"type": "lookup", "host": "github.com", "repository": "owner/repo", "number": 42}).encode()]
        frames = b"".join(struct.pack("=I", len(data)) + data for data in messages)
        output = io.BytesIO()
        host.serve(io.BytesIO(frames), output, self.config)
        output.seek(0)
        responses = []
        while header := output.read(4):
            responses.append(json.loads(output.read(struct.unpack("=I", header)[0])))
        self.assertFalse(responses[0]["ok"])
        self.assertEqual(responses[1]["threadCount"], 1)
        self.assertEqual(responses[2]["threads"][0]["id"], "linked")

    def test_remote_matches_keep_remote_environment_and_computer_label(self):
        config = {**self.config, "sshHosts": [{"host": "mini", "name": "Mac Mini"}]}
        remote = {"ok": True, "threads": [{"id": "remote-thread", "title": "Remote work", "environmentId": "mini-environment", "archived": False}]}
        with patch.object(host, "read_remote", return_value=remote):
            response = host.handle_request({"type": "lookup", "host": "github.com", "repository": "owner/repo", "number": 42}, config)
        self.assertEqual(response["threads"][0]["environmentId"], "mini-environment")
        self.assertEqual(response["threads"][0]["computer"], "Mac Mini")

    def test_offline_remote_does_not_hide_local_matches(self):
        self.add("local", {"pullRequests": [link()]})
        config = {**self.config, "sshHosts": [{"host": "mini", "name": "Mac Mini"}]}
        with patch.object(host, "read_remote", side_effect=ValueError("Offline")):
            response = host.handle_request({"type": "lookup", "host": "github.com", "repository": "owner/repo", "number": 42}, config)
            status = host.handle_request({"type": "status"}, config)
        self.assertTrue(response["ok"])
        self.assertEqual(response["threads"][0]["id"], "local")
        self.assertEqual(response["environments"][1], {"name": "Mac Mini", "ok": False, "error": "Offline"})
        self.assertEqual(status["threadCount"], 1)

    def test_remote_only_still_works_when_local_t3_data_is_missing(self):
        config = {"userdata": str(self.userdata / "missing"), "sshHosts": [{"host": "mini"}]}
        with patch.object(host, "read_remote", return_value={"ok": True, "threadCount": 12, "databasePath": "remote-data"}):
            response = host.handle_request({"type": "status"}, config)
        self.assertTrue(response["ok"])
        self.assertEqual(response["threadCount"], 12)
        self.assertFalse(response["environments"][0]["ok"])

    def test_invalid_request_does_not_contact_remote_and_duplicate_environments_deduplicate(self):
        config = {**self.config, "sshHosts": [{"host": "mini"}]}
        with patch.object(host, "read_remote") as remote:
            with self.assertRaises(ValueError):
                host.handle_request({"type": "lookup", "host": "evil", "repository": "owner/repo", "number": 42}, config)
            remote.assert_not_called()
        self.add("same", {"pullRequests": [link()]})
        with patch.object(host, "read_remote", return_value=self.lookup()):
            response = host.handle_request({"type": "lookup", "host": "github.com", "repository": "owner/repo", "number": 42}, config)
        self.assertEqual(len(response["threads"]), 1)

    def test_ssh_program_is_read_only_and_needs_no_remote_install(self):
        import subprocess
        self.add("over-ssh", {"pullRequests": [link()]})
        real_run = subprocess.run
        commands = []
        def run(command, **kwargs):
            commands.append(command)
            return real_run([host.sys.executable, "-"], **kwargs)
        remote = {"host": "mini", "userdata": str(self.userdata)}
        with patch.object(host.subprocess, "run", run):
            response = host.read_remote({"type": "lookup", "host": "github.com", "repository": "owner/repo", "number": 42}, remote)
        self.assertEqual(response["threads"][0]["id"], "over-ssh")
        self.assertIn("BatchMode=yes", commands[0])
        self.assertIn("StrictHostKeyChecking=yes", commands[0])
        forwarding = ["-a", "-x", "ClearAllForwardings=yes", "PermitLocalCommand=no"]
        self.assertTrue(set(forwarding) <= set(commands[0][:commands[0].index("mini")]))
        self.assertEqual(commands[0][-1], "python3 -")
        with self.assertRaises(ValueError): host.read_remote({"type": "status"}, {"host": "-oProxyCommand=bad"})

    def test_branch_lookup_uses_repo_and_case_sensitive_branch_without_explicit_pr_link(self):
        repo = self.userdata / "repo"
        host.subprocess.run(["git", "init", "--quiet", str(repo)], check=True)
        host.subprocess.run(["git", "-C", str(repo), "config", "remote.origin.url", "git@github.com:Owner/Repo.git"], check=True)
        self.db.execute("CREATE TABLE projection_projects (project_id TEXT, workspace_root TEXT, deleted_at TEXT)")
        self.db.execute("INSERT INTO projection_projects VALUES ('project-1', ?, NULL)", (str(repo),))
        self.add("branch-only", {"branch": "Feature/foo", "pullRequests": []})
        self.add("case-wrong", {"branch": "feature/foo", "pullRequests": []})
        self.add("linked", {"branch": "unrelated", "pullRequests": [link()]})
        request = {"type": "lookup", "host": "github.com", "repository": "owner/repo", "number": 42,
                   "head": {"repository": "owner/repo", "branch": "Feature/foo"}}
        threads = host.handle_request(request, self.config)["threads"]
        self.assertEqual([t["id"] for t in threads], ["linked", "branch-only"])
        self.assertEqual(threads[1]["matchType"], "branch")
        request["head"]["repository"] = "unrelated/repo"
        self.assertEqual([t["id"] for t in host.handle_request(request, self.config)["threads"]], ["linked"])

    def test_forks_match_origin_or_branch_tracking_remote_but_not_every_remote(self):
        repo = self.userdata / "fork"
        host.subprocess.run(["git", "init", "--quiet", str(repo)], check=True)
        for remote, url in [("origin", "https://github.com/fork/repo.git"), ("upstream", "https://github.com/owner/repo.git")]:
            host.subprocess.run(["git", "-C", str(repo), "config", f"remote.{remote}.url", url], check=True)
        self.assertEqual(host.git_branch_repository(str(repo), "feature", {}), "fork/repo")
        host.subprocess.run(["git", "-C", str(repo), "config", "branch.feature.remote", "upstream"], check=True)
        self.assertEqual(host.git_branch_repository(str(repo), "feature", {}), "owner/repo")

    def test_github_remote_normalization_does_not_match_other_hosts(self):
        for url in ["git@github.com:Owner/Repo.git", "https://token@github.com/Owner/Repo.git", "ssh://git@github.com/Owner/Repo.git", "https://github.com/Owner/Repo/"]:
            self.assertEqual(host.repository_from_remote(url), "owner/repo")
        for url in ["https://github.com.evil/owner/repo", "git@evil:owner/repo", "file:///owner/repo", "https://github.com/owner/repo/extra"]:
            self.assertIsNone(host.repository_from_remote(url))

    def test_invalid_head_is_rejected_before_ssh(self):
        config = {**self.config, "sshHosts": [{"host": "mini"}]}
        for head in [{"repository": "owner/repo", "branch": "bad\nbranch"}, {"repository": "owner/repo", "branch": ""}, {"repository": "owner/repo/extra", "branch": "main"}]:
            with patch.object(host, "read_remote") as remote:
                with self.assertRaises(ValueError):
                    host.handle_request({"type": "lookup", "host": "github.com", "repository": "owner/repo", "number": 42, "head": head}, config)
                remote.assert_not_called()

    def test_batch_looks_up_exact_keys_with_one_database_read_and_excludes_other_threads(self):
        self.add("first", {"pullRequests": [link()]})
        self.add("both", {"pullRequests": [link(), link(number=43)]})
        self.add("unrequested", {"pullRequests": [link(number=44)]})
        real_read = host.read_threads
        with patch.object(host, "read_threads", wraps=real_read) as read:
            response = host.handle_request({"type": "batchLookup", "queries": [
                {"host": "github.com", "repository": "owner/repo", "number": number} for number in (42, 43, 99)]}, self.config)
        self.assertEqual(read.call_count, 1)
        self.assertEqual({t["id"] for t in response["matches"]["owner/repo#42"]}, {"first", "both"})
        self.assertEqual([t["id"] for t in response["matches"]["owner/repo#43"]], ["both"])
        self.assertEqual(response["matches"]["owner/repo#99"], [])
        self.assertNotIn("_prKeys", json.dumps(response))

    def test_batch_keeps_local_matches_when_remote_is_offline(self):
        self.add("local", {"pullRequests": [link()]})
        config = {**self.config, "sshHosts": [{"host": "mini"}]}
        with patch.object(host, "read_remote", side_effect=ValueError("Offline")):
            response = host.handle_request({"type": "batchLookup", "queries": [{"host": "github.com", "repository": "owner/repo", "number": 42}]}, config)
        self.assertTrue(response["ok"])
        self.assertEqual(response["matches"]["owner/repo#42"][0]["computer"], "This computer")
        self.assertFalse(response["environments"][1]["ok"])

    def test_invalid_or_oversized_batches_are_rejected_without_connecting(self):
        query = {"host": "github.com", "repository": "owner/repo", "number": 42}
        config = {**self.config, "sshHosts": [{"host": "mini"}]}
        for queries in [[], [query] * 101, [None], [{**query, "host": "evil"}]]:
            with patch.object(host, "read_remote") as remote:
                with self.assertRaises(ValueError): host.handle_request({"type": "batchLookup", "queries": queries}, config)
                remote.assert_not_called()

    def test_duplicate_batch_rows_do_not_consume_the_result_budget_or_hide_later_prs(self):
        for index in range(10):
            self.add(str(index), {"pullRequests": [link(), link(number=43)]})
        request = {"type": "batchLookup", "queries": [link("Owner/Repo")] * 99 + [link(number=43)]}
        result = host.handle_request(request, self.config)
        self.assertEqual(len(result["matches"]["owner/repo#42"]), 10)
        self.assertEqual(len(result["matches"]["owner/repo#43"]), 10)
        self.assertFalse(result["truncated"])
        self.assertEqual(result["lookupWarnings"], [])
        self.assertEqual(len(request["queries"]), 100)
        config = {**self.config, "sshHosts": [{"host": "mini"}]}
        with patch.object(host, "read_remote", return_value={"ok": True, "matches": {}}) as remote:
            combined = host.handle_request(request, config)
        self.assertEqual(len(remote.call_args.args[0]["queries"]), 2)
        self.assertEqual(len(combined["matches"]["owner/repo#43"]), 10)

    def test_local_pr_and_branch_limits_report_omissions_and_exact_limits_are_complete(self):
        for index in range(101):
            self.add(str(index), {"pullRequests": [link()], "branch": "feature", "worktreePath": "/workspace"})
        pr = self.lookup()
        self.assertEqual(len(pr["threads"]), 100)
        self.assertEqual(pr["threadCount"], 101)
        self.assertTrue(pr["truncated"])
        self.assertEqual(len(pr["lookupWarnings"]), 1)
        with patch.object(host, "git_branch_repository", return_value="owner/repo"):
            branch = host.handle_request({"type": "branchLookup", "host": "github.com", "repository": "owner/repo", "branch": "feature", "liveBranches": False}, self.config)
        self.assertEqual(len(branch["threads"]), 100)
        self.assertTrue(branch["truncated"])
        self.assertEqual(branch["threadCount"], 101)
        self.db.execute("DELETE FROM orchestration_v2_projection_threads WHERE thread_id = '100'")
        self.db.commit()
        exact = self.lookup()
        self.assertFalse(exact["truncated"])
        self.assertEqual(exact["lookupWarnings"], [])

    def test_batch_reports_per_pr_and_total_limits(self):
        for index in range(11):
            self.add(str(index), {"pullRequests": [link(number=number) for number in range(1, 22)]})
        result = host.handle_request({"type": "batchLookup", "queries": [link(number=number) for number in range(1, 22)]}, self.config)
        self.assertEqual(sum(map(len, result["matches"].values())), 200)
        self.assertEqual(result["matches"]["owner/repo#21"], [])
        self.assertTrue(result["truncated"])
        self.assertEqual(len(result["lookupWarnings"]), 1)

    def test_combined_limits_report_omissions_and_preserve_remote_warnings(self):
        self.add("local", {"pullRequests": [link()]})
        config = {**self.config, "sshHosts": [{"host": "mini", "name": "Mini"}]}
        remote = {"ok": True, "threads": [{"id": str(index), "environmentId": "remote", "archived": False, "matchType": "linked"} for index in range(100)]}
        with patch.object(host, "read_remote", return_value=remote):
            result = host.handle_request({"type": "lookup", "host": "github.com", "repository": "owner/repo", "number": 42}, config)
        self.assertEqual(len(result["threads"]), 100)
        self.assertTrue(result["truncated"])
        self.assertEqual(len(result["lookupWarnings"]), 1)
        with patch.object(host, "read_remote", return_value={"ok": True, "matches": {"owner/repo#42": []}, "truncated": True, "lookupWarnings": ["Remote limit reached"]}):
            batch = host.handle_request({"type": "batchLookup", "queries": [link()]}, config)
        self.assertTrue(batch["truncated"])
        self.assertEqual(batch["lookupWarnings"], ["Mini: Remote limit reached"])


if __name__ == "__main__": unittest.main()
