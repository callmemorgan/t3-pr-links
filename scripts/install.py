#!/usr/bin/env python3
"""Register a local, per-user Chrome native messaging host."""
import argparse
import base64
import hashlib
import json
import re
import shlex
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
NAME = "codes.t3.pr_links"


def extension_id(key):
    digest = hashlib.sha256(base64.b64decode(key)).hexdigest()[:32]
    return "".join(chr(ord("a") + int(char, 16)) for char in digest)


def locations():
    if sys.platform == "darwin":
        return (Path.home() / "Library/Application Support/Google/Chrome/NativeMessagingHosts",
                Path.home() / "Library/Application Support/T3 PR Links")
    if sys.platform.startswith("linux"):
        return (Path.home() / ".config/google-chrome/NativeMessagingHosts",
                Path.home() / ".local/share/t3-pr-links")
    raise SystemExit("The local helper installer currently supports macOS and Linux.")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--userdata", help="T3 userdata directory (contains environment-id and statev2.sqlite); preserves the saved directory when omitted")
    parser.add_argument("--uninstall", action="store_true")
    remote_args = parser.add_mutually_exclusive_group()
    remote_args.add_argument("--ssh-host", action="append", help="Also read this computer through an existing SSH connection (repeat for more computers)")
    remote_args.add_argument("--clear-ssh-hosts", action="store_true", help="Remove all saved SSH computers")
    args = parser.parse_args()
    registration, installed = locations()
    manifest_path = registration / f"{NAME}.json"
    if args.uninstall:
        manifest_path.unlink(missing_ok=True)
        if installed.exists():
            shutil.rmtree(installed)
        print("Removed the T3 PR Links local helper. Remove the extension in chrome://extensions separately.")
        return
    key = json.loads((ROOT / "extension/manifest.json").read_text())["key"]
    identity = extension_id(key)
    installed.mkdir(parents=True, exist_ok=True, mode=0o700)
    shutil.copyfile(ROOT / "native/host.py", installed / "host.py")
    config_path = installed / "config.json"
    previous = json.loads(config_path.read_text()) if config_path.exists() else {}
    remotes = previous.get("sshHosts", [])
    if args.clear_ssh_hosts:
        remotes = []
    if args.ssh_host is not None:
        remotes = []
        for hostname in args.ssh_host:
            if not re.fullmatch(r"[a-zA-Z0-9][a-zA-Z0-9_.@-]*", hostname):
                raise SystemExit(f"Invalid SSH host: {hostname}")
            remotes.append({"host": hostname, "name": "Mac Mini" if hostname == "mac-mini" else hostname})
    userdata = args.userdata or previous.get("userdata") or str(Path.home() / ".t3/userdata")
    config_path.write_text(json.dumps({"userdata": str(Path(userdata).expanduser().resolve()), "sshHosts": remotes}, indent=2) + "\n")
    config_path.chmod(0o600)
    launcher = installed / "host"
    launcher.write_text("#!/bin/sh\nexec " + shlex.quote(sys.executable) + " " + shlex.quote(str(installed / "host.py")) + " \"$@\"\n")
    launcher.chmod(0o700)
    registration.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text(json.dumps({
        "name": NAME, "description": "Read local T3 Code pull request links",
        "path": str(launcher), "type": "stdio",
        "allowed_origins": [f"chrome-extension://{identity}/"]
    }, indent=2) + "\n")
    print(f"Local helper installed. Extension ID: {identity}")
    if remotes:
        print("Remote computers: " + ", ".join(remote["name"] for remote in remotes))
    print(f"In chrome://extensions, enable Developer mode, choose Load unpacked, and select:\n{ROOT / 'extension'}")


if __name__ == "__main__":
    main()
