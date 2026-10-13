#!/usr/bin/env python3
"""Build the Chrome Web Store upload zip from the extension folder."""
import json
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
IGNORED = {".DS_Store"}


def build(root=ROOT, output=None):
    extension = root / "extension"
    manifest = json.loads((extension / "manifest.json").read_text())
    version = json.loads((root / "package.json").read_text())["version"]
    if manifest["version"] != version:
        raise SystemExit(f"manifest.json version {manifest['version']} does not match package.json version {version}.")
    # The store assigns the published ID from its own key; the local key only pins unpacked builds to it.
    manifest.pop("key", None)
    output = output or root / "dist" / f"t3code-pr-links-{version}.zip"
    output.parent.mkdir(parents=True, exist_ok=True)
    files = sorted(path for path in extension.rglob("*") if path.is_file() and path.name not in IGNORED)
    with zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED) as archive:
        for path in files:
            name = path.relative_to(extension).as_posix()
            if name == "manifest.json":
                archive.writestr(name, json.dumps(manifest, indent=2) + "\n")
            else:
                archive.write(path, name)
    return output


def main():
    output = build()
    print(f"Wrote {output.relative_to(ROOT)}. Upload it at https://chrome.google.com/webstore/devconsole")


if __name__ == "__main__":
    main()
