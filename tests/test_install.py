import importlib.util
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

SPEC = importlib.util.spec_from_file_location("installer", Path(__file__).resolve().parents[1] / "scripts/install.py")
installer = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(installer)


class InstallTests(unittest.TestCase):
    def test_updates_preserve_custom_directory_and_computers(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            installed = root / "installed"
            installed.mkdir()
            saved = {"userdata": str((root / "custom").resolve()), "sshHosts": [{"host": "mini", "name": "My Mini", "userdata": "~/other"}]}
            (installed / "config.json").write_text(json.dumps(saved))
            with patch.object(installer, "locations", return_value=(root / "registration", installed, root / "legacy")), patch.object(installer.sys, "argv", ["install.py"]), patch("builtins.print") as output:
                installer.main()
            self.assertEqual(json.loads((installed / "config.json").read_text()), saved)
            self.assertTrue(any("T3 Code data was not found" in str(call) for call in output.call_args_list))
            (root / "custom").mkdir()
            (root / "custom/statev2.sqlite").touch()
            with patch.object(installer, "locations", return_value=(root / "registration", installed, root / "legacy")), patch.object(installer.sys, "argv", ["install.py"]), patch("builtins.print") as output:
                installer.main()
            self.assertFalse(any("T3 Code data was not found" in str(call) for call in output.call_args_list))
            self.assertEqual((installed / "config.json").stat().st_mode & 0o777, 0o600)
            with patch.object(installer, "locations", return_value=(root / "registration", installed, root / "legacy")), patch.object(installer.sys, "argv", ["install.py", "--clear-ssh-hosts"]), patch("builtins.print"):
                installer.main()
            self.assertEqual(json.loads((installed / "config.json").read_text())["sshHosts"], [])

    def test_install_migrates_and_removes_the_legacy_helper(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            registration, installed, legacy = root / "registration", root / "installed", root / "legacy"
            registration.mkdir()
            legacy.mkdir()
            saved = {"userdata": str((root / "custom").resolve()), "sshHosts": [{"host": "mini", "name": "My Mini", "userdata": "~/other"}]}
            (legacy / "config.json").write_text(json.dumps(saved))
            (registration / f"{installer.LEGACY_NAME}.json").write_text("{}")
            with patch.object(installer, "locations", return_value=(registration, installed, legacy)), patch.object(installer.sys, "argv", ["install.py"]), patch("builtins.print"):
                installer.main()
            self.assertEqual(json.loads((installed / "config.json").read_text()), saved)
            self.assertEqual(json.loads((registration / f"{installer.NAME}.json").read_text())["name"], installer.NAME)
            self.assertFalse((registration / f"{installer.LEGACY_NAME}.json").exists())
            self.assertFalse(legacy.exists())
            legacy.mkdir()
            (registration / f"{installer.LEGACY_NAME}.json").write_text("{}")
            with patch.object(installer, "locations", return_value=(registration, installed, legacy)), patch.object(installer.sys, "argv", ["install.py", "--uninstall"]), patch("builtins.print"):
                installer.main()
            self.assertEqual(list(registration.iterdir()), [])
            self.assertFalse(installed.exists() or legacy.exists())
