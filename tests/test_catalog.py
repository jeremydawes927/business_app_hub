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

    def test_powershell_string_escapes_apostrophes(self):
        self.assertEqual("'Bob''s Folder'", hub.powershell_string("Bob's Folder"))

    def test_desktop_shortcut_uses_app_name(self):
        shortcut_path = hub.desktop_shortcut_path()
        self.assertEqual("Business App Hub.lnk", shortcut_path.name)

    def test_version_compare_detects_newer_release(self):
        self.assertTrue(hub.is_newer_version("v0.1.3", "0.1.2"))
        self.assertFalse(hub.is_newer_version("0.1.2", "0.1.2"))
        self.assertFalse(hub.is_newer_version("0.1.1", "0.1.2"))

    def test_github_page_url_normalizes_to_releases_api(self):
        self.assertEqual(
            "https://api.github.com/repos/example-user/example-app/releases",
            hub.normalize_github_releases_url(
                "https://github.com/example-user/example-app/releases"
            ),
        )

    def test_latest_api_url_falls_back_to_releases_list_url(self):
        self.assertEqual(
            "https://api.github.com/repos/example-user/example-app/releases",
            hub.release_list_api_url(
                "https://api.github.com/repos/example-user/example-app/releases/latest"
            ),
        )

    def test_publish_new_app_from_exe_writes_catalog_latest_and_zip(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            folder = Path(temp_dir)
            (folder / "catalog.json").write_text(
                json.dumps({"hub_version": "1.0.0", "apps": []}),
                encoding="utf-8",
            )
            package = folder / "Demo Tool.exe"
            package.write_bytes(b"fake executable")

            app_id = hub.publish_app_package(
                folder,
                mode="Create new app",
                existing_app_id="",
                app_name="Demo Tool",
                app_id="",
                description="A test app.",
                version="1.2.3",
                release_name="First release",
                executable_name="",
                package_input=package,
                icon_input=None,
            )

            catalog = hub.load_catalog(folder)
            self.assertEqual("demo-tool", app_id)
            self.assertEqual("Demo Tool", catalog.apps[0].name)
            self.assertEqual("1.2.3", catalog.apps[0].default_version)
            self.assertEqual(("1.2.3",), catalog.apps[0].allowed_versions)
            self.assertEqual("Demo Tool.exe", catalog.apps[0].executable_name)
            release = catalog.apps[0].releases[0]
            self.assertEqual("First release", release.notes)
            zip_path = folder / catalog.apps[0].source_folder / release.package
            self.assertTrue(zip_path.is_file())
            self.assertTrue((folder / catalog.apps[0].source_folder / "latest.json").is_file())

    def test_install_app_release_extracts_executable(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            folder = Path(temp_dir) / "hub"
            install_root = Path(temp_dir) / "installs"
            folder.mkdir()
            (folder / "catalog.json").write_text(
                json.dumps({"hub_version": "1.0.0", "apps": []}),
                encoding="utf-8",
            )
            package = Path(temp_dir) / "Demo Tool.exe"
            package.write_bytes(b"fake executable")
            app_id = hub.publish_app_package(
                folder,
                mode="Create new app",
                existing_app_id="",
                app_name="Demo Tool",
                app_id="",
                description="A test app.",
                version="1.2.3",
                release_name="First release",
                executable_name="",
                package_input=package,
                icon_input=None,
            )
            app = hub.load_catalog(folder).apps[0]

            record = hub.install_app_release(folder, app, install_root=install_root)

            self.assertEqual(app_id, record.app_id)
            self.assertTrue(Path(record.executable_path).is_file())
            self.assertTrue(Path(record.install_folder).is_dir())

    def test_install_app_release_keeps_existing_app_folder(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            folder = Path(temp_dir) / "hub"
            install_root = Path(temp_dir) / "installs"
            folder.mkdir()
            (folder / "catalog.json").write_text(
                json.dumps({"hub_version": "1.0.0", "apps": []}),
                encoding="utf-8",
            )
            legacy_folder = install_root / "demo-tool"
            legacy_folder.mkdir(parents=True)
            legacy_marker = legacy_folder / "old-version.txt"
            legacy_marker.write_text("still running", encoding="utf-8")
            package = Path(temp_dir) / "Demo Tool.exe"
            package.write_bytes(b"fake executable")
            hub.publish_app_package(
                folder,
                mode="Create new app",
                existing_app_id="",
                app_name="Demo Tool",
                app_id="",
                description="A test app.",
                version="1.2.3",
                release_name="First release",
                executable_name="",
                package_input=package,
                icon_input=None,
            )
            app = hub.load_catalog(folder).apps[0]

            record = hub.install_app_release(folder, app, install_root=install_root)

            self.assertTrue(legacy_marker.is_file())
            self.assertNotEqual(legacy_folder.resolve(), Path(record.install_folder).resolve())
            self.assertTrue(Path(record.install_folder).is_dir())

    def test_find_installed_executable_ignores_bundled_helper_exes(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            install_folder = Path(temp_dir) / "demo-tool"
            helper_folder = install_folder / "_internal" / "tools" / "tesseract"
            helper_folder.mkdir(parents=True)
            helper_exe = helper_folder / "tesseract.exe"
            helper_exe.write_bytes(b"helper")
            app_exe = install_folder / "Demo Tool.exe"
            app_exe.write_bytes(b"app")
            app = hub.HubApp(
                app_id="demo-tool",
                name="Demo Tool",
                executable_name="Demo Tool",
            )

            selected = hub.find_installed_executable(install_folder, app)

            self.assertEqual(app_exe.resolve(), selected)


if __name__ == "__main__":
    unittest.main()
