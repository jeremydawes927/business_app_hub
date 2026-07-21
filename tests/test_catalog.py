import json
import tempfile
import unittest
from pathlib import Path

import sys

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

import business_app_hub as hub


class CatalogTests(unittest.TestCase):
    def test_empty_catalog_parses(self):
        catalog = hub.parse_catalog_text(
            json.dumps({"hub_version": "1.0.0", "apps": []})
        )

        self.assertEqual("1.0.0", catalog.hub_version)
        self.assertEqual((), catalog.apps)

    def test_allowed_and_blocked_versions_filter_releases(self):
        catalog = hub.parse_catalog_text(
            json.dumps(
                {
                    "hub_version": "1.0.0",
                    "apps": [
                        {
                            "id": "inventory-helper",
                            "name": "Inventory Helper",
                            "allowed_versions": ["1.0.0", "0.9.8"],
                            "blocked_versions": ["0.9.8"],
                            "releases": [
                                {"version": "1.0.0", "notes": "Stable"},
                                {"version": "0.9.8", "notes": "Beta"},
                                {"version": "0.9.7", "notes": "Blocked by omission"},
                            ],
                        }
                    ],
                }
            )
        )

        releases = catalog.apps[0].published_releases
        self.assertEqual(["1.0.0"], [release.version for release in releases])

    def test_icon_path_parses_from_catalog(self):
        catalog = hub.parse_catalog_text(
            json.dumps(
                {
                    "apps": [
                        {
                            "id": "inventory-helper",
                            "name": "Inventory Helper",
                            "icon": "icon.png",
                        }
                    ]
                }
            )
        )

        self.assertEqual("icon.png", catalog.apps[0].icon_path)

    def test_icon_path_auto_discovers_app_folder_icon(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            folder = Path(temp_dir)
            app_folder = folder / "Apps" / "Inventory Helper"
            app_folder.mkdir(parents=True)
            icon_path = app_folder / "icon.png"
            icon_path.write_bytes(b"not a real png, just a path test")
            app = hub.HubApp(
                app_id="inventory-helper",
                name="Inventory Helper",
                source_folder="Apps/Inventory Helper",
            )

            self.assertEqual(
                icon_path.resolve(),
                hub.resolve_app_icon_path(folder, app),
            )

    def test_update_catalog_app_fields_preserves_catalog(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            folder = Path(temp_dir)
            (folder / "catalog.json").write_text(
                json.dumps(
                    {
                        "hub_version": "1.0.0",
                        "apps": [
                            {
                                "id": "inventory-helper",
                                "name": "Inventory Helper",
                                "description": "Old description",
                                "releases": [{"version": "1.0.0"}],
                            }
                        ],
                    }
                ),
                encoding="utf-8",
            )

            hub.update_catalog_app_fields(
                folder,
                "inventory-helper",
                {"description": "New description"},
            )

            catalog = hub.load_catalog(folder)
            self.assertEqual("New description", catalog.apps[0].description)
            self.assertEqual("1.0.0", catalog.apps[0].releases[0].version)

    def test_hub_folder_requires_catalog_json(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            folder = Path(temp_dir)
            self.assertFalse(hub.is_valid_hub_folder(folder))
            (folder / "catalog.json").write_text('{"apps": []}', encoding="utf-8")
            self.assertTrue(hub.is_valid_hub_folder(folder))


if __name__ == "__main__":
    unittest.main()
