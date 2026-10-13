#!/usr/bin/env python3
"""Chrome native messaging bridge. Never opens T3 state for writing."""
import json
import os
import re
import sqlite3
import struct
import subprocess
import sys
import tempfile
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from urllib.parse import urlsplit

MAX_MESSAGE = 64 * 1024
CONFIG_PATH = Path(__file__).resolve().with_name("config.json")


def load_config():
    if CONFIG_PATH.exists():
        return json.loads(CONFIG_PATH.read_text())
    return {"userdata": str(Path.home() / ".t3" / "userdata")}


def parse_json(value, default):
    try:
        return json.loads(value) if value else default
    except (TypeError, ValueError):
        return default


def normalized_config(value):
    if not isinstance(value, dict):
        raise ValueError("Invalid computer configuration.")
    userdata = value.get("userdata")
    if not isinstance(userdata, str) or not userdata.strip() or len(userdata) > 4096 or re.search(r"[\x00-\x1f\x7f]", userdata):
        raise ValueError("Enter a valid local T3 data directory.")
    remotes = value.get("sshHosts", [])
    if not isinstance(remotes, list) or len(remotes) > 12:
        raise ValueError("Configure at most 12 SSH computers.")
    clean = []
    seen = set()
    names = {"This computer", "all"}
    for remote in remotes:
        if not isinstance(remote, dict):
            raise ValueError("Invalid SSH computer.")
        hostname = remote.get("host", "")
        name = remote.get("name", hostname)
        directory = remote.get("userdata", "~/.t3/userdata")
        if not isinstance(hostname, str) or not re.fullmatch(r"[a-zA-Z0-9][a-zA-Z0-9_.@-]*", hostname):
            raise ValueError("Enter an existing SSH alias or hostname, without command arguments.")
        if not isinstance(name, str) or not name.strip() or len(name) > 200 or re.search(r"[\x00-\x1f\x7f]", name):
            raise ValueError("Enter a computer name of 1 to 200 characters.")
        if name.strip() in names:
            raise ValueError("Give each remote computer a unique display name other than 'This computer' or 'all'.")
        names.add(name.strip())
        if not isinstance(directory, str) or not directory.strip() or len(directory) > 4096 or re.search(r"[\x00-\x1f\x7f]", directory):
            raise ValueError("Enter a valid remote T3 data directory.")
        identity = (hostname, directory)
        if identity in seen:
            raise ValueError("The same SSH computer and data directory is listed twice.")
        seen.add(identity)
        clean.append({"host": hostname, "name": name.strip(), "userdata": directory})
    return {"userdata": str(Path(userdata).expanduser().resolve()), "sshHosts": clean}


def save_config(value):
    config = normalized_config(value)
    CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(mode="w", dir=CONFIG_PATH.parent, prefix=".config-", delete=False) as stream:
            temporary = Path(stream.name)
            json.dump(config, stream, indent=2)
            stream.write("\n")
        os.replace(temporary, CONFIG_PATH)
    finally:
        if temporary:
            temporary.unlink(missing_ok=True)
    return config


def link_key(link):
    if not isinstance(link, dict) or link.get("source") == "stack-dismissed":
        return None
    host = link.get("host")
    if host is None:
        try:
            host = urlsplit(link.get("url", "")).hostname
        except ValueError:
            return None
    repository = link.get("repository")
    number = link.get("number")
    if (not isinstance(host, str) or host.strip().lower() != "github.com"
            or not isinstance(repository, str) or not re.fullmatch(r"[a-zA-Z0-9_.-]+/[a-zA-Z0-9_.-]+", repository.strip())
            or type(number) is not int or not 0 < number <= 9007199254740991):
        return None
    return (host.strip().lower(), repository.strip().lower(), number)


def repository_from_remote(value):
    """Normalize GitHub HTTPS/SSH/scp remotes without returning embedded credentials."""
    if not isinstance(value, str):
        return None
    match = re.fullmatch(r"(?:[^/@:]+@)?github\.com:([^\s]+)", value, re.IGNORECASE)
    if match:
        path = match[1]
    else:
        try:
            url = urlsplit(value)
            if url.hostname is None or url.hostname.lower() != "github.com" or url.scheme not in ("https", "http", "ssh", "git"):
                return None
            path = url.path.lstrip("/")
        except ValueError:
            return None
    path = path.rstrip("/")
    if path.endswith(".git"):
        path = path[:-4]
    return path.lower() if re.fullmatch(r"[a-zA-Z0-9_.-]+/[a-zA-Z0-9_.-]+", path) else None


def git_branch_repository(workspace, branch, cache):
    if not workspace:
        return None
    if workspace not in cache:
        try:
            process = subprocess.run(
                ["/usr/bin/git", "-C", workspace, "config", "--local", "--get-regexp",
                 r"^(remote\..*\.url|branch\..*\.remote)$"],
                text=True, capture_output=True, timeout=2,
            )
            values = {}
            if process.returncode == 0:
                for line in process.stdout.splitlines():
                    pair = line.split(None, 1)
                    if len(pair) == 2:
                        values[pair[0]] = pair[1]
            cache[workspace] = values
        except (OSError, subprocess.TimeoutExpired):
            cache[workspace] = {}
    values = cache[workspace]
    remote = values.get(f"branch.{branch}.remote", "origin")
    if remote == ".":
        remote = "origin"
    # Use the branch's tracking remote or origin. Matching every configured
    # remote would conflate a fork's local branch with the upstream branch.
    return repository_from_remote(values.get(f"remote.{remote}.url"))


def git_current_branch(workspace, cache):
    if not workspace:
        return None
    if workspace not in cache:
        try:
            ref = subprocess.run(["/usr/bin/git", "-C", workspace, "symbolic-ref", "--quiet", "--short", "HEAD"],
                                 text=True, capture_output=True, timeout=1)
            cache[workspace] = ref.stdout.strip() if ref.returncode == 0 else None
        except (OSError, subprocess.TimeoutExpired):
            cache[workspace] = None
    return cache[workspace]


def thread_rows(connection):
    tables = {row[0] for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    if "orchestration_v2_projection_threads" in tables:
        # The V2 payload owns current links; old V1 tables can be stale after migration.
        rows = connection.execute("""
            SELECT thread_id, title, archived_at, updated_at,
                   project_id, json_extract(payload_json, '$.branch') AS branch,
                   json_extract(payload_json, '$.worktreePath') AS worktree_path,
                   json_extract(payload_json, '$.pullRequests') AS links,
                   json_extract(payload_json, '$.linkedPullRequest') AS legacy
            FROM orchestration_v2_projection_threads
            WHERE deleted_at IS NULL
            ORDER BY updated_at DESC
        """)
        for row in rows:
            links = parse_json(row["links"], None)
            if links is None:
                legacy = parse_json(row["legacy"], None)
                links = [legacy] if legacy else []
            yield row, links if isinstance(links, list) else []
    elif "projection_threads" in tables:
        columns = {row[1] for row in connection.execute("PRAGMA table_info(projection_threads)")}
        legacy = "linked_pull_request_json" if "linked_pull_request_json" in columns else "NULL"
        archived = "archived_at" if "archived_at" in columns else "NULL"
        project = "project_id" if "project_id" in columns else "NULL"
        branch = "branch" if "branch" in columns else "NULL"
        worktree = "worktree_path" if "worktree_path" in columns else "NULL"
        rows = connection.execute(f"""
            SELECT thread_id, title, {archived} AS archived_at, updated_at, {legacy} AS legacy,
                   {project} AS project_id, {branch} AS branch, {worktree} AS worktree_path
            FROM projection_threads WHERE deleted_at IS NULL ORDER BY updated_at DESC
        """).fetchall()
        for row in rows:
            if "projection_thread_pull_requests" in tables:
                links = [dict(link) for link in connection.execute(
                    "SELECT host, repository, number, source FROM projection_thread_pull_requests WHERE thread_id = ?",
                    (row["thread_id"],))]
            else:
                link = parse_json(row["legacy"], None)
                links = [link] if link else []
            yield row, links
    else:
        raise ValueError("This database has no supported T3 Code thread table.")


def read_threads(userdata, key=None, head=None, include_keys=False, repository=None, identity=None, live_branches=True, diagnostics=None):
    userdata = Path(userdata).expanduser().resolve()
    database = userdata / "statev2.sqlite"
    if not database.exists():
        database = userdata / "state.sqlite"
    if not database.is_file():
        raise ValueError("T3 Code data was not found. Open T3 Code or configure --userdata when installing.")
    identity_path = userdata / "environment-id"
    if not identity_path.is_file():
        raise ValueError("T3 Code environment-id was not found beside the database.")
    environment_id = identity_path.read_text().strip()
    if not environment_id or len(environment_id) > 256:
        raise ValueError("T3 Code environment-id is invalid.")
    if identity and identity[0] != environment_id:
        return [], str(database)
    threads = []
    # mode=ro includes live WAL changes. immutable=1 would incorrectly ignore them.
    connection = sqlite3.connect(database.as_uri() + "?mode=ro", uri=True, timeout=2)
    connection.row_factory = sqlite3.Row
    try:
        connection.execute("PRAGMA query_only = ON")
        projects = {}
        tables = {row[0] for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        if "projection_projects" in tables:
            columns = {row[1] for row in connection.execute("PRAGMA table_info(projection_projects)")}
            title = "title" if "title" in columns else "NULL"
            projects = {row["project_id"]: dict(row) for row in connection.execute(
                f"SELECT project_id, workspace_root, {title} AS title FROM projection_projects WHERE deleted_at IS NULL")}
        git_cache = {}
        checkout_cache = {}
        deadline = time.monotonic() + 5

        def can_check_git():
            if time.monotonic() < deadline:
                return True
            if diagnostics is not None:
                diagnostics["incomplete"] = True
            return False

        for row, links in thread_rows(connection):
            if identity and row["thread_id"] != identity[1]:
                continue
            keys = {item for item in (link_key(link) for link in links) if item is not None}
            linked = bool(keys) if key is None and head is None and repository is None else key in keys if key else False
            branch_match = False
            checkout_match = False
            if not linked and head and row["branch"] == head["branch"] and can_check_git():
                workspace = row["worktree_path"] or projects.get(row["project_id"], {}).get("workspace_root")
                branch_match = git_branch_repository(workspace, head["branch"], git_cache) == head["repository"].lower()
            if not linked and not branch_match and head and live_branches and can_check_git():
                workspace = row["worktree_path"] or projects.get(row["project_id"], {}).get("workspace_root")
                if git_branch_repository(workspace, head["branch"], git_cache) == head["repository"].lower():
                    checkout_match = git_current_branch(workspace, checkout_cache) == head["branch"]
            repository_match = False
            if repository:
                repository_match = any(item[1] == repository.lower() for item in keys)
                if not repository_match and can_check_git():
                    workspace = row["worktree_path"] or projects.get(row["project_id"], {}).get("workspace_root")
                    repository_match = git_branch_repository(workspace, row["branch"], git_cache) == repository.lower()
            if not linked and not branch_match and not checkout_match and not repository_match and not identity:
                continue
            threads.append({"id": row["thread_id"], "title": row["title"][:2000],
                            "environmentId": environment_id, "archived": row["archived_at"] is not None,
                            "branch": row["branch"], "updatedAt": row["updated_at"],
                            "matchType": "repository" if repository else "linked" if linked else "branch" if branch_match else "checkout"})
            if checkout_match:
                threads[-1]["matchedBranch"] = head["branch"]
            project = projects.get(row["project_id"], {})
            if isinstance(project.get("title"), str):
                threads[-1]["project"] = project["title"][:1000]
            workspace = row["worktree_path"] or project.get("workspace_root")
            if isinstance(workspace, str):
                threads[-1]["workspace"] = workspace[:4096]
                threads[-1]["workspaceType"] = "worktree" if row["worktree_path"] else "project"
            threads[-1]["pullRequests"] = [{"repository": item[1], "number": item[2]} for item in sorted(keys)[:30]]
            if include_keys:
                threads[-1]["_prKeys"] = keys
    finally:
        connection.close()
    return threads, str(database)


def workspace_checkout(thread):
    workspace = thread.get("workspace")
    if not workspace:
        return {"state": "unavailable", "error": "This thread has no saved workspace path."}
    if not Path(workspace).is_dir():
        return {"state": "missing", "error": "The saved workspace no longer exists on this computer."}
    try:
        valid = subprocess.run(["/usr/bin/git", "-C", workspace, "rev-parse", "--is-inside-work-tree"],
                               text=True, capture_output=True, timeout=2)
        if valid.returncode != 0 or valid.stdout.strip() != "true":
            return {"state": "unavailable", "error": "The workspace is not a readable Git checkout."}
        ref = subprocess.run(["/usr/bin/git", "-C", workspace, "symbolic-ref", "--quiet", "--short", "HEAD"],
                             text=True, capture_output=True, timeout=2)
        if ref.returncode == 1:
            return {"state": "detached"}
        if ref.returncode != 0:
            return {"state": "unavailable", "error": "The current branch could not be read."}
        branch = ref.stdout.strip()
        recorded = thread.get("branch")
        return {"state": "branch", "branch": branch, "matchesRecorded": branch == recorded if recorded else None}
    except (OSError, subprocess.TimeoutExpired):
        return {"state": "unavailable", "error": "Git did not respond while checking the workspace."}


def validate_request(request):
    if not isinstance(request, dict):
        raise ValueError("Invalid request.")
    request_type = request.get("type")
    if request_type == "getConfig":
        return
    if request_type == "checkoutLookup":
        for key in ("environmentId", "threadId"):
            value = request.get(key)
            if not isinstance(value, str) or not value or len(value) > 256 or re.search(r"[\x00-\x1f\x7f]", value):
                raise ValueError("Invalid T3 thread identity.")
        return
    if request_type == "saveConfig":
        normalized_config(request.get("config"))
        return
    if request_type == "status":
        return
    if request_type == "repositoryLookup":
        validate_request({"type": "lookup", "host": request.get("host"),
                          "repository": request.get("repository"), "number": 1})
        return
    if request_type == "branchLookup":
        validate_request({"type": "lookup", "host": request.get("host"),
                          "repository": request.get("repository"), "number": 1,
                          "head": {"repository": request.get("repository"), "branch": request.get("branch")},
                          "liveBranches": request.get("liveBranches", True)})
        return
    if request_type == "batchLookup":
        queries = request.get("queries")
        if not isinstance(queries, list) or not 1 <= len(queries) <= 100:
            raise ValueError("A batch must contain 1 to 100 pull requests.")
        for query in queries:
            if not isinstance(query, dict):
                raise ValueError("Invalid batch entry.")
            validate_request({**query, "type": "lookup", "head": None})
        return
    if request_type != "lookup":
        raise ValueError("Unsupported request.")
    if "liveBranches" in request and type(request["liveBranches"]) is not bool:
        raise ValueError("Invalid live branch preference.")
    repository, number = request.get("repository"), request.get("number")
    if (request.get("host") != "github.com" or not isinstance(repository, str)
            or not re.fullmatch(r"[a-zA-Z0-9_.-]+/[a-zA-Z0-9_.-]+", repository)
            or type(number) is not int or not 0 < number <= 9007199254740991):
        raise ValueError("Invalid GitHub pull request.")
    head = request.get("head")
    if head is not None and (not isinstance(head, dict)
            or not isinstance(head.get("repository"), str)
            or not re.fullmatch(r"[a-zA-Z0-9_.-]+/[a-zA-Z0-9_.-]+", head["repository"])
            or not isinstance(head.get("branch"), str) or not head["branch"] or len(head["branch"]) > 1024
            or re.search(r"[\x00-\x1f\x7f]", head["branch"])):
        raise ValueError("Invalid source branch.")


def handle_local_request(request, config):
    validate_request(request)
    if request["type"] == "checkoutLookup":
        threads, _ = read_threads(config["userdata"], identity=(request["environmentId"], request["threadId"]))
        return {"ok": True, "threads": [{"id": thread["id"], "environmentId": thread["environmentId"],
                                        "checkout": workspace_checkout(thread)} for thread in threads]}
    if request["type"] == "status":
        threads, database = read_threads(config["userdata"])
        return {"ok": True, "threadCount": len(threads), "databasePath": database}
    if request["type"] == "batchLookup":
        records, _ = read_threads(config["userdata"], include_keys=True)
        matches = {}
        remaining = 200
        for query in request["queries"]:
            repository, number = query["repository"].lower(), query["number"]
            key = ("github.com", repository, number)
            match_key = f"{repository}#{number}"
            found = [record for record in records if key in record["_prKeys"]]
            found.sort(key=lambda record: record["archived"])
            matches[match_key] = [{field: record[field] for field in ("id", "environmentId", "archived", "matchType")}
                                  | {"title": record["title"][:300], "branch": record["branch"], "updatedAt": record["updatedAt"]}
                                  for record in found[:min(10, remaining)]]
            remaining -= len(matches[match_key])
        return {"ok": True, "matches": matches}
    if request["type"] == "branchLookup":
        diagnostics = {}
        threads, _ = read_threads(config["userdata"], head={"repository": request["repository"], "branch": request["branch"]},
                                  live_branches=request.get("liveBranches", True), diagnostics=diagnostics)
        threads.sort(key=lambda thread: (thread["matchType"] == "checkout", thread["archived"]))
        return {"ok": True, "threads": threads[:100], "lookupWarnings": branch_warnings(diagnostics)}
    if request["type"] == "repositoryLookup":
        diagnostics = {}
        threads, _ = read_threads(config["userdata"], repository=request["repository"], diagnostics=diagnostics)
        threads.sort(key=lambda thread: thread["archived"])
        return {"ok": True, "threads": threads[:200], "threadCount": len(threads), "truncated": len(threads) > 200,
                "lookupWarnings": branch_warnings(diagnostics)}
    repository, number = request["repository"], request["number"]
    diagnostics = {}
    threads, _ = read_threads(config["userdata"], ("github.com", repository.lower(), number), request.get("head"),
                              live_branches=request.get("liveBranches", True), diagnostics=diagnostics)
    threads.sort(key=lambda thread: (match_rank(thread), thread["archived"]))
    return {"ok": True, "threads": threads[:100], "lookupWarnings": branch_warnings(diagnostics)}


def branch_warnings(diagnostics):
    return ["The Git lookup time limit was reached; some workspace matches may be missing."] if diagnostics.get("incomplete") else []


def match_rank(thread):
    return {"linked": 0, "branch": 1, "checkout": 2, "repository": 3}.get(thread.get("matchType"), 4)


def read_remote(request, remote):
    hostname = remote.get("host", "")
    if not isinstance(hostname, str) or not re.fullmatch(r"[a-zA-Z0-9][a-zA-Z0-9_.@-]*", hostname):
        raise ValueError("Invalid configured SSH host.")
    # Send the read-only helper as a Python program over stdin. Nothing is installed
    # or written on the remote machine, and no T3 credentials are extracted.
    source = Path(__file__).read_text()
    remote_config = {"userdata": remote.get("userdata", "~/.t3/userdata")}
    program = (
        "import json\n"
        "namespace = {'__name__': 't3_pr_remote', '__file__': 't3-pr-links-remote.py'}\n"
        f"exec({source!r}, namespace)\n"
        "try:\n"
        f"    result = namespace['handle_local_request']({request!r}, {remote_config!r})\n"
        "except Exception as error:\n"
        "    result = {'ok': False, 'error': str(error)}\n"
        "print(json.dumps(result))\n"
    )
    try:
        process = subprocess.run(
            ["/usr/bin/ssh", "-T", "-o", "BatchMode=yes", "-o", "ConnectTimeout=4",
             "-o", "StrictHostKeyChecking=yes", "-o", "ServerAliveInterval=3",
             "-o", "ServerAliveCountMax=1", hostname, "python3 -"],
            input=program, text=True, capture_output=True, timeout=8,
        )
    except subprocess.TimeoutExpired:
        raise ValueError("Computer did not respond over SSH within 8 seconds.") from None
    if process.returncode != 0:
        raise ValueError("Could not connect over SSH. Check that the computer is online and its saved SSH connection works.")
    try:
        response = json.loads(process.stdout)
    except ValueError:
        raise ValueError("The remote helper returned an invalid response.") from None
    if not isinstance(response, dict) or not response.get("ok"):
        raise ValueError(response.get("error", "Remote T3 data is unavailable.") if isinstance(response, dict) else "Invalid remote response.")
    return response


def handle_request(request, config):
    validate_request(request)
    if request["type"] == "getConfig":
        return {"ok": True, "config": normalized_config(config)}
    if request["type"] == "saveConfig":
        return {"ok": True, "config": save_config(request["config"])}
    remotes = config.get("sshHosts", [])
    if not remotes:
        return handle_local_request(request, config)
    sources = [("This computer", None)] + [(remote.get("name", remote["host"]), remote) for remote in remotes]

    def fetch(source):
        name, remote = source
        try:
            response = read_remote(request, remote) if remote else handle_local_request(request, config)
            return name, response
        except (ValueError, OSError, sqlite3.Error) as error:
            return name, {"ok": False, "error": str(error)}

    with ThreadPoolExecutor(max_workers=min(len(sources), 4)) as executor:
        results = list(executor.map(fetch, sources))
    environments = [{"name": name, "ok": response["ok"],
                     **({"error": response["error"]} if not response["ok"] else {})}
                    for name, response in results]
    if not any(response["ok"] for _, response in results):
        return {"ok": False, "error": "No configured computers could be read.", "environments": environments}
    if request["type"] == "status":
        return {"ok": True, "threadCount": sum(response.get("threadCount", 0) for _, response in results),
                "databasePath": next((response["databasePath"] for _, response in results if response.get("databasePath")), "Remote T3 data"),
                "environments": environments}
    if request["type"] == "batchLookup":
        matches = {}
        remaining = 200
        for query in request["queries"]:
            key = f"{query['repository'].lower()}#{query['number']}"
            found = {}
            for name, response in results:
                for thread in response.get("matches", {}).get(key, []):
                    identity = (thread["environmentId"], thread["id"])
                    found.setdefault(identity, {**thread, "computer": name})
            matches[key] = sorted(found.values(), key=lambda thread: thread.get("archived", False))[:min(10, remaining)]
            remaining -= len(matches[key])
        return {"ok": True, "matches": matches, "environments": environments}
    threads = {}
    for name, response in results:
        for thread in response.get("threads", []):
            identity = (thread["environmentId"], thread["id"])
            threads.setdefault(identity, {**thread, "computer": name})
    ordered = sorted(threads.values(), key=lambda thread: (match_rank(thread), thread.get("archived", False)))
    warnings = [f"{name}: {warning}" for name, response in results for warning in response.get("lookupWarnings", [])]
    limit = 200 if request["type"] == "repositoryLookup" else 100
    return {"ok": True, "threads": ordered[:limit], "environments": environments,
            "threadCount": len(ordered), "truncated": len(ordered) > limit or any(response.get("truncated") for _, response in results),
            "lookupWarnings": warnings}


def read_exact(stream, size):
    chunks = bytearray()
    while len(chunks) < size:
        chunk = stream.read(size - len(chunks))
        if not chunk:
            return None
        chunks.extend(chunk)
    return bytes(chunks)


def serve(input_stream, output_stream, config):
    while True:
        header = read_exact(input_stream, 4)
        if header is None:
            return
        size = struct.unpack("=I", header)[0]
        if size == 0 or size > MAX_MESSAGE:
            return
        data = read_exact(input_stream, size)
        if data is None:
            return
        try:
            request = json.loads(data)
            response = handle_request(request, config)
        except (ValueError, OSError, sqlite3.Error) as error:
            response = {"ok": False, "error": str(error)}
        encoded = json.dumps(response, ensure_ascii=True).encode("utf-8")
        if len(encoded) > 900_000:
            encoded = json.dumps({"ok": False, "error": "Too many matches to display. Narrow the GitHub list or thread filters."}).encode("utf-8")
        output_stream.write(struct.pack("=I", len(encoded)) + encoded)
        output_stream.flush()


if __name__ == "__main__":
    try:
        serve(sys.stdin.buffer, sys.stdout.buffer, load_config())
    except (ValueError, OSError) as error:
        print(str(error), file=sys.stderr)
        sys.exit(1)
