import importlib.util
import json
import tempfile
import zipfile
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("packager", ROOT / "scripts/package.py")
packager = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(packager)


class PackageTests(unittest.TestCase):
    def test_zip_contains_every_extension_file_without_the_key(self):
        with tempfile.TemporaryDirectory() as temporary:
            output = packager.build(output=Path(temporary) / "upload.zip")
            with zipfile.ZipFile(output) as archive:
                names = set(archive.namelist())
                manifest = json.loads(archive.read("manifest.json"))
        expected = {path.relative_to(ROOT / "extension").as_posix() for path in (ROOT / "extension").rglob("*")
                    if path.is_file() and path.name != ".DS_Store"}
        self.assertEqual(names, expected)
        self.assertNotIn("key", manifest)
        self.assertEqual(manifest["version"], json.loads((ROOT / "package.json").read_text())["version"])

    def test_mismatched_versions_stop_the_build(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "extension").mkdir()
            (root / "extension/manifest.json").write_text(json.dumps({"version": "1.0.0"}))
            (root / "package.json").write_text(json.dumps({"version": "1.0.1"}))
            with self.assertRaises(SystemExit):
                packager.build(root)
            self.assertFalse((root / "dist").exists())


if __name__ == "__main__":
    unittest.main()
