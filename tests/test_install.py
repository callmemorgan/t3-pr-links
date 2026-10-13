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
            with patch.object(installer, "locations", return_value=(root / "registration", installed)), patch.object(installer.sys, "argv", ["install.py"]), patch("builtins.print"):
                installer.main()
            self.assertEqual(json.loads((installed / "config.json").read_text()), saved)
            self.assertEqual((installed / "config.json").stat().st_mode & 0o777, 0o600)
            with patch.object(installer, "locations", return_value=(root / "registration", installed)), patch.object(installer.sys, "argv", ["install.py", "--clear-ssh-hosts"]), patch("builtins.print"):
                installer.main()
            self.assertEqual(json.loads((installed / "config.json").read_text())["sshHosts"], [])
