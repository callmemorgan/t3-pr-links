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
NAME = "com.callmemorgan.t3code_pr_links"
# Versions before 1.5.3 registered this name and installed to the legacy folders below.
LEGACY_NAME = "codes.t3.pr_links"


def extension_id(key):
    digest = hashlib.sha256(base64.b64decode(key)).hexdigest()[:32]
    return "".join(chr(ord("a") + int(char, 16)) for char in digest)


def locations():
    if sys.platform == "darwin":
        support = Path.home() / "Library/Application Support"
        return support / "Google/Chrome/NativeMessagingHosts", support / "T3Code PR Links", support / "T3 PR Links"
    if sys.platform.startswith("linux"):
        share = Path.home() / ".local/share"
        return Path.home() / ".config/google-chrome/NativeMessagingHosts", share / "t3code-pr-links", share / "t3-pr-links"
    raise SystemExit("The local helper installer currently supports macOS and Linux.")


def remove_legacy(registration, legacy):
    (registration / f"{LEGACY_NAME}.json").unlink(missing_ok=True)
    if legacy.exists():
        shutil.rmtree(legacy)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--userdata", help="T3 userdata directory (contains environment-id and statev2.sqlite); preserves the saved directory when omitted")
    parser.add_argument("--uninstall", action="store_true")
    remote_args = parser.add_mutually_exclusive_group()
    remote_args.add_argument("--ssh-host", action="append", help="Also read this computer through an existing SSH connection (repeat for more computers)")
    remote_args.add_argument("--clear-ssh-hosts", action="store_true", help="Remove all saved SSH computers")
    args = parser.parse_args()
    registration, installed, legacy = locations()
    manifest_path = registration / f"{NAME}.json"
    if args.uninstall:
        remove_legacy(registration, legacy)
        manifest_path.unlink(missing_ok=True)
        if installed.exists():
            shutil.rmtree(installed)
        print("Removed the T3Code PR Links local helper. Remove the extension in chrome://extensions separately.")
        return
    key = json.loads((ROOT / "extension/manifest.json").read_text())["key"]
    identity = extension_id(key)
    installed.mkdir(parents=True, exist_ok=True, mode=0o700)
    shutil.copyfile(ROOT / "native/host.py", installed / "host.py")
    config_path = installed / "config.json"
    source = next((path for path in (config_path, legacy / "config.json") if path.exists()), None)
    previous = json.loads(source.read_text()) if source else {}
    remotes = previous.get("sshHosts", [])
    if args.clear_ssh_hosts:
        remotes = []
    if args.ssh_host is not None:
        remotes = []
        for hostname in args.ssh_host:
            if not re.fullmatch(r"[a-zA-Z0-9][a-zA-Z0-9_.@-]*", hostname):
                raise SystemExit(f"Invalid SSH host: {hostname}")
            remotes.append({"host": hostname, "name": hostname})
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
    remove_legacy(registration, legacy)
    print(f"Local helper installed. Extension ID: {identity}")
    data = Path(userdata).expanduser().resolve()
    if not any((data / name).is_file() for name in ("statev2.sqlite", "state.sqlite")):
        print(f"Warning: T3 Code data was not found in {data}. Open T3 Code once, or pass --userdata with the right directory.")
    if remotes:
        print("Remote computers: " + ", ".join(remote["name"] for remote in remotes))
    print("Next, install T3Code PR Links from the Chrome Web Store and reload any open GitHub tabs.")
    print(f"For development, choose Load unpacked in chrome://extensions and select:\n{ROOT / 'extension'}")


if __name__ == "__main__":
    main()
