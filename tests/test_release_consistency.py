"""Release metadata consistency checks."""

from __future__ import annotations

import json
from pathlib import Path
import unittest

ROOT = Path(__file__).parents[1]
VERSION = "0.1.0-alpha.11.0"


class ReleaseConsistencyTests(unittest.TestCase):
    def test_manifest_const_and_release_notes_match(self) -> None:
        manifest = json.loads((ROOT / "custom_components/dummy_os_data/manifest.json").read_text())
        const = (ROOT / "custom_components/dummy_os_data/const.py").read_text()
        notes = (ROOT / "RELEASE_NOTES.md").read_text()
        self.assertEqual(manifest["version"], VERSION)
        self.assertIn(f'VERSION = "{VERSION}"', const)
        self.assertIn(f"**Tag:** `{VERSION}`", notes)
        self.assertIn(f"## Dummy OS Data {VERSION}", notes)

    def test_translation_key_sets_match(self) -> None:
        strings = json.loads((ROOT / "custom_components/dummy_os_data/strings.json").read_text())
        english = json.loads((ROOT / "custom_components/dummy_os_data/translations/en.json").read_text())
        dutch = json.loads((ROOT / "custom_components/dummy_os_data/translations/nl.json").read_text())
        expected = set(strings["options"]["step"]["init"]["data"])
        self.assertEqual(expected, set(english["options"]["step"]["init"]["data"]))
        self.assertEqual(expected, set(dutch["options"]["step"]["init"]["data"]))


if __name__ == "__main__":
    unittest.main()
