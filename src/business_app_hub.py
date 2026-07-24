from __future__ import annotations

import json
import os
import hashlib
import shutil
import subprocess
import sys
import tempfile
import threading
import urllib.error
import urllib.parse
import urllib.request
import webbrowser
import zipfile
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
from tkinter import filedialog, messagebox, ttk
import tkinter as tk

try:
    from PIL import Image, ImageTk
except ImportError:  # Pillow is optional; PNG display still works through Tk.
    Image = None
    ImageTk = None


APP_NAME = "Business App Hub"
APP_VERSION = "0.1.6"
HUB_FOLDER_NAME = "Business App Hub"
FONT_FAMILY = "Georgia"
APP_DATA_FOLDER = Path(os.environ.get("LOCALAPPDATA", Path.home())) / "Business App Hub"
INSTALLS_FOLDER = APP_DATA_FOLDER / "InstalledApps"
SHORTCUT_ICON_FOLDER = APP_DATA_FOLDER / "ShortcutIcons"
SETTINGS_FILE = APP_DATA_FOLDER / "settings.json"
CATALOG_FILE_NAME = "catalog.json"
APPS_FOLDER_NAME = "Apps"
BUNDLED_HEADER_IMAGE_NAME = "hub_header.png"
INSTALL_MARKER_NAME = ".business_app_hub_install_marker.json"
INSTALL_MARKER_TYPE = "business_app_hub_install_marker"
SELF_APP_ID = "business-app-hub"
PROTECTED_UPDATE_FOLDER_NAMES = {
    "",
    "desktop",
    "documents",
    "downloads",
    "music",
    "pictures",
    "videos",
    "users",
    "windows",
    "program files",
    "program files (x86)",
    "system32",
    "syswow64",
    "onedrive",
}
DEFAULT_GITHUB_RELEASES_API_URL = (
    "https://api.github.com/repos/jeremydawes927/business_app_hub/releases/latest"
)
IMAGE_EXTENSIONS = (".png", ".ico", ".gif", ".jpg", ".jpeg", ".ppm", ".pgm")
PUBLISH_ICON_EXTENSIONS = (".png", ".ico")
PUBLISH_UPDATE_IMAGE_EXTENSIONS = (".png", ".ico", ".jpg", ".jpeg", ".gif")
ICON_CANDIDATE_NAMES = (
    "icon.png",
    "icon.ico",
    "app.png",
    "app.ico",
    "logo.png",
    "logo.ico",
    "tile.png",
    "tile.ico",
    "icon.gif",
    "app.gif",
    "logo.gif",
)
HEADER_CANDIDATE_NAMES = (
    "header.png",
    "hub_header.png",
    "portal_header.png",
    "background.png",
    "header.gif",
)

COLORS = {
    "background": "#12131d",
    "chrome_top": "#25213c",
    "chrome_bottom": "#12131d",
    "nav": "#191a28",
    "nav_active": "#68b8ff",
    "nav_light": "#2f6fa8",
    "nav_text": "#d7dcea",
    "panel": "#1d2030",
    "panel_alt": "#252a3d",
    "panel_high": "#30364c",
    "card": "#23283a",
    "card_hover": "#2a3248",
    "card_selected": "#314d72",
    "store_card": "#273044",
    "border": "#3b4258",
    "accent": "#68b8ff",
    "accent_dark": "#2475b8",
    "purple": "#6f5bd8",
    "warning": "#f2c94c",
    "success": "#56d19a",
    "update_green": "#42f59b",
    "text": "#edf2ff",
    "muted": "#9aa7bf",
    "button": "#2f6fa8",
    "button_hover": "#3c8fd6",
    "button_dark": "#252a3d",
    "download_idle": "#151823",
    "download_flash": "#164f91",
    "scrollbar_track": "#151823",
    "scrollbar_thumb": "#347eb8",
    "scrollbar_thumb_hover": "#68b8ff",
}

VERSION_HISTORY = (
    {
        "version": "0.1.6",
        "name": "Safety and Polish Update",
        "date": "2026-07-24",
        "changes": (
            "Added safer update handling with install markers, ZIP path validation, "
            "staged extraction, temp backups, and protected-folder checks.",
            "Added app release update cards with version notes and optional release images.",
            "Improved app pages with cleaner descriptions, app action controls, and shortcut support.",
            "Added this version-history page and one-time update summary popup.",
        ),
    },
    {
        "version": "0.1.5",
        "name": "Release Notes Update",
        "date": "2026-07-23",
        "changes": (
            "Added richer release notes for managed apps.",
            "Improved admin publishing fields for app updates and new app entries.",
        ),
    },
    {
        "version": "0.1.4",
        "name": "Admin Controls Update",
        "date": "2026-07-23",
        "changes": (
            "Added local admin mode controls for publishing tabs.",
            "Improved app update and rollback workflow.",
        ),
    },
    {
        "version": "0.1.3",
        "name": "Shortcut and Hub Settings Update",
        "date": "2026-07-22",
        "changes": (
            "Added Desktop shortcut creation.",
            "Moved hub folder controls into Settings.",
            "Improved the Steam-inspired layout and app cards.",
        ),
    },
)


@dataclass(frozen=True)
class AppRelease:
    version: str
    package: str = ""
    sha256: str = ""
    notes: str = ""
    update_name: str = ""
    update_description: str = ""
    update_image: str = ""
    date: str = ""
    allowed: bool = True


@dataclass(frozen=True)
class HubApp:
    app_id: str
    name: str
    description: str = ""
    source_folder: str = ""
    icon_path: str = ""
    executable_name: str = ""
    default_version: str = ""
    allowed_versions: tuple[str, ...] = ()
    blocked_versions: tuple[str, ...] = ()
    releases: tuple[AppRelease, ...] = ()

    @property
    def published_releases(self) -> tuple[AppRelease, ...]:
        blocked = {version.strip() for version in self.blocked_versions}
        allowed = {version.strip() for version in self.allowed_versions}
        releases: list[AppRelease] = []
        for release in self.releases:
            if release.version in blocked:
                continue
            if allowed and release.version not in allowed:
                continue
            if not release.allowed:
                continue
            releases.append(release)
        return tuple(releases)


@dataclass(frozen=True)
class HubCatalog:
    hub_version: str = "1.0.0"
    apps: tuple[HubApp, ...] = ()


@dataclass(frozen=True)
class InstallRecord:
    app_id: str
    version: str
    install_folder: str
    executable_path: str


@dataclass(frozen=True)
class DownloadTask:
    app: HubApp
    version: str = ""


def normalize_path(path: Path) -> Path:
    try:
        return path.resolve()
    except OSError:
        return path


def app_data_settings() -> dict[str, object]:
    if not SETTINGS_FILE.exists():
        return {}
    try:
        raw = SETTINGS_FILE.read_text(encoding="utf-8-sig")
        data = json.loads(raw)
    except (OSError, json.JSONDecodeError):
        return {}
    return data if isinstance(data, dict) else {}


def save_app_data_settings(settings: dict[str, object]) -> None:
    APP_DATA_FOLDER.mkdir(parents=True, exist_ok=True)
    SETTINGS_FILE.write_text(json.dumps(settings, indent=2), encoding="utf-8")


def version_key(version: str) -> tuple[int, ...]:
    clean = version.strip().lstrip("vV")
    parts: list[int] = []
    current = ""
    for character in clean:
        if character.isdigit():
            current += character
            continue
        if current:
            parts.append(int(current))
            current = ""
        if character not in ".-_ ":
            break
    if current:
        parts.append(int(current))
    return tuple(parts) or (0,)


def is_newer_version(candidate: str, current: str) -> bool:
    candidate_parts = list(version_key(candidate))
    current_parts = list(version_key(current))
    width = max(len(candidate_parts), len(current_parts))
    candidate_parts.extend([0] * (width - len(candidate_parts)))
    current_parts.extend([0] * (width - len(current_parts)))
    return tuple(candidate_parts) > tuple(current_parts)


def load_github_update_settings() -> tuple[bool, str]:
    settings = app_data_settings()
    enabled = bool(settings.get("check_github_updates", True))
    url = str(
        settings.get("github_releases_api_url", DEFAULT_GITHUB_RELEASES_API_URL)
    ).strip()
    return enabled, url or DEFAULT_GITHUB_RELEASES_API_URL


def save_github_update_settings(enabled: bool, url: str) -> None:
    settings = app_data_settings()
    settings["check_github_updates"] = bool(enabled)
    settings["github_releases_api_url"] = url.strip() or DEFAULT_GITHUB_RELEASES_API_URL
    save_app_data_settings(settings)


def load_coder_settings() -> tuple[bool, bool]:
    settings = app_data_settings()
    advanced_open = bool(settings.get("coder_settings_open", False))
    device_admin = bool(settings.get("device_admin", False))
    return advanced_open, device_admin


def save_coder_settings(advanced_open: bool, device_admin: bool) -> None:
    settings = app_data_settings()
    settings["coder_settings_open"] = bool(advanced_open)
    settings["device_admin"] = bool(device_admin)
    save_app_data_settings(settings)


def normalize_github_releases_url(url: str) -> str:
    raw = (url or DEFAULT_GITHUB_RELEASES_API_URL).strip()
    parsed = urllib.parse.urlparse(raw)
    host = parsed.netloc.lower()
    path_parts = [part for part in parsed.path.split("/") if part]
    if host == "github.com" and len(path_parts) >= 2:
        owner, repo = path_parts[0], path_parts[1]
        return f"https://api.github.com/repos/{owner}/{repo}/releases"
    return raw


def release_list_api_url(api_url: str) -> str:
    clean = api_url.rstrip("/")
    if clean.endswith("/latest"):
        return clean[: -len("/latest")]
    marker = "/releases/tags/"
    if marker in clean:
        return clean.split(marker, 1)[0] + "/releases"
    return clean


def release_summary_from_payload(payload: object) -> dict[str, str]:
    if isinstance(payload, list):
        if not payload:
            raise ValueError(
                "GitHub answered, but this repository does not have any published releases yet."
            )
        payload = payload[0]
    if not isinstance(payload, dict):
        raise ValueError("GitHub release response was not a JSON object.")
    tag = str(payload.get("tag_name", "")).strip()
    html_url = str(payload.get("html_url", "")).strip()
    name = str(payload.get("name", "")).strip()
    if not tag:
        raise ValueError("GitHub release response did not include tag_name.")
    asset_url = ""
    asset_name = ""
    expected_name = APP_NAME.lower().replace(" ", "")
    assets = payload.get("assets", [])
    if isinstance(assets, list):
        for raw_asset in assets:
            if not isinstance(raw_asset, dict):
                continue
            candidate_name = str(raw_asset.get("name", "")).strip()
            candidate_url = str(raw_asset.get("browser_download_url", "")).strip()
            if not candidate_name.lower().endswith(".zip") or not candidate_url:
                continue
            if not asset_url:
                asset_name = candidate_name
                asset_url = candidate_url
            normalized_asset = candidate_name.lower().replace(" ", "")
            if expected_name in normalized_asset:
                asset_name = candidate_name
                asset_url = candidate_url
                break
    return {
        "tag": tag,
        "url": html_url,
        "name": name,
        "asset_url": asset_url,
        "asset_name": asset_name,
    }


def read_github_release_payload(api_url: str) -> object:
    request = urllib.request.Request(
        api_url,
        headers={
            "Accept": "application/vnd.github+json",
            "User-Agent": f"{APP_NAME}/{APP_VERSION}",
        },
    )
    with urllib.request.urlopen(request, timeout=8) as response:
        return json.loads(response.read().decode("utf-8"))


def fetch_latest_github_release(api_url: str) -> dict[str, str]:
    normalized_url = normalize_github_releases_url(api_url)
    try:
        return release_summary_from_payload(read_github_release_payload(normalized_url))
    except urllib.error.HTTPError as exc:
        if exc.code != 404 or not normalized_url.rstrip("/").endswith("/latest"):
            raise FileNotFoundError(
                "GitHub could not find that releases endpoint. Check the owner/repo, "
                "whether the repository is public, and the releases URL in Settings."
            ) from exc
    list_url = release_list_api_url(normalized_url)
    try:
        return release_summary_from_payload(read_github_release_payload(list_url))
    except urllib.error.HTTPError as exc:
        if exc.code == 404:
            raise FileNotFoundError(
                "GitHub could not find that repository's releases list. Check the owner/repo, "
                "whether the repository is public, and the releases URL in Settings."
            ) from exc
        raise


def download_url_to_file(url: str, destination: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    request = urllib.request.Request(
        url,
        headers={"User-Agent": f"{APP_NAME}/{APP_VERSION}"},
    )
    with urllib.request.urlopen(request, timeout=60) as response:
        with destination.open("wb") as output:
            shutil.copyfileobj(response, output)


def load_saved_hub_folder() -> Path | None:
    folder = str(app_data_settings().get("hub_folder", "")).strip()
    if not folder:
        return None
    path = Path(folder)
    return path if is_valid_hub_folder(path) else None


def save_hub_folder(folder: Path) -> None:
    settings = app_data_settings()
    settings["hub_folder"] = str(normalize_path(folder))
    save_app_data_settings(settings)


def load_installed_app_ids() -> set[str]:
    installed = app_data_settings().get("installed_apps", [])
    app_ids = set()
    if isinstance(installed, list):
        app_ids.update(str(app_id).strip() for app_id in installed if str(app_id).strip())
    app_ids.update(load_install_records().keys())
    return app_ids


def save_installed_app_ids(app_ids: set[str]) -> None:
    settings = app_data_settings()
    settings["installed_apps"] = sorted(app_ids)
    save_app_data_settings(settings)


def load_install_records() -> dict[str, InstallRecord]:
    records = app_data_settings().get("installed_app_records", {})
    if not isinstance(records, dict):
        return {}
    parsed: dict[str, InstallRecord] = {}
    for app_id, raw in records.items():
        if not isinstance(raw, dict):
            continue
        clean_app_id = str(app_id).strip()
        version = str(raw.get("version", "")).strip()
        install_folder = str(raw.get("install_folder", "")).strip()
        executable_path = str(raw.get("executable_path", "")).strip()
        if not clean_app_id or not version or not install_folder or not executable_path:
            continue
        parsed[clean_app_id] = InstallRecord(
            app_id=clean_app_id,
            version=version,
            install_folder=install_folder,
            executable_path=executable_path,
        )
    return parsed


def save_install_record(record: InstallRecord) -> None:
    settings = app_data_settings()
    records = settings.get("installed_app_records", {})
    if not isinstance(records, dict):
        records = {}
    records[record.app_id] = {
        "version": record.version,
        "install_folder": record.install_folder,
        "executable_path": record.executable_path,
    }
    installed = settings.get("installed_apps", [])
    installed_ids = (
        set(str(app_id).strip() for app_id in installed if str(app_id).strip())
        if isinstance(installed, list)
        else set()
    )
    installed_ids.add(record.app_id)
    settings["installed_apps"] = sorted(installed_ids)
    settings["installed_app_records"] = records
    save_app_data_settings(settings)


def delete_install_record(app_id: str) -> None:
    settings = app_data_settings()
    records = settings.get("installed_app_records", {})
    if isinstance(records, dict):
        records.pop(app_id, None)
    installed = settings.get("installed_apps", [])
    if isinstance(installed, list):
        settings["installed_apps"] = [
            item for item in installed if str(item).strip() != app_id
        ]
    settings["installed_app_records"] = records if isinstance(records, dict) else {}
    save_app_data_settings(settings)


def likely_onedrive_roots() -> list[Path]:
    home = Path.home()
    roots = [
        home / "OneDrive",
    ]
    roots.extend(sorted(home.glob("OneDrive*")))
    unique: list[Path] = []
    seen: set[str] = set()
    for root in roots:
        key = str(root).lower()
        if key not in seen and root.exists():
            unique.append(root)
            seen.add(key)
    return unique


def candidate_hub_folders() -> list[Path]:
    home = Path.home()
    candidates = [
        home / HUB_FOLDER_NAME,
        home / "Documents" / HUB_FOLDER_NAME,
        home / "Desktop" / HUB_FOLDER_NAME,
    ]
    for root in likely_onedrive_roots():
        candidates.append(root / HUB_FOLDER_NAME)
        candidates.append(root / "Projects" / HUB_FOLDER_NAME)
        candidates.append(root / "Shared Documents" / HUB_FOLDER_NAME)
        candidates.append(root / "USA-Engineering - General" / "Projects" / HUB_FOLDER_NAME)
        candidates.append(root / "USA-Engineering - General" / "Projects" / "Apps" / HUB_FOLDER_NAME)

    unique: list[Path] = []
    seen: set[str] = set()
    for candidate in candidates:
        key = str(candidate).lower()
        if key not in seen:
            unique.append(candidate)
            seen.add(key)
    return unique


def is_valid_hub_folder(folder: Path) -> bool:
    return folder.is_dir() and (folder / CATALOG_FILE_NAME).is_file()


def find_hub_folder() -> Path | None:
    saved = load_saved_hub_folder()
    if saved:
        return saved
    for candidate in candidate_hub_folders():
        if is_valid_hub_folder(candidate):
            return candidate
    return None


def string_tuple(value: object) -> tuple[str, ...]:
    if not isinstance(value, list):
        return ()
    return tuple(str(item).strip() for item in value if str(item).strip())


def parse_release(raw: object) -> AppRelease | None:
    if not isinstance(raw, dict):
        return None
    version = str(raw.get("version", "")).strip()
    if not version:
        return None
    package = str(raw.get("zip", raw.get("package", ""))).strip()
    return AppRelease(
        version=version,
        package=package,
        sha256=str(raw.get("sha256", "")).strip(),
        notes=str(raw.get("notes", "")).strip(),
        update_name=str(raw.get("update_name", "")).strip(),
        update_description=str(raw.get("update_description", "")).strip(),
        update_image=str(raw.get("update_image", raw.get("image", ""))).strip(),
        date=str(raw.get("date", "")).strip(),
        allowed=bool(raw.get("allowed", True)),
    )


def parse_app(raw: object) -> HubApp | None:
    if not isinstance(raw, dict):
        return None
    app_id = str(raw.get("id", "")).strip()
    name = str(raw.get("name", "")).strip()
    if not app_id or not name:
        return None
    releases = tuple(
        release
        for item in raw.get("releases", [])
        if (release := parse_release(item)) is not None
    )
    return HubApp(
        app_id=app_id,
        name=name,
        description=str(raw.get("description", "")).strip(),
        source_folder=str(raw.get("source_folder", "")).strip(),
        icon_path=str(raw.get("icon", raw.get("icon_path", raw.get("logo", "")))).strip(),
        executable_name=str(raw.get("executable_name", "")).strip(),
        default_version=str(raw.get("default_version", "")).strip(),
        allowed_versions=string_tuple(raw.get("allowed_versions", [])),
        blocked_versions=string_tuple(raw.get("blocked_versions", [])),
        releases=releases,
    )


def parse_catalog_text(text: str) -> HubCatalog:
    raw = json.loads(text)
    if not isinstance(raw, dict):
        raise ValueError("catalog.json must contain a JSON object.")
    apps = tuple(
        app
        for item in raw.get("apps", [])
        if (app := parse_app(item)) is not None
    )
    return HubCatalog(
        hub_version=str(raw.get("hub_version", "1.0.0")).strip() or "1.0.0",
        apps=apps,
    )


def load_catalog(folder: Path) -> HubCatalog:
    catalog_path = folder / CATALOG_FILE_NAME
    if not catalog_path.exists():
        raise FileNotFoundError(f"{CATALOG_FILE_NAME} was not found in {folder}")
    return parse_catalog_text(catalog_path.read_text(encoding="utf-8-sig"))


def load_catalog_json(folder: Path) -> dict[str, object]:
    catalog_path = folder / CATALOG_FILE_NAME
    raw = json.loads(catalog_path.read_text(encoding="utf-8-sig"))
    if not isinstance(raw, dict):
        raise ValueError("catalog.json must contain a JSON object.")
    return raw


def save_catalog_json(folder: Path, data: dict[str, object]) -> None:
    catalog_path = folder / CATALOG_FILE_NAME
    catalog_path.write_text(json.dumps(data, indent=2), encoding="utf-8")


def update_catalog_app_fields(
    folder: Path, app_id: str, fields: dict[str, object]
) -> None:
    data = load_catalog_json(folder)
    apps = data.get("apps", [])
    if not isinstance(apps, list):
        raise ValueError("catalog.json apps field must be a list.")
    for app in apps:
        if not isinstance(app, dict):
            continue
        if str(app.get("id", "")).strip() == app_id:
            app.update(fields)
            save_catalog_json(folder, data)
            return
    raise ValueError(f"App {app_id!r} was not found in catalog.json.")


def resolve_app_source_folder(hub_folder: Path, app: HubApp) -> Path | None:
    if not app.source_folder:
        return None
    source = Path(app.source_folder)
    if not source.is_absolute():
        source = hub_folder / source
    return normalize_path(source)


def safe_app_folder_name(app_id: str) -> str:
    safe = "".join(
        character if character.isalnum() or character in "._-" else "_"
        for character in app_id
    )
    return safe.strip("._-") or "app"


def safe_shortcut_name(name: str) -> str:
    invalid = '<>:"/\\|?*'
    safe = "".join("_" if character in invalid else character for character in name)
    return safe.strip().rstrip(".") or "App"


def slugify_app_id(name: str) -> str:
    slug = []
    previous_dash = False
    for character in name.strip().lower():
        if character.isalnum():
            slug.append(character)
            previous_dash = False
        elif not previous_dash:
            slug.append("-")
            previous_dash = True
    return "".join(slug).strip("-") or "app"


def app_install_folder(app_id: str, install_root: Path = INSTALLS_FOLDER) -> Path:
    return normalize_path(install_root / safe_app_folder_name(app_id))


def safe_version_folder_name(version: str) -> str:
    safe = "".join(
        character if character.isalnum() or character in "._-" else "_"
        for character in version.strip()
    )
    return safe.strip("._-") or "version"


def app_version_install_folder(
    app_id: str,
    version: str,
    install_root: Path = INSTALLS_FOLDER,
) -> Path:
    return normalize_path(app_install_folder(app_id, install_root) / safe_version_folder_name(version))


def next_available_version_install_folder(
    app_id: str,
    version: str,
    install_root: Path = INSTALLS_FOLDER,
) -> Path:
    base_folder = app_install_folder(app_id, install_root)
    version_name = safe_version_folder_name(version)
    candidate = base_folder / version_name
    if not candidate.exists():
        return normalize_path(candidate)
    for index in range(2, 1000):
        candidate = base_folder / f"{version_name}-{index}"
        if not candidate.exists():
            return normalize_path(candidate)
    return normalize_path(base_folder / f"{version_name}-{os.getpid()}")


def is_path_inside(path: Path, parent: Path) -> bool:
    try:
        normalize_path(path).relative_to(normalize_path(parent))
        return True
    except ValueError:
        return False


def install_marker_path(folder: Path) -> Path:
    return normalize_path(folder) / INSTALL_MARKER_NAME


def read_install_marker(folder: Path) -> dict[str, object] | None:
    marker = install_marker_path(folder)
    if not marker.is_file():
        return None
    try:
        data = json.loads(marker.read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError):
        return None
    if not isinstance(data, dict):
        return None
    if data.get("marker_type") != INSTALL_MARKER_TYPE:
        return None
    return data


def write_install_marker(
    folder: Path,
    *,
    app_id: str,
    install_kind: str,
    exe_name: str,
    version: str,
) -> Path:
    marker = install_marker_path(folder)
    existing = read_install_marker(folder) or {}
    now = datetime.now().isoformat(timespec="seconds")
    payload = {
        "marker_type": INSTALL_MARKER_TYPE,
        "app_id": app_id,
        "install_kind": install_kind,
        "exe_name": exe_name,
        "version": version,
        "created_at": str(existing.get("created_at") or now),
        "updated_at": now,
    }
    marker.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return marker


def is_protected_update_target(folder: Path) -> bool:
    target = normalize_path(folder)
    if target == normalize_path(Path(target.anchor)):
        return True
    try:
        if target == normalize_path(Path.home()):
            return True
    except OSError:
        pass
    return target.name.strip().lower() in PROTECTED_UPDATE_FOLDER_NAMES


def validate_zip_member_paths(zip_path: Path) -> None:
    with zipfile.ZipFile(zip_path) as zip_file:
        for info in zip_file.infolist():
            raw_name = info.filename.strip()
            normalized_name = raw_name.replace("\\", "/")
            parts = [part for part in normalized_name.split("/") if part]
            if (
                not raw_name
                or normalized_name.startswith("/")
                or (len(normalized_name) >= 2 and normalized_name[1] == ":")
                or any(part == ".." for part in parts)
            ):
                raise ValueError(
                    f"Refusing to extract unsafe ZIP entry: {info.filename!r}"
                )


def safe_extract_zip(zip_path: Path, destination: Path) -> None:
    validate_zip_member_paths(zip_path)
    with zipfile.ZipFile(zip_path) as zip_file:
        zip_file.extractall(destination)


def ensure_self_update_marker(target_folder: Path, exe_name: str) -> None:
    target = normalize_path(target_folder)
    if is_protected_update_target(target):
        raise ValueError(
            f"Refusing to self-update from a broad folder:\n\n{target}\n\n"
            "Move Business App Hub into its own extracted folder, then create/use a shortcut."
        )
    if not (target / exe_name).is_file():
        raise FileNotFoundError(
            f"Could not confirm the running hub executable:\n\n{target / exe_name}"
        )
    if not (target / "_internal").is_dir():
        raise FileNotFoundError(
            f"Could not confirm the packaged _internal folder:\n\n{target / '_internal'}"
        )
    marker = read_install_marker(target)
    if marker is not None and str(marker.get("app_id", "")) != SELF_APP_ID:
        raise ValueError(
            f"Install marker in this folder belongs to another app:\n\n{target}"
        )
    write_install_marker(
        target,
        app_id=SELF_APP_ID,
        install_kind="self",
        exe_name=exe_name,
        version=APP_VERSION,
    )


def sorted_app_releases(app: HubApp) -> tuple[AppRelease, ...]:
    return tuple(
        sorted(
            app.published_releases,
            key=lambda release: version_key(release.version),
            reverse=True,
        )
    )


def app_release_versions(app: HubApp) -> tuple[str, ...]:
    return tuple(release.version for release in sorted_app_releases(app))


def latest_app_version(app: HubApp) -> str:
    versions = list(app_release_versions(app))
    if versions:
        return max(versions, key=version_key)
    return app.default_version


def app_update_available_for_record(app: HubApp, record: InstallRecord | None) -> bool:
    if record is None or not Path(record.executable_path).is_file():
        return False
    latest = latest_app_version(app)
    return bool(latest and is_newer_version(latest, record.version))


def catalog_app_by_id(catalog: HubCatalog, app_id: str) -> HubApp | None:
    for app in catalog.apps:
        if app.app_id == app_id:
            return app
    return None


def select_release(app: HubApp, version: str = "") -> AppRelease | None:
    releases = app.published_releases
    if not releases:
        return None
    requested = version.strip()
    if requested:
        for release in releases:
            if release.version == requested:
                return release
        return None
    if app.default_version:
        for release in releases:
            if release.version == app.default_version:
                return release
    return sorted_app_releases(app)[0]


def resolve_release_package_path(
    hub_folder: Path,
    app: HubApp,
    release: AppRelease,
) -> Path | None:
    package = release.package.strip()
    source = resolve_app_source_folder(hub_folder, app)
    candidates: list[Path] = []
    if package:
        package_path = Path(package)
        if package_path.is_absolute():
            candidates.append(package_path)
        else:
            candidates.append(hub_folder / package_path)
            if source is not None:
                candidates.append(source / package_path)
                candidates.append(source / "Releases" / package_path)
    if source is not None:
        candidates.extend(
            [
                source / "Releases" / f"{app.name} {release.version}.zip",
                source / "Releases" / f"{safe_app_folder_name(app.name)} {release.version}.zip",
            ]
        )
    for candidate in candidates:
        if candidate.is_file():
            return normalize_path(candidate)
    return None


def hash_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as file:
        for chunk in iter(lambda: file.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest().upper()


def validate_release_hash(package_path: Path, release: AppRelease) -> None:
    expected = release.sha256.strip().upper()
    if not expected:
        return
    actual = hash_file(package_path)
    if actual != expected:
        raise ValueError(
            "Release ZIP hash did not match the catalog. "
            f"Expected {expected}, got {actual}."
        )


def find_installed_executable(install_folder: Path, app: HubApp) -> Path | None:
    if app.executable_name:
        configured = Path(app.executable_name)
        configured_names = {configured.name}
        if configured.suffix.lower() != ".exe":
            configured_names.add(f"{configured.name}.exe")
        if configured.is_absolute() and configured.is_file():
            return normalize_path(configured)
        for name in configured_names:
            direct = install_folder / name
            if direct.is_file():
                return normalize_path(direct)
        for candidate in install_folder.rglob("*.exe"):
            if candidate.name in configured_names and not is_helper_executable(candidate, install_folder):
                return normalize_path(candidate)
    executables = sorted(
        (candidate for candidate in install_folder.rglob("*.exe") if not is_helper_executable(candidate, install_folder)),
        key=lambda candidate: (len(candidate.relative_to(install_folder).parts), candidate.name.lower()),
    )
    return normalize_path(executables[0]) if executables else None


def is_helper_executable(executable: Path, install_folder: Path) -> bool:
    name = executable.name.lower()
    if name in {"tesseract.exe", "python.exe", "pythonw.exe"}:
        return True
    try:
        parts = [part.lower() for part in executable.relative_to(install_folder).parts]
    except ValueError:
        return False
    helper_parts = {"_internal", "tools", "tesseract"}
    return bool(helper_parts.intersection(parts[:-1]))


def install_app_release(
    hub_folder: Path,
    app: HubApp,
    version: str = "",
    install_root: Path = INSTALLS_FOLDER,
) -> InstallRecord:
    release = select_release(app, version)
    if release is None:
        detail = f" version {version}" if version else ""
        raise ValueError(f"{app.name} does not have an allowed release{detail} to install.")
    package_path = resolve_release_package_path(hub_folder, app, release)
    if package_path is None:
        raise FileNotFoundError(
            f"Could not find the release ZIP for {app.name} {release.version}."
        )
    validate_release_hash(package_path, release)
    install_base = app_install_folder(app.app_id, install_root)
    install_folder = next_available_version_install_folder(
        app.app_id,
        release.version,
        install_root,
    )
    if not is_path_inside(install_base, install_root) or not is_path_inside(
        install_folder,
        install_root,
    ):
        raise ValueError("Refusing to install outside the hub install folder.")
    if is_protected_update_target(install_root) or is_protected_update_target(install_base):
        raise ValueError("Refusing to install into a broad system/user folder.")
    install_base.mkdir(parents=True, exist_ok=True)
    write_install_marker(
        install_base,
        app_id=app.app_id,
        install_kind="managed-app-root",
        exe_name=app.executable_name or "",
        version=release.version,
    )
    staging_root = install_base / ".staging"
    staging_root.mkdir(parents=True, exist_ok=True)
    stage_folder = normalize_path(
        Path(
            tempfile.mkdtemp(
                prefix=f"{safe_version_folder_name(release.version)}_",
                dir=staging_root,
            )
        )
    )
    try:
        safe_extract_zip(package_path, stage_folder)
        executable = find_installed_executable(stage_folder, app)
        if executable is None:
            raise FileNotFoundError(
                f"{app.name} installed, but no launchable .exe was found."
            )
        if install_folder.exists():
            install_folder = next_available_version_install_folder(
                app.app_id,
                release.version,
                install_root,
            )
        shutil.move(str(stage_folder), str(install_folder))
    except Exception:
        shutil.rmtree(stage_folder, ignore_errors=True)
        shutil.rmtree(install_folder, ignore_errors=True)
        raise
    executable = find_installed_executable(install_folder, app)
    if executable is None:
        shutil.rmtree(install_folder, ignore_errors=True)
        raise FileNotFoundError(
            f"{app.name} installed, but no launchable .exe was found."
        )
    write_install_marker(
        install_folder,
        app_id=app.app_id,
        install_kind="managed-app-version",
        exe_name=executable.name,
        version=release.version,
    )
    return InstallRecord(
        app_id=app.app_id,
        version=release.version,
        install_folder=str(install_folder),
        executable_path=str(executable),
    )


def delete_app_install(app: HubApp, install_root: Path = INSTALLS_FOLDER) -> None:
    records = load_install_records()
    record = records.get(app.app_id)
    root = normalize_path(install_root)
    app_folder = app_install_folder(app.app_id, install_root)
    targets = [app_folder]
    if record is not None:
        record_folder = normalize_path(Path(record.install_folder))
        if record_folder != app_folder and not is_path_inside(record_folder, app_folder):
            targets.append(record_folder)
    for install_folder in targets:
        if not install_folder.exists():
            continue
        if not is_path_inside(install_folder, root):
            raise ValueError("Refusing to delete outside the hub install folder.")
        marker = read_install_marker(install_folder)
        if marker is not None and str(marker.get("app_id", "")) != app.app_id:
            raise ValueError(
                f"Refusing to delete an install folder marked for another app:\n\n{install_folder}"
            )
        if install_folder != app_folder and marker is None:
            raise ValueError(
                f"Refusing to delete an unexpected install folder without a marker:\n\n{install_folder}"
            )
        shutil.rmtree(install_folder)
    shortcut = app_desktop_shortcut_path(app)
    if shortcut.exists():
        shortcut.unlink()
    delete_install_record(app.app_id)


def launch_install_record(record: InstallRecord) -> subprocess.Popen:
    executable = Path(record.executable_path)
    if not executable.is_file():
        raise FileNotFoundError(f"Installed executable was not found:\n\n{executable}")
    return subprocess.Popen([str(executable)], cwd=str(executable.parent))


def first_executable_in_zip(zip_path: Path) -> str:
    try:
        with zipfile.ZipFile(zip_path) as zip_file:
            executable_names = [
                name
                for name in zip_file.namelist()
                if name.lower().endswith(".exe") and not name.endswith("/")
            ]
    except zipfile.BadZipFile:
        return ""
    if not executable_names:
        return ""
    executable_names.sort(key=lambda value: (value.count("/"), len(value), value.lower()))
    return executable_names[0].replace("/", "\\")


def zip_folder_contents(source_folder: Path, destination_zip: Path) -> None:
    with zipfile.ZipFile(destination_zip, "w", compression=zipfile.ZIP_DEFLATED) as zip_file:
        for file_path in sorted(source_folder.rglob("*")):
            if file_path.is_file():
                zip_file.write(file_path, file_path.relative_to(source_folder))


def prepare_release_zip(input_path: Path, destination_zip: Path) -> None:
    destination_zip.parent.mkdir(parents=True, exist_ok=True)
    if input_path.is_dir():
        zip_folder_contents(input_path, destination_zip)
        return
    if not input_path.is_file():
        raise FileNotFoundError(f"Release package was not found:\n\n{input_path}")
    if input_path.suffix.lower() == ".zip":
        if normalize_path(input_path) != normalize_path(destination_zip):
            shutil.copy2(input_path, destination_zip)
        return
    if input_path.suffix.lower() == ".exe":
        with zipfile.ZipFile(destination_zip, "w", compression=zipfile.ZIP_DEFLATED) as zip_file:
            zip_file.write(input_path, input_path.name)
        return
    raise ValueError("Choose a .zip, .exe, or folder to publish.")


def validate_publish_icon(icon_input: Path) -> None:
    if not icon_input.is_file():
        raise FileNotFoundError(f"Icon file was not found:\n\n{icon_input}")
    if icon_input.suffix.lower() not in PUBLISH_ICON_EXTENSIONS:
        raise ValueError("Choose a .png or .ico file for the app icon.")


def validate_publish_update_image(image_input: Path) -> None:
    if not image_input.is_file():
        raise FileNotFoundError(f"Update image file was not found:\n\n{image_input}")
    if image_input.suffix.lower() not in PUBLISH_UPDATE_IMAGE_EXTENSIONS:
        raise ValueError("Choose a .png, .jpg, .jpeg, .gif, or .ico file for the update image.")


def copy_app_icon_to_source(
    hub_folder: Path,
    app_data: dict[str, object],
    source_folder: str,
    icon_input: Path,
) -> str:
    validate_publish_icon(icon_input)
    source = hub_folder / source_folder
    source.mkdir(parents=True, exist_ok=True)
    icon_destination = source / icon_input.name
    if normalize_path(icon_input) != normalize_path(icon_destination):
        shutil.copy2(icon_input, icon_destination)
    app_data["icon"] = icon_destination.name
    return icon_destination.name


def copy_release_image_to_source(
    hub_folder: Path,
    source_folder: str,
    version: str,
    image_input: Path,
) -> str:
    validate_publish_update_image(image_input)
    source = hub_folder / source_folder
    updates_folder = source / "UpdateImages"
    updates_folder.mkdir(parents=True, exist_ok=True)
    image_name = f"{safe_version_folder_name(version)}{image_input.suffix.lower()}"
    destination = updates_folder / image_name
    if normalize_path(image_input) != normalize_path(destination):
        shutil.copy2(image_input, destination)
    return f"UpdateImages/{image_name}"


def find_catalog_app_data(data: dict[str, object], app_id: str) -> dict[str, object] | None:
    apps = data.get("apps", [])
    if not isinstance(apps, list):
        return None
    for item in apps:
        if isinstance(item, dict) and str(item.get("id", "")).strip() == app_id:
            return item
    return None


def ensure_catalog_apps_list(data: dict[str, object]) -> list[object]:
    apps = data.get("apps", [])
    if not isinstance(apps, list):
        apps = []
        data["apps"] = apps
    return apps


def update_app_icon_only(hub_folder: Path, app_id: str, icon_input: Path) -> str:
    clean_app_id = app_id.strip()
    if not clean_app_id:
        raise ValueError("Choose an existing app before changing its icon.")
    data = load_catalog_json(hub_folder)
    app_data = find_catalog_app_data(data, clean_app_id)
    if app_data is None:
        raise ValueError("Choose an existing app before changing its icon.")
    clean_name = str(app_data.get("name", clean_app_id)).strip() or clean_app_id
    source_folder = str(
        app_data.get("source_folder", f"{APPS_FOLDER_NAME}/{safe_app_folder_name(clean_name)}")
    ).strip()
    if not source_folder:
        source_folder = f"{APPS_FOLDER_NAME}/{safe_app_folder_name(clean_name)}"
        app_data["source_folder"] = source_folder
    copy_app_icon_to_source(hub_folder, app_data, source_folder, icon_input)
    save_catalog_json(hub_folder, data)
    return clean_app_id


def publish_app_package(
    hub_folder: Path,
    *,
    mode: str,
    existing_app_id: str,
    app_name: str,
    app_id: str,
    description: str,
    version: str,
    release_name: str,
    executable_name: str,
    package_input: Path,
    icon_input: Path | None,
    release_description: str = "",
    release_image_input: Path | None = None,
) -> str:
    clean_version = version.strip()
    if not clean_version:
        raise ValueError("Version is required.")
    clean_release_name = release_name.strip() or f"Release {clean_version}"
    data = load_catalog_json(hub_folder)
    apps = ensure_catalog_apps_list(data)
    creating = mode.lower().startswith("create")
    if creating:
        clean_name = app_name.strip()
        clean_app_id = slugify_app_id(app_id or clean_name)
        if not clean_name:
            raise ValueError("New app name is required.")
        if find_catalog_app_data(data, clean_app_id) is not None:
            raise ValueError(f"App ID {clean_app_id!r} already exists.")
        source_folder = f"{APPS_FOLDER_NAME}/{safe_app_folder_name(clean_name)}"
        app_data: dict[str, object] = {
            "id": clean_app_id,
            "name": clean_name,
            "description": description.strip(),
            "source_folder": source_folder,
            "executable_name": executable_name.strip(),
            "default_version": clean_version,
            "allowed_versions": [clean_version],
            "releases": [],
        }
        apps.append(app_data)
    else:
        clean_app_id = existing_app_id.strip()
        app_data = find_catalog_app_data(data, clean_app_id)
        if app_data is None:
            raise ValueError("Choose an existing app to update.")
        clean_name = str(app_data.get("name", clean_app_id)).strip() or clean_app_id
        source_folder = str(
            app_data.get("source_folder", f"{APPS_FOLDER_NAME}/{safe_app_folder_name(clean_name)}")
        ).strip()
        if description.strip():
            app_data["description"] = description.strip()
        if executable_name.strip():
            app_data["executable_name"] = executable_name.strip()

    source = hub_folder / source_folder
    releases_folder = source / "Releases"
    releases_folder.mkdir(parents=True, exist_ok=True)
    zip_name = f"{safe_app_folder_name(clean_name)} {clean_version}.zip"
    destination_zip = releases_folder / zip_name
    prepare_release_zip(package_input, destination_zip)
    if not app_data.get("executable_name"):
        guessed_executable = (
            package_input.name
            if package_input.is_file() and package_input.suffix.lower() == ".exe"
            else first_executable_in_zip(destination_zip)
        )
        if guessed_executable:
            app_data["executable_name"] = guessed_executable

    if icon_input is not None:
        copy_app_icon_to_source(hub_folder, app_data, source_folder, icon_input)
    update_image_rel = ""
    if release_image_input is not None:
        update_image_rel = copy_release_image_to_source(
            hub_folder,
            source_folder,
            clean_version,
            release_image_input,
        )

    package_rel = f"Releases/{zip_name}"
    zip_hash = hash_file(destination_zip)
    releases = app_data.get("releases", [])
    if not isinstance(releases, list):
        releases = []
        app_data["releases"] = releases
    release_data = {
        "version": clean_version,
        "zip": package_rel,
        "sha256": zip_hash,
        "notes": clean_release_name,
        "update_name": clean_release_name,
        "update_description": release_description.strip(),
        "date": date.today().isoformat(),
        "allowed": True,
    }
    if update_image_rel:
        release_data["update_image"] = update_image_rel
    replaced = False
    for index, raw_release in enumerate(releases):
        if isinstance(raw_release, dict) and str(raw_release.get("version", "")).strip() == clean_version:
            releases[index] = release_data
            replaced = True
            break
    if not replaced:
        releases.append(release_data)
    allowed_versions = app_data.get("allowed_versions", [])
    if not isinstance(allowed_versions, list):
        allowed_versions = []
    allowed_clean = [str(item).strip() for item in allowed_versions if str(item).strip()]
    if clean_version not in allowed_clean:
        allowed_clean.append(clean_version)
    app_data["allowed_versions"] = allowed_clean
    app_data["default_version"] = clean_version
    if not str(app_data.get("source_folder", "")).strip():
        app_data["source_folder"] = source_folder

    save_catalog_json(hub_folder, data)
    latest_data = {
        "version": clean_version,
        "name": clean_release_name,
        "package": package_rel,
        "sha256": zip_hash,
        "notes": release_description.strip(),
    }
    if update_image_rel:
        latest_data["update_image"] = update_image_rel
    (source / "latest.json").write_text(json.dumps(latest_data, indent=2), encoding="utf-8")
    return str(clean_app_id)


def resolve_app_icon_path(hub_folder: Path, app: HubApp) -> Path | None:
    source = resolve_app_source_folder(hub_folder, app)
    configured = app.icon_path.strip()
    if configured:
        configured_path = Path(configured)
        candidates = [configured_path] if configured_path.is_absolute() else []
        if not configured_path.is_absolute():
            candidates.extend(
                [
                    hub_folder / configured_path,
                    source / configured_path if source is not None else hub_folder / configured_path,
                ]
            )
        for candidate in candidates:
            if candidate.is_file():
                return normalize_path(candidate)

    if source is None or not source.is_dir():
        return None

    icon_folders = [source, source / "assets", source / "Assets", source / "icons", source / "Icons"]
    for folder in icon_folders:
        if not folder.is_dir():
            continue
        for name in ICON_CANDIDATE_NAMES:
            candidate = folder / name
            if candidate.is_file():
                return normalize_path(candidate)

    for folder in icon_folders:
        if not folder.is_dir():
            continue
        for candidate in sorted(folder.iterdir()):
            if candidate.is_file() and candidate.suffix.lower() in IMAGE_EXTENSIONS:
                return normalize_path(candidate)
    return None


def resolve_release_update_image_path(
    hub_folder: Path,
    app: HubApp,
    release: AppRelease,
) -> Path | None:
    configured = release.update_image.strip()
    if not configured:
        return None
    configured_path = Path(configured)
    source = resolve_app_source_folder(hub_folder, app)
    candidates = [configured_path] if configured_path.is_absolute() else []
    if not configured_path.is_absolute():
        candidates.append(hub_folder / configured_path)
        if source is not None:
            candidates.append(source / configured_path)
            candidates.append(source / "UpdateImages" / configured_path)
    for candidate in candidates:
        if candidate.is_file() and candidate.suffix.lower() in IMAGE_EXTENSIONS:
            return normalize_path(candidate)
    return None


def load_icon_photo_image(path: Path, max_size: int) -> tk.PhotoImage | None:
    if Image is not None and ImageTk is not None:
        try:
            with Image.open(path) as pil_image:
                pil_image.load()
                working = pil_image.convert("RGBA")
                resample = getattr(getattr(Image, "Resampling", Image), "LANCZOS")
                working.thumbnail((max_size, max_size), resample)
                return ImageTk.PhotoImage(working)
        except Exception:
            pass

    try:
        image = tk.PhotoImage(file=str(path))
    except tk.TclError:
        return None
    max_dimension = max(image.width(), image.height())
    if max_dimension > max_size:
        scale = max(1, (max_dimension + max_size - 1) // max_size)
        image = image.subsample(scale, scale)
    return image


def resolve_app_shortcut_icon_path(hub_folder: Path, app: HubApp) -> Path | None:
    icon_path = resolve_app_icon_path(hub_folder, app)
    if icon_path is None or not icon_path.exists():
        return None
    if icon_path.suffix.lower() == ".ico":
        return icon_path
    if Image is None:
        return None

    try:
        with Image.open(icon_path) as pil_image:
            pil_image.load()
            working = pil_image.convert("RGBA")
            resample = getattr(getattr(Image, "Resampling", Image), "LANCZOS")
            working.thumbnail((256, 256), resample)
            canvas = Image.new("RGBA", (256, 256), (0, 0, 0, 0))
            left = (256 - working.width) // 2
            top = (256 - working.height) // 2
            canvas.alpha_composite(working, (left, top))

            SHORTCUT_ICON_FOLDER.mkdir(parents=True, exist_ok=True)
            cache_path = SHORTCUT_ICON_FOLDER / f"{safe_app_folder_name(app.app_id)}.ico"
            canvas.save(cache_path, format="ICO", sizes=[(256, 256), (64, 64), (48, 48), (32, 32), (16, 16)])
            return normalize_path(cache_path)
    except Exception:
        return None


def resolve_hub_header_texture_path(hub_folder: Path) -> Path | None:
    for name in HEADER_CANDIDATE_NAMES:
        candidate = hub_folder / name
        if candidate.is_file():
            return normalize_path(candidate)
    assets_folder = hub_folder / "assets"
    if assets_folder.is_dir():
        for name in HEADER_CANDIDATE_NAMES:
            candidate = assets_folder / name
            if candidate.is_file():
                return normalize_path(candidate)
    return None


def bundled_asset_path(name: str) -> Path | None:
    base_folder = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent.parent))
    candidates = [
        base_folder / "assets" / name,
        Path(__file__).resolve().parent.parent / "assets" / name,
        Path.cwd() / "assets" / name,
    ]
    for candidate in candidates:
        if candidate.is_file():
            return normalize_path(candidate)
    return None


def powershell_string(value: str | Path) -> str:
    return "'" + str(value).replace("'", "''") + "'"


def shortcut_argument(value: str | Path) -> str:
    return '"' + str(value).replace('"', '\\"') + '"'


def shortcut_argument_string(values: list[str | Path]) -> str:
    return " ".join(shortcut_argument(value) for value in values)


def running_app_shortcut_target(
    extra_arguments: list[str | Path] | None = None,
) -> tuple[Path, str, Path]:
    extra_arguments = extra_arguments or []
    if getattr(sys, "frozen", False):
        executable = Path(sys.executable)
        return executable, shortcut_argument_string(extra_arguments), executable.parent
    script = Path(__file__).resolve()
    arguments = shortcut_argument_string([script, *extra_arguments])
    return Path(sys.executable), arguments, script.parent.parent


def desktop_shortcut_path() -> Path:
    desktop = Path(os.environ.get("USERPROFILE", str(Path.home()))) / "Desktop"
    return desktop / f"{APP_NAME}.lnk"


def app_desktop_shortcut_path(app: HubApp) -> Path:
    desktop = Path(os.environ.get("USERPROFILE", str(Path.home()))) / "Desktop"
    return desktop / f"{safe_shortcut_name(app.name)}.lnk"


def create_windows_shortcut(
    shortcut_path: Path,
    target: Path,
    arguments: str,
    working_dir: Path,
    *,
    icon_path: Path | None = None,
) -> Path:
    if not sys.platform.startswith("win"):
        raise RuntimeError("Desktop shortcut creation is currently supported on Windows only.")
    shortcut_path.parent.mkdir(parents=True, exist_ok=True)
    icon = icon_path if icon_path is not None and icon_path.exists() else target
    script = "\n".join(
        [
            "$ErrorActionPreference = 'Stop'",
            "$shell = New-Object -ComObject WScript.Shell",
            f"$shortcut = $shell.CreateShortcut({powershell_string(shortcut_path)})",
            f"$shortcut.TargetPath = {powershell_string(target)}",
            f"$shortcut.Arguments = {powershell_string(arguments)}",
            f"$shortcut.WorkingDirectory = {powershell_string(working_dir)}",
            f"$shortcut.IconLocation = {powershell_string(icon)}",
            "$shortcut.Save()",
        ]
    )
    result = subprocess.run(
        ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", script],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        detail = (result.stderr or result.stdout or "Unknown shortcut creation error.").strip()
        raise RuntimeError(detail)
    return shortcut_path


def create_desktop_shortcut_file() -> Path:
    target, arguments, working_dir = running_app_shortcut_target()
    return create_windows_shortcut(desktop_shortcut_path(), target, arguments, working_dir)


def create_app_desktop_shortcut_file(
    app: HubApp,
    record: InstallRecord,
    hub_folder: Path | None = None,
) -> Path:
    target, arguments, working_dir = running_app_shortcut_target(["--launch-app", app.app_id])
    executable = Path(record.executable_path)
    icon = None
    if hub_folder is not None:
        icon = resolve_app_shortcut_icon_path(hub_folder, app)
    if icon is None and executable.exists():
        icon = executable
    return create_windows_shortcut(
        app_desktop_shortcut_path(app),
        target,
        arguments,
        working_dir,
        icon_path=icon,
    )


def running_hub_install_folder() -> Path:
    if getattr(sys, "frozen", False):
        return normalize_path(Path(sys.executable).parent)
    return normalize_path(Path(__file__).resolve().parent.parent)


def write_self_update_script(zip_path: Path, target_folder: Path) -> Path:
    script_path = APP_DATA_FOLDER / "hub_self_update.ps1"
    exe_name = Path(sys.executable).name if getattr(sys, "frozen", False) else f"{APP_NAME}.exe"
    blocked_names = ",".join(
        powershell_string(name) for name in sorted(PROTECTED_UPDATE_FOLDER_NAMES) if name
    )
    script = "\n".join(
        [
            "$ErrorActionPreference = 'Stop'",
            f"$pidToWait = {os.getpid()}",
            f"$zipPath = {powershell_string(zip_path)}",
            f"$target = {powershell_string(target_folder)}",
            f"$exeName = {powershell_string(exe_name)}",
            f"$blockedNames = @({blocked_names})",
            f"$markerName = {powershell_string(INSTALL_MARKER_NAME)}",
            "$stage = Join-Path ([System.IO.Path]::GetTempPath()) ('BusinessAppHubUpdate_' + [guid]::NewGuid().ToString())",
            "$backupRoot = Join-Path $env:LOCALAPPDATA 'Business App Hub\\Backups'",
            "$backup = Join-Path $backupRoot ('HubSelfUpdate_' + (Get-Date -Format 'yyyyMMdd_HHmmss'))",
            "try { Wait-Process -Id $pidToWait -Timeout 45 -ErrorAction SilentlyContinue } catch { }",
            "$targetLeaf = (Split-Path -Leaf $target).ToLowerInvariant()",
            "$targetRoot = [System.IO.Path]::GetPathRoot($target)",
            "if ($target.TrimEnd('\\') -eq $targetRoot.TrimEnd('\\')) {",
            "    throw ('Refusing to update drive root: ' + $target)",
            "}",
            "if ($blockedNames -contains $targetLeaf) {",
            "    throw ('Refusing to update broad folder: ' + $target)",
            "}",
            "if (-not (Test-Path -LiteralPath (Join-Path $target $exeName))) {",
            "    throw ('Refusing to update because the expected executable was not found: ' + (Join-Path $target $exeName))",
            "}",
            "if (-not (Test-Path -LiteralPath (Join-Path $target '_internal'))) {",
            "    throw ('Refusing to update because the expected _internal folder was not found: ' + (Join-Path $target '_internal'))",
            "}",
            "if (-not (Test-Path -LiteralPath (Join-Path $target $markerName))) {",
            "    throw ('Refusing to update because the Business App Hub install marker was not found: ' + (Join-Path $target $markerName))",
            "}",
            "New-Item -ItemType Directory -Force -Path $stage | Out-Null",
            "New-Item -ItemType Directory -Force -Path $backup | Out-Null",
            "Expand-Archive -LiteralPath $zipPath -DestinationPath $stage -Force",
            "$payload = $stage",
            "if (-not (Test-Path -LiteralPath (Join-Path $payload $exeName))) {",
            "    foreach ($child in Get-ChildItem -LiteralPath $stage -Directory) {",
            "        if (Test-Path -LiteralPath (Join-Path $child.FullName $exeName)) {",
            "            $payload = $child.FullName",
            "            break",
            "        }",
            "    }",
            "}",
            "if (-not (Test-Path -LiteralPath (Join-Path $payload $exeName))) {",
            "    throw ('Updated hub package did not contain ' + $exeName)",
            "}",
            "$payloadItems = @(Get-ChildItem -LiteralPath $payload -Force)",
            "foreach ($item in $payloadItems) {",
            "    $existing = Join-Path $target $item.Name",
            "    if (Test-Path -LiteralPath $existing) {",
            "        Copy-Item -LiteralPath $existing -Destination $backup -Recurse -Force",
            "    }",
            "}",
            "try {",
            "    foreach ($item in $payloadItems) {",
            "        Copy-Item -LiteralPath $item.FullName -Destination $target -Recurse -Force",
            "    }",
            "} catch {",
            "    if (Test-Path -LiteralPath $backup) {",
            "        Get-ChildItem -LiteralPath $backup -Force | Copy-Item -Destination $target -Recurse -Force -ErrorAction SilentlyContinue",
            "    }",
            "    throw",
            "}",
            "Start-Process -FilePath (Join-Path $target $exeName)",
            "Start-Sleep -Seconds 2",
            "Remove-Item -LiteralPath $stage -Recurse -Force -ErrorAction SilentlyContinue",
            "Remove-Item -LiteralPath $zipPath -Force -ErrorAction SilentlyContinue",
        ]
    )
    APP_DATA_FOLDER.mkdir(parents=True, exist_ok=True)
    script_path.write_text(script, encoding="utf-8")
    return script_path


def start_hub_self_update(zip_path: Path) -> None:
    if not getattr(sys, "frozen", False):
        raise RuntimeError("Hub self-update is only available from the packaged EXE.")
    target_folder = running_hub_install_folder()
    if not target_folder.exists():
        raise FileNotFoundError(f"Hub install folder was not found:\n\n{target_folder}")
    exe_name = Path(sys.executable).name
    ensure_self_update_marker(target_folder, exe_name)
    script_path = write_self_update_script(zip_path, target_folder)
    subprocess.Popen(
        [
            "powershell",
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(script_path),
        ],
        cwd=str(target_folder),
        creationflags=subprocess.CREATE_NO_WINDOW if sys.platform.startswith("win") else 0,
    )


def open_path(path: Path) -> None:
    if sys.platform.startswith("win"):
        os.startfile(path)  # type: ignore[attr-defined]
    elif sys.platform == "darwin":
        subprocess.Popen(["open", str(path)])
    else:
        subprocess.Popen(["xdg-open", str(path)])


class BusinessAppHub(tk.Tk):
    def __init__(self) -> None:
        super().__init__()
        self.title(f"{APP_NAME} {APP_VERSION}")
        self.geometry("1180x740")
        self.minsize(960, 620)

        self.hub_folder: Path | None = None
        self.catalog = HubCatalog()
        self.app_rows: dict[str, HubApp] = {}
        self.card_frames: dict[str, tk.Frame] = {}
        self.icon_images: dict[str, tk.PhotoImage] = {}
        self.selected_app_id: str | None = None

        self.path_text = tk.StringVar()
        self.status_text = tk.StringVar(value="Choose the Business App Hub folder.")
        self.detail_title = tk.StringVar(value="Select an app")
        self.detail_meta = tk.StringVar(value="Choose an app from the library.")

        self.apply_theme()
        self.build_ui()
        self.after(100, self.start_folder_discovery)

    def apply_theme(self) -> None:
        self.configure(bg=COLORS["background"])
        style = ttk.Style(self)
        try:
            style.theme_use("clam")
        except tk.TclError:
            pass
        style.configure(
            "Portal.TEntry",
            fieldbackground="#ffffff",
            bordercolor=COLORS["border"],
            lightcolor=COLORS["border"],
            darkcolor=COLORS["border"],
        )
        style.configure(
            "Portal.Vertical.TScrollbar",
            background=COLORS["nav_light"],
            troughcolor=COLORS["panel_alt"],
            arrowcolor="#ffffff",
            bordercolor=COLORS["panel_alt"],
        )

    def build_ui(self) -> None:
        self.columnconfigure(0, weight=1)
        self.rowconfigure(2, weight=1)

        header = tk.Frame(self, bg=COLORS["nav"], padx=18, pady=16)
        header.grid(row=0, column=0, sticky="ew")
        header.columnconfigure(1, weight=1)

        tk.Label(
            header,
            text=APP_NAME,
            bg=COLORS["nav"],
            fg="#ffffff",
            font=(FONT_FAMILY, 21, "bold"),
        ).grid(row=0, column=0, sticky="w")
        tk.Label(
            header,
            text="Company apps, updates, and rollback control in one place.",
            bg=COLORS["nav"],
            fg="#cfe8ff",
            font=(FONT_FAMILY, 10),
        ).grid(row=1, column=0, sticky="w", pady=(3, 0))
        tk.Label(
            header,
            text=f"v{APP_VERSION}",
            bg=COLORS["accent"],
            fg=COLORS["text"],
            font=(FONT_FAMILY, 10, "bold"),
            padx=12,
            pady=5,
        ).grid(row=0, column=2, sticky="e")

        path_bar = tk.Frame(self, bg=COLORS["panel_alt"], padx=18, pady=12)
        path_bar.grid(row=1, column=0, sticky="ew")
        path_bar.columnconfigure(1, weight=1)
        tk.Label(
            path_bar,
            text="Hub folder",
            bg=COLORS["panel_alt"],
            fg=COLORS["text"],
            font=(FONT_FAMILY, 10, "bold"),
        ).grid(row=0, column=0, sticky="w")
        self.path_entry = ttk.Entry(path_bar, textvariable=self.path_text, style="Portal.TEntry")
        self.path_entry.grid(row=0, column=1, sticky="ew", padx=(10, 10))
        self.portal_button(path_bar, "Browse", self.browse_hub_folder).grid(
            row=0, column=2, padx=(0, 8)
        )
        self.portal_button(path_bar, "Refresh", self.refresh_catalog).grid(row=0, column=3)
        tk.Label(
            path_bar,
            textvariable=self.status_text,
            bg=COLORS["panel_alt"],
            fg=COLORS["muted"],
            font=(FONT_FAMILY, 9),
        ).grid(row=1, column=1, columnspan=3, sticky="w", pady=(7, 0))

        body = tk.Frame(self, bg=COLORS["background"], padx=18, pady=16)
        body.grid(row=2, column=0, sticky="nsew")
        body.columnconfigure(0, weight=5, uniform="body")
        body.columnconfigure(1, weight=7, uniform="body")
        body.rowconfigure(0, weight=1)

        self.build_library_panel(body)
        self.build_detail_panel(body)

        footer = tk.Frame(self, bg=COLORS["background"], padx=18, pady=0)
        footer.grid(row=3, column=0, sticky="ew", pady=(0, 14))
        self.portal_button(footer, "Open Hub Folder", self.open_hub_folder).grid(
            row=0, column=0, sticky="w"
        )
        self.portal_button(footer, "Open GitHub Help", self.open_github_help).grid(
            row=0, column=1, sticky="w", padx=(8, 0)
        )

    def build_library_panel(self, parent: tk.Widget) -> None:
        library = tk.Frame(
            parent,
            bg=COLORS["panel"],
            highlightbackground=COLORS["border"],
            highlightthickness=1,
            padx=14,
            pady=12,
        )
        library.grid(row=0, column=0, sticky="nsew", padx=(0, 8))
        library.columnconfigure(0, weight=1)
        library.rowconfigure(2, weight=1)

        tk.Label(
            library,
            text="App Library",
            bg=COLORS["panel"],
            fg=COLORS["text"],
            font=(FONT_FAMILY, 15, "bold"),
        ).grid(row=0, column=0, sticky="w")
        tk.Label(
            library,
            text="Click an app card to open its page.",
            bg=COLORS["panel"],
            fg=COLORS["muted"],
            font=(FONT_FAMILY, 9),
        ).grid(row=1, column=0, sticky="w", pady=(2, 10))

        scroll_shell = tk.Frame(library, bg=COLORS["panel"])
        scroll_shell.grid(row=2, column=0, sticky="nsew")
        scroll_shell.columnconfigure(0, weight=1)
        scroll_shell.rowconfigure(0, weight=1)

        self.apps_canvas = tk.Canvas(
            scroll_shell,
            bg=COLORS["panel"],
            highlightthickness=0,
            borderwidth=0,
        )
        self.apps_canvas.grid(row=0, column=0, sticky="nsew")
        app_scrollbar = ttk.Scrollbar(
            scroll_shell,
            orient="vertical",
            command=self.apps_canvas.yview,
            style="Portal.Vertical.TScrollbar",
        )
        app_scrollbar.grid(row=0, column=1, sticky="ns")
        self.apps_canvas.configure(yscrollcommand=app_scrollbar.set)

        self.cards_inner = tk.Frame(self.apps_canvas, bg=COLORS["panel"])
        self.cards_window = self.apps_canvas.create_window(
            (0, 0), window=self.cards_inner, anchor="nw"
        )
        self.cards_inner.bind(
            "<Configure>",
            lambda _event: self.apps_canvas.configure(
                scrollregion=self.apps_canvas.bbox("all")
            ),
        )
        self.apps_canvas.bind(
            "<Configure>",
            lambda event: self.apps_canvas.itemconfigure(self.cards_window, width=event.width),
        )

    def build_detail_panel(self, parent: tk.Widget) -> None:
        detail = tk.Frame(
            parent,
            bg=COLORS["card"],
            highlightbackground=COLORS["border"],
            highlightthickness=1,
            padx=18,
            pady=16,
        )
        detail.grid(row=0, column=1, sticky="nsew", padx=(8, 0))
        detail.columnconfigure(0, weight=1)
        detail.rowconfigure(4, weight=1)

        hero = tk.Frame(detail, bg=COLORS["card"])
        hero.grid(row=0, column=0, sticky="ew")
        hero.columnconfigure(1, weight=1)
        self.detail_icon_label = tk.Label(
            hero,
            text="APP",
            width=8,
            height=4,
            bg=COLORS["nav_light"],
            fg="#ffffff",
            font=(FONT_FAMILY, 15, "bold"),
        )
        self.detail_icon_label.grid(row=0, column=0, rowspan=2, sticky="nw", padx=(0, 14))
        tk.Label(
            hero,
            textvariable=self.detail_title,
            bg=COLORS["card"],
            fg=COLORS["text"],
            font=(FONT_FAMILY, 20, "bold"),
        ).grid(row=0, column=1, sticky="w")
        tk.Label(
            hero,
            textvariable=self.detail_meta,
            bg=COLORS["card"],
            fg=COLORS["muted"],
            font=(FONT_FAMILY, 10),
        ).grid(row=1, column=1, sticky="w", pady=(2, 0))

        tk.Label(
            detail,
            text="Editable Description",
            bg=COLORS["card"],
            fg=COLORS["text"],
            font=(FONT_FAMILY, 11, "bold"),
        ).grid(row=1, column=0, sticky="w", pady=(18, 6))
        self.description_editor = tk.Text(
            detail,
            height=7,
            wrap="word",
            bg="#fffdf0",
            fg=COLORS["text"],
            insertbackground=COLORS["text"],
            relief="solid",
            borderwidth=1,
            font=(FONT_FAMILY, 10),
            padx=10,
            pady=8,
        )
        self.description_editor.grid(row=2, column=0, sticky="ew")
        self.description_editor.configure(state="disabled")

        description_buttons = tk.Frame(detail, bg=COLORS["card"])
        description_buttons.grid(row=3, column=0, sticky="ew", pady=(8, 12))
        description_buttons.columnconfigure(0, weight=1)
        self.save_description_button = self.portal_button(
            description_buttons,
            "Save Description",
            self.save_selected_description,
            state="disabled",
        )
        self.save_description_button.grid(row=0, column=1, sticky="e")

        releases_frame = tk.Frame(detail, bg=COLORS["card"])
        releases_frame.grid(row=4, column=0, sticky="nsew")
        releases_frame.columnconfigure(0, weight=1)
        releases_frame.rowconfigure(1, weight=1)
        tk.Label(
            releases_frame,
            text="Allowed Releases",
            bg=COLORS["card"],
            fg=COLORS["text"],
            font=(FONT_FAMILY, 11, "bold"),
        ).grid(row=0, column=0, sticky="w", pady=(0, 6))
        self.release_list = tk.Listbox(
            releases_frame,
            bg=COLORS["panel_alt"],
            fg=COLORS["text"],
            relief="flat",
            activestyle="none",
            font=(FONT_FAMILY, 10),
            height=7,
        )
        self.release_list.grid(row=1, column=0, sticky="nsew")

        action_row = tk.Frame(detail, bg=COLORS["card"])
        action_row.grid(row=5, column=0, sticky="ew", pady=(14, 0))
        for index in range(3):
            action_row.columnconfigure(index, weight=1)
        self.open_source_button = self.portal_button(
            action_row,
            "Open Source Folder",
            self.open_selected_source_folder,
            state="disabled",
        )
        self.open_source_button.grid(row=0, column=0, sticky="ew", padx=(0, 6))
        self.install_button = self.portal_button(
            action_row,
            "Install / Update",
            self.install_selected_placeholder,
            state="disabled",
            accent=True,
        )
        self.install_button.grid(row=0, column=1, sticky="ew", padx=6)
        self.launch_button = self.portal_button(
            action_row,
            "Launch",
            self.launch_selected_placeholder,
            state="disabled",
        )
        self.launch_button.grid(row=0, column=2, sticky="ew", padx=(6, 0))

    def portal_button(
        self,
        parent: tk.Widget,
        text: str,
        command,
        *,
        state: str = "normal",
        accent: bool = False,
    ) -> tk.Button:
        bg = COLORS["accent"] if accent else COLORS["button"]
        fg = COLORS["text"] if accent else "#ffffff"
        button = tk.Button(
            parent,
            text=text,
            command=command,
            state=state,
            bg=bg,
            fg=fg,
            activebackground=COLORS["accent_dark"] if accent else COLORS["button_hover"],
            activeforeground=COLORS["text"] if accent else "#ffffff",
            disabledforeground="#8aa1b6",
            relief="flat",
            padx=14,
            pady=8,
            font=(FONT_FAMILY, 9, "bold"),
            cursor="hand2",
        )
        return button

    def start_folder_discovery(self) -> None:
        found = find_hub_folder()
        if found is None:
            messagebox.showinfo(
                APP_NAME,
                "I could not automatically find the Business App Hub folder.\n\n"
                "Please browse to the folder that contains catalog.json.",
            )
            self.browse_hub_folder()
            return

        answer = messagebox.askyesno(
            APP_NAME,
            "I found this Business App Hub folder:\n\n"
            f"{found}\n\nIs this the correct hub folder?",
        )
        if answer:
            self.set_hub_folder(found)
        else:
            self.browse_hub_folder()

    def browse_hub_folder(self) -> None:
        initial = str(self.hub_folder or Path.home())
        folder = filedialog.askdirectory(
            title="Select Business App Hub folder",
            initialdir=initial,
        )
        if not folder:
            return
        selected = Path(folder)
        if not is_valid_hub_folder(selected):
            messagebox.showerror(
                APP_NAME,
                "That folder does not look like a Business App Hub folder.\n\n"
                "Choose the folder that contains catalog.json.",
            )
            return
        self.set_hub_folder(selected)

    def set_hub_folder(self, folder: Path) -> None:
        self.hub_folder = normalize_path(folder)
        self.path_text.set(str(self.hub_folder))
        save_hub_folder(self.hub_folder)
        self.load_header_texture()
        self.paint_header_canvas()
        self.refresh_catalog()

    def refresh_catalog(self) -> None:
        if self.hub_folder is None:
            self.status_text.set("No hub folder selected.")
            return
        previous_selection = self.selected_app_id
        try:
            self.catalog = load_catalog(self.hub_folder)
        except Exception as exc:
            self.catalog = HubCatalog()
            self.status_text.set("Could not load catalog.json.")
            self.populate_apps()
            messagebox.showerror(APP_NAME, f"Could not read catalog.json:\n\n{exc}")
            return
        self.status_text.set(
            f"Loaded catalog v{self.catalog.hub_version} from {self.hub_folder}"
        )
        self.populate_apps(preferred_app_id=previous_selection)

    def populate_apps(self, preferred_app_id: str | None = None) -> None:
        for child in self.cards_inner.winfo_children():
            child.destroy()
        self.app_rows.clear()
        self.card_frames.clear()
        self.icon_images.clear()
        self.selected_app_id = None
        self.show_empty_details()
        self.set_app_buttons("disabled")

        if not self.catalog.apps:
            empty_card = tk.Frame(
                self.cards_inner,
                bg=COLORS["card"],
                highlightbackground=COLORS["border"],
                highlightthickness=1,
                padx=18,
                pady=18,
            )
            empty_card.grid(row=0, column=0, sticky="ew", pady=(0, 10))
            self.cards_inner.columnconfigure(0, weight=1)
            tk.Label(
                empty_card,
                text="No apps published yet",
                bg=COLORS["card"],
                fg=COLORS["text"],
                font=(FONT_FAMILY, 13, "bold"),
            ).grid(row=0, column=0, sticky="w")
            tk.Label(
                empty_card,
                text="Add apps to catalog.json and refresh the hub.",
                bg=COLORS["card"],
                fg=COLORS["muted"],
                font=(FONT_FAMILY, 10),
            ).grid(row=1, column=0, sticky="w", pady=(4, 0))
            return

        select_id = preferred_app_id
        for app in self.catalog.apps:
            self.app_rows[app.app_id] = app
            self.create_app_card(app, len(self.card_frames))
        if select_id not in self.app_rows:
            select_id = self.catalog.apps[0].app_id
        if select_id:
            self.select_app(select_id)

    def create_app_card(self, app: HubApp, row: int) -> None:
        card = tk.Frame(
            self.cards_inner,
            bg=COLORS["card"],
            highlightbackground=COLORS["border"],
            highlightthickness=1,
            padx=12,
            pady=12,
            cursor="hand2",
        )
        card.grid(row=row, column=0, sticky="ew", pady=(0, 10))
        self.cards_inner.columnconfigure(0, weight=1)
        card.columnconfigure(1, weight=1)
        self.card_frames[app.app_id] = card

        icon = self.load_app_icon(app, 56)
        if icon:
            icon_label = tk.Label(card, image=icon, bg=COLORS["card"], width=62, height=62)
        else:
            icon_label = tk.Label(
                card,
                text=self.app_initials(app.name),
                bg=COLORS["nav_light"],
                fg="#ffffff",
                width=6,
                height=3,
                font=(FONT_FAMILY, 14, "bold"),
            )
        icon_label.grid(row=0, column=0, rowspan=3, sticky="nw", padx=(0, 12))

        tk.Label(
            card,
            text=app.name,
            bg=COLORS["card"],
            fg=COLORS["text"],
            font=(FONT_FAMILY, 13, "bold"),
        ).grid(row=0, column=1, sticky="w")
        tk.Label(
            card,
            text=f"Default: {app.default_version or '-'}",
            bg=COLORS["card"],
            fg=COLORS["muted"],
            font=(FONT_FAMILY, 9),
        ).grid(row=0, column=2, sticky="e", padx=(8, 0))
        tk.Label(
            card,
            text=self.short_description(app.description),
            bg=COLORS["card"],
            fg=COLORS["muted"],
            justify="left",
            wraplength=430,
            font=(FONT_FAMILY, 9),
        ).grid(row=1, column=1, columnspan=2, sticky="w", pady=(6, 0))
        tk.Label(
            card,
            text=self.release_status(app),
            bg=COLORS["panel_alt"],
            fg=COLORS["nav"],
            font=(FONT_FAMILY, 8, "bold"),
            padx=8,
            pady=3,
        ).grid(row=2, column=1, sticky="w", pady=(8, 0))
        self.bind_card_click(card, app.app_id)

    def bind_card_click(self, widget: tk.Widget, app_id: str) -> None:
        widget.bind("<Button-1>", lambda _event, item_id=app_id: self.select_app(item_id))
        for child in widget.winfo_children():
            self.bind_card_click(child, app_id)

    def selected_app(self) -> HubApp | None:
        if self.selected_app_id is None:
            return None
        return self.app_rows.get(self.selected_app_id)

    def select_app(self, app_id: str) -> None:
        app = self.app_rows.get(app_id)
        if app is None:
            self.show_empty_details()
            self.set_app_buttons("disabled")
            return
        self.selected_app_id = app_id
        self.paint_cards()
        self.show_app_details(app)
        self.set_app_buttons("normal")

    def paint_cards(self) -> None:
        for app_id, card in self.card_frames.items():
            selected = app_id == self.selected_app_id
            bg = COLORS["card_selected"] if selected else COLORS["card"]
            border = COLORS["nav_light"] if selected else COLORS["border"]
            card.configure(bg=bg, highlightbackground=border, highlightthickness=2 if selected else 1)
            self.paint_children(card, bg)

    def paint_children(self, widget: tk.Widget, bg: str) -> None:
        for child in widget.winfo_children():
            if isinstance(child, tk.Label) and child.cget("bg") in (
                COLORS["card"],
                COLORS["card_selected"],
            ):
                child.configure(bg=bg)
            if isinstance(child, tk.Frame):
                child.configure(bg=bg)
                self.paint_children(child, bg)

    def show_empty_details(self) -> None:
        self.detail_title.set("Select an app")
        self.detail_meta.set("Choose an app from the library.")
        self.detail_icon_label.configure(
            image="",
            text="APP",
            bg=COLORS["nav_light"],
            fg="#ffffff",
        )
        self.description_editor.configure(state="normal")
        self.description_editor.delete("1.0", "end")
        self.description_editor.insert(
            "1.0", "App descriptions can be edited after an app is selected."
        )
        self.description_editor.configure(state="disabled")
        self.release_list.delete(0, "end")

    def show_app_details(self, app: HubApp) -> None:
        self.detail_title.set(app.name)
        self.detail_meta.set(
            f"{app.app_id} | Default {app.default_version or '-'} | {self.release_status(app)}"
        )
        icon = self.load_app_icon(app, 96)
        if icon:
            self.detail_icon_label.configure(image=icon, text="", bg=COLORS["card"])
        else:
            self.detail_icon_label.configure(
                image="",
                text=self.app_initials(app.name),
                bg=COLORS["nav_light"],
                fg="#ffffff",
            )
        self.description_editor.configure(state="normal")
        self.description_editor.delete("1.0", "end")
        self.description_editor.insert("1.0", app.description or "")
        self.save_description_button.configure(state="normal")
        self.release_list.delete(0, "end")
        releases = app.published_releases
        if not releases:
            self.release_list.insert("end", "No allowed releases yet.")
        else:
            for release in releases:
                notes = release.notes or "No notes"
                self.release_list.insert("end", f"{release.version}    {notes}")

    def save_selected_description(self) -> None:
        app = self.selected_app()
        if app is None or self.hub_folder is None:
            return
        description = self.description_editor.get("1.0", "end").strip()
        try:
            update_catalog_app_fields(
                self.hub_folder,
                app.app_id,
                {"description": description},
            )
        except Exception as exc:
            messagebox.showerror(APP_NAME, f"Could not save description:\n\n{exc}")
            return
        self.status_text.set(f"Saved description for {app.name}.")
        self.refresh_catalog()

    def load_app_icon(self, app: HubApp, max_size: int) -> tk.PhotoImage | None:
        if self.hub_folder is None:
            return None
        key = f"{app.app_id}:{max_size}"
        if key in self.icon_images:
            return self.icon_images[key]
        path = resolve_app_icon_path(self.hub_folder, app)
        if path is None:
            return None
        image = load_icon_photo_image(path, max_size)
        if image is None:
            return None
        self.icon_images[key] = image
        return image

    def app_initials(self, name: str) -> str:
        parts = [part for part in name.replace("-", " ").split() if part]
        if len(parts) >= 2:
            return (parts[0][0] + parts[1][0]).upper()
        if parts:
            return parts[0][:2].upper()
        return "AP"

    def short_description(self, description: str, limit: int = 130) -> str:
        text = " ".join(description.split()) or "No description yet. Click to edit this app page."
        if len(text) <= limit:
            return text
        return text[: limit - 3].rstrip() + "..."

    def release_status(self, app: HubApp) -> str:
        count = len(app.published_releases)
        if count == 0:
            return "No allowed releases"
        if count == 1:
            return "1 allowed release"
        return f"{count} allowed releases"

    def set_app_buttons(self, state: str) -> None:
        self.open_source_button.configure(state=state)
        self.install_button.configure(state=state)
        self.launch_button.configure(state=state)
        self.save_description_button.configure(state=state)

    def app_source_folder(self, app: HubApp) -> Path | None:
        if self.hub_folder is None:
            return None
        return resolve_app_source_folder(self.hub_folder, app)

    def open_selected_source_folder(self) -> None:
        app = self.selected_app()
        if app is None:
            return
        source = self.app_source_folder(app)
        if source is None or not source.exists():
            messagebox.showinfo(
                APP_NAME,
                "This app does not have a source folder configured yet.",
            )
            return
        open_path(source)

    def install_selected_placeholder(self) -> None:
        app = self.selected_app()
        if app is None:
            return
        self.queue_download(app)

    def launch_selected_placeholder(self) -> None:
        app = self.selected_app()
        if app is None:
            return
        record = load_install_records().get(app.app_id)
        if record is None:
            messagebox.showinfo(APP_NAME, f"{app.name} is not installed on this computer yet.")
            return
        try:
            launch_install_record(record)
        except Exception as exc:
            messagebox.showerror(APP_NAME, f"Could not launch {app.name}:\n\n{exc}")

    def open_hub_folder(self) -> None:
        if self.hub_folder is None:
            messagebox.showinfo(APP_NAME, "No hub folder selected.")
            return
        open_path(self.hub_folder)

    def open_github_help(self) -> None:
        webbrowser.open("https://github.com/")


class SteamStyleBusinessAppHub(tk.Tk):
    def __init__(self) -> None:
        super().__init__()
        self.title(f"{APP_NAME} {APP_VERSION}")
        self.geometry("1320x820")
        self.minsize(1060, 680)

        self.hub_folder: Path | None = None
        self.catalog = HubCatalog()
        self.app_rows: dict[str, HubApp] = {}
        self.card_frames: dict[str, tk.Frame] = {}
        self.icon_images: dict[str, tk.PhotoImage] = {}
        self.install_records = load_install_records()
        self.installed_app_ids = load_installed_app_ids()
        self.selected_app_id: str | None = None
        self.current_view = "find"
        self.detail_back_view = "find"
        self.hovered_nav_view: str | None = None
        self.download_queue: list[DownloadTask] = []
        self.active_download: DownloadTask | None = None
        self.download_flash_on = False
        self.header_texture_image: tk.PhotoImage | None = None
        self.available_hub_release_url = ""
        self.available_hub_release_version = ""
        self.available_hub_release_asset_url = ""
        self.available_hub_release_asset_name = ""
        self.app_update_flash_on = False

        self.path_text = tk.StringVar()
        self.status_text = tk.StringVar(value="Choose the Business App Hub folder.")
        self.find_search_text = tk.StringVar()
        self.my_search_text = tk.StringVar()
        self.create_shortcut_on_download = tk.BooleanVar(
            value=bool(app_data_settings().get("create_app_shortcut_on_download", True))
        )
        self.download_text = tk.StringVar(value="No active downloads.")
        self.download_queue_text = tk.StringVar(value="Queue: 0")
        self.download_progress = tk.IntVar(value=0)
        self.publish_mode_text = tk.StringVar(value="Update existing app")
        self.publish_app_id_text = tk.StringVar()
        self.publish_new_name_text = tk.StringVar()
        self.publish_new_id_text = tk.StringVar()
        self.publish_version_text = tk.StringVar()
        self.publish_release_name_text = tk.StringVar()
        self.publish_executable_text = tk.StringVar()
        self.publish_package_text = tk.StringVar()
        self.publish_icon_text = tk.StringVar()
        self.publish_release_image_text = tk.StringVar()
        self.publish_status_text = tk.StringVar(value="Choose an app package to publish.")
        self.detail_version_text = tk.StringVar()
        github_updates_enabled, github_url = load_github_update_settings()
        self.github_updates_enabled = tk.BooleanVar(value=github_updates_enabled)
        self.github_release_url_text = tk.StringVar(value=github_url)
        coder_settings_open, device_admin = load_coder_settings()
        self.coder_settings_open = tk.BooleanVar(value=coder_settings_open)
        self.device_admin = tk.BooleanVar(value=device_admin)

        self.apply_theme()
        self.build_ui()
        self.after(20, self.open_full_screen)
        self.after(100, self.start_folder_discovery)
        self.after(450, self.show_current_version_notes_once)
        self.after(1200, self.check_github_updates_on_startup)
        self.after(650, self.pulse_app_update_alert)

    def open_full_screen(self) -> None:
        try:
            self.state("zoomed")
        except tk.TclError:
            screen_width = self.winfo_screenwidth()
            screen_height = self.winfo_screenheight()
            self.geometry(f"{screen_width}x{screen_height}+0+0")

    def apply_theme(self) -> None:
        self.configure(bg=COLORS["background"])
        style = ttk.Style(self)
        try:
            style.theme_use("clam")
        except tk.TclError:
            pass
        style.configure(
            "Dark.TEntry",
            fieldbackground=COLORS["panel"],
            foreground=COLORS["text"],
            bordercolor=COLORS["border"],
            lightcolor=COLORS["border"],
            darkcolor=COLORS["border"],
        )
        style.configure(
            "Dark.TCombobox",
            fieldbackground=COLORS["panel"],
            foreground=COLORS["text"],
            background=COLORS["panel"],
            bordercolor=COLORS["border"],
            arrowcolor=COLORS["accent"],
            selectbackground=COLORS["accent_dark"],
            selectforeground=COLORS["text"],
            lightcolor=COLORS["border"],
            darkcolor=COLORS["border"],
            insertcolor=COLORS["text"],
            padding=3,
            arrowsize=16,
        )
        style.map(
            "Dark.TCombobox",
            fieldbackground=[
                ("readonly", COLORS["panel"]),
                ("disabled", COLORS["panel_alt"]),
                ("!disabled", COLORS["panel"]),
            ],
            foreground=[
                ("readonly", COLORS["text"]),
                ("disabled", COLORS["muted"]),
                ("!disabled", COLORS["text"]),
            ],
            background=[
                ("active", COLORS["card_hover"]),
                ("readonly", COLORS["panel"]),
                ("!disabled", COLORS["panel"]),
            ],
            selectbackground=[("readonly", COLORS["accent_dark"])],
            selectforeground=[("readonly", COLORS["text"])],
            arrowcolor=[("active", COLORS["text"]), ("!disabled", COLORS["accent"])],
        )
        self.option_add("*TCombobox*Listbox.background", COLORS["panel_high"])
        self.option_add("*TCombobox*Listbox.foreground", COLORS["text"])
        self.option_add("*TCombobox*Listbox.selectBackground", COLORS["accent_dark"])
        self.option_add("*TCombobox*Listbox.selectForeground", COLORS["text"])
        style.configure(
            "Portal.Vertical.TScrollbar",
            background=COLORS["panel_high"],
            troughcolor=COLORS["panel"],
            arrowcolor=COLORS["text"],
            bordercolor=COLORS["panel"],
        )
        style.configure(
            "Download.Horizontal.TProgressbar",
            background=COLORS["accent"],
            troughcolor=COLORS["panel_alt"],
            bordercolor=COLORS["panel_alt"],
            lightcolor=COLORS["accent"],
            darkcolor=COLORS["accent_dark"],
        )

    def build_ui(self) -> None:
        self.columnconfigure(0, weight=1)
        self.rowconfigure(1, weight=1)
        self.build_top_chrome()
        self.content = tk.Frame(self, bg=COLORS["background"], padx=18, pady=14)
        self.content.grid(row=1, column=0, sticky="nsew")
        self.content.columnconfigure(0, weight=1)
        self.content.rowconfigure(0, weight=1)
        self.build_downloads_bar()

    def build_top_chrome(self) -> None:
        chrome = tk.Frame(self, bg=COLORS["chrome_top"])
        chrome.grid(row=0, column=0, sticky="ew")
        chrome.columnconfigure(0, weight=1)

        header = tk.Frame(chrome, bg=COLORS["chrome_top"], height=96)
        header.grid(row=0, column=0, sticky="ew")
        header.grid_propagate(False)
        header.columnconfigure(0, weight=1)

        self.header_canvas = tk.Canvas(header, highlightthickness=0, bd=0)
        self.header_canvas.place(relx=0, rely=0, relwidth=1, relheight=1)
        self.header_canvas.bind("<Configure>", lambda _event: self.paint_header_canvas())

        self.load_header_texture()
        self.paint_header_canvas()

        self.nav_frame = tk.Frame(chrome, bg=COLORS["background"], padx=20)
        self.nav_frame.grid(row=1, column=0, sticky="ew", pady=(10, 8))
        self.nav_frame.columnconfigure(6, weight=1)
        self.nav_order = ("my", "find", "publish", "guide", "history", "settings")
        self.admin_nav_views = {"publish", "guide"}
        self.nav_buttons: dict[str, tk.Label] = {}
        self.build_nav_tab("my", "MY APPS", 0)
        self.build_nav_tab("find", "FIND APPS", 1)
        self.build_nav_tab("publish", "PUBLISH APPS", 2)
        self.build_nav_tab("guide", "UPDATE GUIDE", 3)
        self.build_nav_tab("history", "VERSION HISTORY", 4)
        self.build_nav_tab("settings", "SETTINGS", 5)

        self.nav_search_frame = tk.Frame(self.nav_frame, bg=COLORS["background"])
        self.nav_search_frame.grid(row=0, column=6, sticky="e")
        tk.Label(
            self.nav_search_frame,
            text="Search",
            bg=COLORS["background"],
            fg=COLORS["muted"],
            font=(FONT_FAMILY, 9, "bold"),
        ).grid(row=0, column=0, sticky="e", padx=(0, 8))
        self.nav_search_entry = ttk.Entry(self.nav_search_frame, style="Dark.TEntry", width=30)
        self.nav_search_entry.grid(row=0, column=1, sticky="e")
        self.nav_search_entry.bind("<KeyRelease>", self.on_nav_search_changed)
        self.paint_nav()

    def build_nav_tab(self, view: str, text: str, column: int) -> None:
        tab = tk.Label(
            self.nav_frame,
            text=text,
            bg=COLORS["background"],
            fg=COLORS["nav_text"],
            padx=13,
            pady=4,
            font=(FONT_FAMILY, 10, "bold"),
            cursor="hand2",
            highlightthickness=0,
        )
        tab.grid(row=0, column=column, sticky="w", padx=(0, 20), pady=(0, 0))
        tab.bind("<Button-1>", lambda _event, selected=view: self.switch_view(selected))
        tab.bind("<Enter>", lambda _event, selected=view: self.set_nav_hover(selected))
        tab.bind("<Leave>", lambda _event: self.set_nav_hover(None))
        self.nav_buttons[view] = tab

    def set_nav_hover(self, view: str | None) -> None:
        self.hovered_nav_view = view
        self.paint_nav()

    def active_search_var(self) -> tk.StringVar | None:
        if self.current_view == "find":
            return self.find_search_text
        if self.current_view == "my":
            return self.my_search_text
        return None

    def on_nav_search_changed(self, _event: object | None = None) -> None:
        if self.current_view in ("find", "my"):
            self.render_current_view()

    def load_header_texture(self) -> None:
        self.header_texture_image = None
        bundled_path = bundled_asset_path(BUNDLED_HEADER_IMAGE_NAME)
        if bundled_path is not None:
            try:
                self.header_texture_image = tk.PhotoImage(file=str(bundled_path))
                return
            except tk.TclError:
                self.header_texture_image = None
        if self.hub_folder is None:
            return
        path = resolve_hub_header_texture_path(self.hub_folder)
        if path is None:
            return
        try:
            self.header_texture_image = tk.PhotoImage(file=str(path))
        except tk.TclError:
            self.header_texture_image = None

    def paint_header_canvas(self) -> None:
        canvas = getattr(self, "header_canvas", None)
        if canvas is None:
            return
        width = max(canvas.winfo_width(), 1)
        height = max(canvas.winfo_height(), 1)
        canvas.delete("header")
        self.paint_gradient(canvas, COLORS["chrome_top"], COLORS["chrome_bottom"], tag="header")
        if self.header_texture_image is not None:
            image = self.header_texture_image
            canvas.create_image(width // 2, height // 2, image=image, anchor="center", tags="header")
        canvas.create_text(
            24,
            34,
            text=APP_NAME,
            fill=COLORS["text"],
            font=(FONT_FAMILY, 25, "bold"),
            anchor="w",
            tags="header",
        )
        canvas.create_text(
            26,
            65,
            text="Company app library, approved releases, and update queue.",
            fill="#c7d5ee",
            font=(FONT_FAMILY, 10),
            anchor="w",
            tags="header",
        )
        badge_width = 64
        canvas.create_rectangle(
            width - badge_width - 20,
            25,
            width - 20,
            56,
            fill=COLORS["purple"],
            outline=COLORS["accent"],
            tags="header",
        )
        canvas.create_text(
            width - badge_width // 2 - 20,
            40,
            text=f"v{APP_VERSION}",
            fill="#ffffff",
            font=(FONT_FAMILY, 9, "bold"),
            anchor="center",
            tags="header",
        )

    def build_downloads_bar(self) -> None:
        self.downloads_bar = tk.Frame(self, bg=COLORS["download_idle"], height=72)
        self.downloads_bar.grid(row=2, column=0, sticky="ew")
        self.downloads_bar.grid_propagate(False)
        self.downloads_bar.columnconfigure(2, weight=1)

        tk.Label(
            self.downloads_bar,
            text="UPDATES",
            bg=COLORS["download_idle"],
            fg=COLORS["muted"],
            font=(FONT_FAMILY, 10, "bold"),
        ).grid(row=0, column=0, sticky="w", padx=(18, 16), pady=(13, 0))
        self.download_queue_label = tk.Label(
            self.downloads_bar,
            textvariable=self.download_queue_text,
            bg=COLORS["download_idle"],
            fg=COLORS["muted"],
            font=(FONT_FAMILY, 9),
        )
        self.download_queue_label.grid(row=1, column=0, sticky="w", padx=(18, 16))
        self.download_status_label = tk.Label(
            self.downloads_bar,
            textvariable=self.download_text,
            bg=COLORS["download_idle"],
            fg=COLORS["text"],
            font=(FONT_FAMILY, 10),
        )
        self.download_status_label.grid(row=0, column=1, sticky="w", padx=(0, 18), pady=(13, 0))
        self.download_progressbar = ttk.Progressbar(
            self.downloads_bar,
            variable=self.download_progress,
            maximum=100,
            style="Download.Horizontal.TProgressbar",
        )
        self.download_progressbar.grid(
            row=1,
            column=1,
            columnspan=2,
            sticky="ew",
            padx=(0, 18),
            pady=(4, 0),
        )
        self.hub_update_button = self.portal_button(
            self.downloads_bar,
            "Update Hub",
            self.open_available_hub_update,
            compact=True,
            accent=True,
        )
        self.hub_update_button.grid(row=0, column=3, rowspan=2, sticky="e", padx=(0, 8), pady=16)
        self.hub_update_button.grid_remove()
        self.portal_button(
            self.downloads_bar,
            "Open Hub Folder",
            self.open_hub_folder,
            compact=True,
            subtle=True,
        ).grid(row=0, column=4, rowspan=2, sticky="e", padx=(0, 8), pady=16)
        self.portal_button(
            self.downloads_bar,
            "GitHub Help",
            self.open_github_help,
            compact=True,
            subtle=True,
        ).grid(row=0, column=5, rowspan=2, sticky="e", padx=(0, 18), pady=16)

    def paint_gradient(
        self,
        canvas: tk.Canvas,
        top: str,
        bottom: str,
        *,
        tag: str = "gradient",
    ) -> None:
        width = max(canvas.winfo_width(), 1)
        height = max(canvas.winfo_height(), 1)
        canvas.delete(tag)
        top_rgb = self.hex_to_rgb(top)
        bottom_rgb = self.hex_to_rgb(bottom)
        for y in range(0, height, 2):
            ratio = y / max(height - 1, 1)
            color = self.rgb_to_hex(
                tuple(
                    int(top_rgb[index] + (bottom_rgb[index] - top_rgb[index]) * ratio)
                    for index in range(3)
                )
            )
            canvas.create_rectangle(0, y, width, y + 2, fill=color, outline=color, tags=tag)
        canvas.lower(tag)

    def hex_to_rgb(self, color: str) -> tuple[int, int, int]:
        color = color.lstrip("#")
        return tuple(int(color[index : index + 2], 16) for index in (0, 2, 4))

    def rgb_to_hex(self, rgb: tuple[int, int, int]) -> str:
        return "#" + "".join(f"{max(0, min(value, 255)):02x}" for value in rgb)

    def portal_button(
        self,
        parent: tk.Widget,
        text: str,
        command,
        *,
        state: str = "normal",
        accent: bool = False,
        compact: bool = False,
        subtle: bool = False,
    ) -> tk.Button:
        bg = COLORS["accent"] if accent else COLORS["button_dark"] if subtle else COLORS["button"]
        fg = COLORS["background"] if accent else COLORS["text"]
        return tk.Button(
            parent,
            text=text,
            command=command,
            state=state,
            bg=bg,
            fg=fg,
            activebackground=COLORS["accent_dark"] if accent else COLORS["button_hover"],
            activeforeground="#ffffff",
            disabledforeground="#67758c",
            relief="flat",
            padx=10 if compact else 15,
            pady=5 if compact else 9,
            font=(FONT_FAMILY, 9, "bold"),
            cursor="hand2",
        )

    def switch_view(self, view: str) -> None:
        if view in getattr(self, "admin_nav_views", set()) and not self.device_admin.get():
            view = "settings"
        self.current_view = view
        if view in ("my", "find", "publish", "guide", "history", "settings"):
            self.detail_back_view = view
        self.paint_nav()
        self.render_current_view()

    def paint_nav(self) -> None:
        active_view = self.detail_back_view if self.current_view == "detail" else self.current_view
        visible_views = [
            view
            for view in self.nav_order
            if view not in self.admin_nav_views or self.device_admin.get()
        ]
        for column in range(9):
            self.nav_frame.columnconfigure(column, weight=0)
        spacer_column = len(visible_views)
        self.nav_frame.columnconfigure(spacer_column, weight=1)
        for index, view in enumerate(visible_views):
            self.nav_buttons[view].grid(row=0, column=index, sticky="w", padx=(0, 20), pady=(0, 0))
        for view in self.nav_order:
            if view not in visible_views:
                self.nav_buttons[view].grid_remove()
        my_updates_available = self.any_app_update_available()
        for view, label in self.nav_buttons.items():
            if view not in visible_views:
                continue
            active = view == active_view
            hovered = view == self.hovered_nav_view
            text = "MY APPS - UPDATE AVAILABLE" if view == "my" and my_updates_available else label.cget("text")
            if view == "my" and not my_updates_available:
                text = "MY APPS"
            if view == "my" and my_updates_available:
                color = COLORS["update_green"] if self.app_update_flash_on else COLORS["accent"]
            else:
                color = COLORS["accent"] if active or hovered else COLORS["nav_text"]
            label.configure(
                text=text,
                bg=COLORS["background"],
                fg=color,
                font=(FONT_FAMILY, 10, "bold"),
                highlightthickness=0,
            )
        if hasattr(self, "nav_search_frame"):
            search_var = self.active_search_var()
            if search_var is None:
                self.nav_search_frame.grid_remove()
            else:
                self.nav_search_frame.grid(row=0, column=spacer_column + 1, sticky="e")
                self.nav_search_entry.configure(textvariable=search_var)

    def start_folder_discovery(self) -> None:
        saved = load_saved_hub_folder()
        if saved is not None:
            self.set_hub_folder(saved)
            return

        found = find_hub_folder()
        if found is None:
            messagebox.showinfo(
                APP_NAME,
                "I could not automatically find the Business App Hub folder.\n\n"
                "Please browse to the folder that contains catalog.json.",
            )
            self.browse_hub_folder()
            return

        answer = messagebox.askyesno(
            APP_NAME,
            "I found this Business App Hub folder:\n\n"
            f"{found}\n\nIs this the correct hub folder?",
        )
        if answer:
            self.set_hub_folder(found)
        else:
            self.browse_hub_folder()

    def browse_hub_folder(self) -> None:
        initial = str(self.hub_folder or Path.home())
        folder = filedialog.askdirectory(
            title="Select Business App Hub folder",
            initialdir=initial,
        )
        if not folder:
            return
        selected = Path(folder)
        if not is_valid_hub_folder(selected):
            messagebox.showerror(
                APP_NAME,
                "That folder does not look like a Business App Hub folder.\n\n"
                "Choose the folder that contains catalog.json.",
            )
            return
        self.set_hub_folder(selected)

    def set_hub_folder(self, folder: Path) -> None:
        self.hub_folder = normalize_path(folder)
        self.path_text.set(str(self.hub_folder))
        save_hub_folder(self.hub_folder)
        self.load_header_texture()
        self.paint_header_canvas()
        self.refresh_catalog()

    def refresh_catalog(self) -> None:
        if self.hub_folder is None:
            self.status_text.set("No hub folder selected.")
            return
        previous_selection = self.selected_app_id
        self.install_records = load_install_records()
        self.installed_app_ids = load_installed_app_ids()
        try:
            self.catalog = load_catalog(self.hub_folder)
        except Exception as exc:
            self.catalog = HubCatalog()
            self.app_rows.clear()
            self.status_text.set("Could not load catalog.json.")
            self.render_current_view()
            messagebox.showerror(APP_NAME, f"Could not read catalog.json:\n\n{exc}")
            return
        self.app_rows = {app.app_id: app for app in self.catalog.apps}
        self.status_text.set(
            f"Loaded catalog v{self.catalog.hub_version} from {self.hub_folder}"
        )
        self.render_current_view()
        if previous_selection in self.app_rows:
            self.select_app(previous_selection)

    def render_current_view(self) -> None:
        if self.current_view in ("publish", "guide") and not self.device_admin.get():
            self.current_view = "settings"
        for child in self.content.winfo_children():
            child.destroy()
        self.card_frames.clear()
        if self.current_view == "my":
            self.render_my_apps()
        elif self.current_view == "publish":
            self.render_publish_apps()
        elif self.current_view == "guide":
            self.render_update_guide()
        elif self.current_view == "history":
            self.render_version_history()
        elif self.current_view == "settings":
            self.render_settings()
        elif self.current_view == "detail":
            app = self.selected_app()
            if app is None:
                self.current_view = self.detail_back_view
                self.render_current_view()
            else:
                self.render_app_detail_page(app)
        else:
            self.render_find_apps()

    def current_version_history_entry(self) -> dict[str, object]:
        for entry in VERSION_HISTORY:
            if str(entry.get("version", "")).strip() == APP_VERSION:
                return entry
        return {
            "version": APP_VERSION,
            "name": "Current Update",
            "date": "",
            "changes": ("No update notes were added for this version.",),
        }

    def show_current_version_notes_once(self) -> None:
        settings = app_data_settings()
        seen_key = f"seen_version_notes_{APP_VERSION}"
        if settings.get(seen_key):
            return
        entry = self.current_version_history_entry()
        self.show_version_notes_popup(entry, seen_key)

    def show_version_notes_popup(self, entry: dict[str, object], seen_key: str) -> None:
        changes = entry.get("changes", ())
        if isinstance(changes, str):
            changes = (changes,)
        version = str(entry.get("version", APP_VERSION))
        update_name = str(entry.get("name", "Current Update"))
        date_text = str(entry.get("date", "")).strip()

        popup = tk.Toplevel(self)
        popup.title(f"What is New - {version} - {update_name}")
        popup.configure(bg=COLORS["background"])
        popup.transient(self)
        popup.grab_set()
        popup.resizable(False, False)
        popup.columnconfigure(0, weight=1)

        body = tk.Frame(
            popup,
            bg=COLORS["background"],
            highlightbackground=COLORS["border"],
            highlightthickness=1,
            padx=26,
            pady=24,
        )
        body.grid(row=0, column=0, sticky="nsew")
        body.columnconfigure(0, weight=1)

        tk.Label(
            body,
            text=f"{version} - {update_name}",
            bg=COLORS["background"],
            fg=COLORS["text"],
            font=(FONT_FAMILY, 18, "bold"),
            anchor="w",
        ).grid(row=0, column=0, sticky="ew")

        subtitle = f"Business App Hub is now on {version} - {update_name}."
        if date_text:
            subtitle += f"\nReleased: {date_text}"
        tk.Label(
            body,
            text=subtitle,
            bg=COLORS["background"],
            fg=COLORS["muted"],
            font=(FONT_FAMILY, 10, "bold"),
            anchor="w",
            justify="left",
        ).grid(row=1, column=0, sticky="ew", pady=(10, 14))

        notes = tk.Frame(body, bg=COLORS["panel_alt"], padx=16, pady=14)
        notes.grid(row=2, column=0, sticky="ew")
        notes.columnconfigure(0, weight=1)
        notes_text = "\n".join(f"- {change}" for change in changes)
        tk.Label(
            notes,
            text=f"Changes:\n{notes_text}",
            bg=COLORS["panel_alt"],
            fg=COLORS["text"],
            font=(FONT_FAMILY, 10),
            justify="left",
            anchor="w",
            wraplength=680,
        ).grid(row=0, column=0, sticky="ew")

        button_row = tk.Frame(body, bg=COLORS["background"])
        button_row.grid(row=3, column=0, sticky="e", pady=(18, 0))

        def close_popup(*, open_history: bool = False) -> None:
            settings = app_data_settings()
            settings[seen_key] = True
            save_app_data_settings(settings)
            popup.destroy()
            if open_history:
                self.switch_view("history")

        self.portal_button(
            button_row,
            "View Version History",
            lambda: close_popup(open_history=True),
            subtle=True,
        ).grid(row=0, column=0, padx=(0, 10))
        self.portal_button(
            button_row,
            "Continue",
            close_popup,
            accent=True,
        ).grid(row=0, column=1)

        popup.update_idletasks()
        width = popup.winfo_width()
        height = popup.winfo_height()
        x = self.winfo_rootx() + max((self.winfo_width() - width) // 2, 0)
        y = self.winfo_rooty() + max((self.winfo_height() - height) // 2, 0)
        popup.geometry(f"+{x}+{y}")
        popup.protocol("WM_DELETE_WINDOW", close_popup)

    def render_version_history(self) -> None:
        self.content.columnconfigure(0, weight=1)
        self.content.rowconfigure(0, weight=1)
        panel = self.portal_panel(self.content)
        panel.grid(row=0, column=0, sticky="nsew")
        panel.columnconfigure(0, weight=1)
        panel.rowconfigure(0, weight=1)

        _canvas, inner = self.scroll_area(panel, row=0)
        inner.columnconfigure(0, weight=1)
        page = tk.Frame(inner, bg=COLORS["panel"])
        page.grid(row=0, column=0, sticky="new", padx=42, pady=28)
        page.columnconfigure(0, weight=1)

        tk.Label(
            page,
            text="Version History",
            bg=COLORS["panel"],
            fg=COLORS["text"],
            font=(FONT_FAMILY, 24, "bold"),
        ).grid(row=0, column=0, sticky="w")
        tk.Label(
            page,
            text="Hub updates, names, and changes.",
            bg=COLORS["panel"],
            fg=COLORS["muted"],
            font=(FONT_FAMILY, 10),
        ).grid(row=1, column=0, sticky="w", pady=(4, 24))

        for row, entry in enumerate(VERSION_HISTORY, start=2):
            card = tk.Frame(
                page,
                bg=COLORS["panel_alt"],
                highlightbackground=COLORS["border"],
                highlightthickness=1,
                padx=18,
                pady=15,
            )
            card.grid(row=row, column=0, sticky="ew", pady=(0, 12))
            card.columnconfigure(0, weight=1)
            header_parts = [f"v{entry.get('version', '')}"]
            if entry.get("name"):
                header_parts.append(str(entry["name"]))
            if entry.get("date"):
                header_parts.append(str(entry["date"]))
            tk.Label(
                card,
                text="  |  ".join(header_parts),
                bg=COLORS["panel_alt"],
                fg=COLORS["text"],
                font=(FONT_FAMILY, 13, "bold"),
                anchor="w",
            ).grid(row=0, column=0, sticky="ew")
            changes = entry.get("changes", ())
            if isinstance(changes, str):
                changes = (changes,)
            tk.Label(
                card,
                text="\n".join(f"- {change}" for change in changes),
                bg=COLORS["panel_alt"],
                fg=COLORS["muted"],
                font=(FONT_FAMILY, 10),
                justify="left",
                anchor="w",
                wraplength=1120,
            ).grid(row=1, column=0, sticky="ew", pady=(8, 0))

    def reload_install_state(self) -> None:
        self.install_records = load_install_records()
        self.installed_app_ids = load_installed_app_ids()

    def install_record_for(self, app: HubApp) -> InstallRecord | None:
        record = self.install_records.get(app.app_id)
        if record is None:
            return None
        install_folder = Path(record.install_folder)
        executable = Path(record.executable_path)
        if is_helper_executable(executable, install_folder):
            repaired = find_installed_executable(install_folder, app)
            if repaired is not None and repaired != executable:
                record = InstallRecord(
                    app_id=record.app_id,
                    version=record.version,
                    install_folder=record.install_folder,
                    executable_path=str(repaired),
                )
                save_install_record(record)
                self.install_records[record.app_id] = record
                self.installed_app_ids.add(record.app_id)
        return record

    def is_app_installed(self, app: HubApp) -> bool:
        record = self.install_record_for(app)
        return record is not None and Path(record.executable_path).is_file()

    def installed_version_text(self, app: HubApp) -> str:
        record = self.install_record_for(app)
        if record is None:
            return "Not installed"
        if not Path(record.executable_path).is_file():
            return "Install record needs repair"
        return f"Installed {record.version}"

    def latest_catalog_version(self, app: HubApp) -> str:
        return latest_app_version(app)

    def app_update_available(self, app: HubApp) -> bool:
        return app_update_available_for_record(app, self.install_record_for(app))

    def any_app_update_available(self) -> bool:
        return any(self.app_update_available(app) for app in self.catalog.apps)

    def pulse_app_update_alert(self) -> None:
        self.app_update_flash_on = not self.app_update_flash_on
        if self.any_app_update_available():
            self.paint_nav()
            if self.current_view == "my":
                self.paint_cards()
        self.after(650, self.pulse_app_update_alert)

    def save_shortcut_download_preference(self) -> None:
        settings = app_data_settings()
        settings["create_app_shortcut_on_download"] = bool(
            self.create_shortcut_on_download.get()
        )
        save_app_data_settings(settings)

    def render_find_apps(self) -> None:
        self.content.columnconfigure(0, weight=1)
        self.content.columnconfigure(1, weight=0)
        self.content.rowconfigure(0, weight=1)
        panel = self.portal_panel(self.content)
        panel.grid(row=0, column=0, sticky="nsew")
        self.build_store_grid_page(
            panel,
            "FIND APPS",
            "Browse the company catalog. Click an app tile to open its page.",
            list(self.catalog.apps),
            "No apps in the company catalog yet",
            "Add app entries to the shared catalog.json, then refresh.",
            mode="find",
        )

    def render_my_apps(self) -> None:
        self.content.columnconfigure(0, weight=1)
        self.content.columnconfigure(1, weight=0)
        self.content.rowconfigure(0, weight=1)
        panel = self.portal_panel(self.content)
        panel.grid(row=0, column=0, sticky="nsew")
        apps = [app for app in self.catalog.apps if self.is_app_installed(app)]
        self.build_store_grid_page(
            panel,
            "MY APPS",
            "Apps downloaded on this computer. Click one to launch, update, or inspect releases.",
            apps,
            "Your library is empty",
            "Go to Find Apps and download an app to add it here.",
            mode="my",
        )

    def render_publish_apps(self) -> None:
        self.content.columnconfigure(0, weight=1)
        self.content.rowconfigure(0, weight=1)
        panel = self.portal_panel(self.content)
        panel.grid(row=0, column=0, sticky="nsew")
        panel.columnconfigure(0, weight=1)
        panel.rowconfigure(0, weight=1)

        _canvas, inner = self.scroll_area(panel, row=0)
        inner.columnconfigure(0, weight=1)
        page = tk.Frame(inner, bg=COLORS["panel"])
        page.grid(row=0, column=0, sticky="new", padx=52, pady=28)
        page.columnconfigure(0, weight=1)

        tk.Label(
            page,
            text="Publish Apps",
            bg=COLORS["panel"],
            fg=COLORS["text"],
            font=(FONT_FAMILY, 24, "bold"),
        ).grid(row=0, column=0, sticky="w")
        tk.Label(
            page,
            text=(
                "Create a catalog entry or publish a new approved release into the "
                "shared hub folder."
            ),
            bg=COLORS["panel"],
            fg=COLORS["muted"],
            font=(FONT_FAMILY, 10),
        ).grid(row=1, column=0, sticky="w", pady=(4, 18))

        form = tk.Frame(
            page,
            bg=COLORS["panel_alt"],
            highlightbackground=COLORS["border"],
            highlightthickness=1,
            padx=18,
            pady=16,
        )
        form.grid(row=2, column=0, sticky="ew")
        form.columnconfigure(1, weight=1)
        form.columnconfigure(3, weight=1)

        self.field_label(form, "Action").grid(row=0, column=0, sticky="w", pady=6)
        mode_box = ttk.Combobox(
            form,
            textvariable=self.publish_mode_text,
            values=(
                "Update existing app",
                "Create new app",
                "Change icon only",
                "Edit description only",
            ),
            state="readonly",
            style="Dark.TCombobox",
            width=24,
        )
        mode_box.grid(row=0, column=1, sticky="w", pady=6, padx=(10, 18))
        mode_box.bind("<<ComboboxSelected>>", lambda _event: self.render_current_view())

        app_values = [f"{app.name} [{app.app_id}]" for app in self.catalog.apps]
        if not self.publish_app_id_text.get() and self.catalog.apps:
            self.publish_app_id_text.set(app_values[0])
        publish_mode = self.publish_mode_text.get().lower()
        is_create = publish_mode.startswith("create")
        is_icon_only = publish_mode.startswith("change icon")
        is_description_only = publish_mode.startswith("edit description")
        self.publish_description_editor = None
        self.publish_release_notes_editor = None
        if is_create:
            self.field_label(form, "New app name").grid(row=1, column=0, sticky="w", pady=6)
            ttk.Entry(
                form,
                textvariable=self.publish_new_name_text,
                style="Dark.TEntry",
            ).grid(row=1, column=1, sticky="ew", pady=6, padx=(10, 18))
            self.field_label(form, "Optional app ID").grid(row=1, column=2, sticky="w", pady=6)
            ttk.Entry(
                form,
                textvariable=self.publish_new_id_text,
                style="Dark.TEntry",
            ).grid(row=1, column=3, sticky="ew", pady=6, padx=(10, 0))
        else:
            self.field_label(form, "Existing app").grid(row=1, column=0, sticky="w", pady=6)
            app_box = ttk.Combobox(
                form,
                textvariable=self.publish_app_id_text,
                values=app_values,
                state="readonly",
                style="Dark.TCombobox",
            )
            app_box.grid(row=1, column=1, columnspan=3, sticky="ew", pady=6, padx=(10, 0))
            app_box.bind("<<ComboboxSelected>>", lambda _event: self.render_current_view())

        if is_icon_only:
            self.field_label(form, "New icon (.png or .ico)").grid(row=2, column=0, sticky="w", pady=6)
            icon_row = tk.Frame(form, bg=COLORS["panel_alt"])
            icon_row.grid(row=2, column=1, columnspan=3, sticky="ew", pady=6, padx=(10, 0))
            icon_row.columnconfigure(0, weight=1)
            ttk.Entry(
                icon_row,
                textvariable=self.publish_icon_text,
                style="Dark.TEntry",
            ).grid(row=0, column=0, sticky="ew", padx=(0, 8))
            self.portal_button(
                icon_row,
                "Browse",
                self.browse_publish_icon,
                compact=True,
                subtle=True,
            ).grid(row=0, column=1)

            footer = tk.Frame(form, bg=COLORS["panel_alt"])
            footer.grid(row=3, column=1, columnspan=3, sticky="ew", padx=(10, 0), pady=(12, 0))
            footer.columnconfigure(0, weight=1)
            tk.Label(
                footer,
                textvariable=self.publish_status_text,
                bg=COLORS["panel_alt"],
                fg=COLORS["muted"],
                font=(FONT_FAMILY, 9),
                wraplength=720,
                justify="left",
            ).grid(row=0, column=0, sticky="w")
            self.portal_button(
                footer,
                "Change Icon",
                self.publish_from_form,
                accent=True,
            ).grid(row=0, column=1, sticky="e", padx=(18, 0))
            return

        if is_description_only:
            tk.Label(
                form,
                text="Description",
                bg=COLORS["panel_alt"],
                fg=COLORS["text"],
                font=(FONT_FAMILY, 9, "bold"),
            ).grid(row=2, column=0, sticky="nw", pady=(12, 6))
            self.publish_description_editor = tk.Text(
                form,
                height=8,
                wrap="word",
                bg="#171a27",
                fg=COLORS["text"],
                insertbackground=COLORS["text"],
                relief="flat",
                font=(FONT_FAMILY, 10),
                padx=10,
                pady=8,
            )
            self.publish_description_editor.grid(
                row=2,
                column=1,
                columnspan=3,
                sticky="ew",
                pady=(12, 6),
                padx=(10, 0),
            )
            selected_app = self.app_rows.get(self.publish_selected_existing_app_id())
            if selected_app is not None:
                self.publish_description_editor.insert("1.0", selected_app.description or "")
            footer = tk.Frame(form, bg=COLORS["panel_alt"])
            footer.grid(row=3, column=1, columnspan=3, sticky="ew", padx=(10, 0), pady=(12, 0))
            footer.columnconfigure(0, weight=1)
            tk.Label(
                footer,
                textvariable=self.publish_status_text,
                bg=COLORS["panel_alt"],
                fg=COLORS["muted"],
                font=(FONT_FAMILY, 9),
                wraplength=720,
                justify="left",
            ).grid(row=0, column=0, sticky="w")
            self.portal_button(
                footer,
                "Save Description",
                self.publish_from_form,
                accent=True,
            ).grid(row=0, column=1, sticky="e", padx=(18, 0))
            return

        self.field_label(form, "Version").grid(row=2, column=0, sticky="w", pady=6)
        ttk.Entry(
            form,
            textvariable=self.publish_version_text,
            style="Dark.TEntry",
        ).grid(row=2, column=1, sticky="ew", pady=6, padx=(10, 18))
        self.field_label(form, "Update name").grid(row=2, column=2, sticky="w", pady=6)
        ttk.Entry(
            form,
            textvariable=self.publish_release_name_text,
            style="Dark.TEntry",
        ).grid(row=2, column=3, sticky="ew", pady=6, padx=(10, 0))

        self.field_label(form, "Executable name").grid(row=3, column=0, sticky="w", pady=6)
        ttk.Entry(
            form,
            textvariable=self.publish_executable_text,
            style="Dark.TEntry",
        ).grid(row=3, column=1, sticky="ew", pady=6, padx=(10, 18))
        self.field_label(form, "Icon file").grid(row=3, column=2, sticky="w", pady=6)
        icon_row = tk.Frame(form, bg=COLORS["panel_alt"])
        icon_row.grid(row=3, column=3, sticky="ew", pady=6, padx=(10, 0))
        icon_row.columnconfigure(0, weight=1)
        ttk.Entry(
            icon_row,
            textvariable=self.publish_icon_text,
            style="Dark.TEntry",
        ).grid(row=0, column=0, sticky="ew", padx=(0, 8))
        self.portal_button(
            icon_row,
            "Browse",
            self.browse_publish_icon,
            compact=True,
            subtle=True,
        ).grid(row=0, column=1)

        self.field_label(form, "Package").grid(row=4, column=0, sticky="w", pady=6)
        package_row = tk.Frame(form, bg=COLORS["panel_alt"])
        package_row.grid(row=4, column=1, columnspan=3, sticky="ew", pady=6, padx=(10, 0))
        package_row.columnconfigure(0, weight=1)
        ttk.Entry(
            package_row,
            textvariable=self.publish_package_text,
            style="Dark.TEntry",
        ).grid(row=0, column=0, sticky="ew", padx=(0, 8))
        self.portal_button(
            package_row,
            "File",
            self.browse_publish_package_file,
            compact=True,
            subtle=True,
        ).grid(row=0, column=1, padx=(0, 6))
        self.portal_button(
            package_row,
            "Folder",
            self.browse_publish_package_folder,
            compact=True,
            subtle=True,
        ).grid(row=0, column=2)

        next_row = 5
        if is_create:
            tk.Label(
                form,
                text="App description",
                bg=COLORS["panel_alt"],
                fg=COLORS["text"],
                font=(FONT_FAMILY, 9, "bold"),
            ).grid(row=next_row, column=0, sticky="nw", pady=(12, 6))
            self.publish_description_editor = tk.Text(
                form,
                height=4,
                wrap="word",
                bg="#171a27",
                fg=COLORS["text"],
                insertbackground=COLORS["text"],
                relief="flat",
                font=(FONT_FAMILY, 10),
                padx=10,
                pady=8,
            )
            self.publish_description_editor.grid(
                row=next_row,
                column=1,
                columnspan=3,
                sticky="ew",
                pady=(12, 6),
                padx=(10, 0),
            )
            next_row += 1

        tk.Label(
            form,
            text="Version updates",
            bg=COLORS["panel_alt"],
            fg=COLORS["text"],
            font=(FONT_FAMILY, 9, "bold"),
        ).grid(row=next_row, column=0, sticky="nw", pady=(12, 6))
        self.publish_release_notes_editor = tk.Text(
            form,
            height=7,
            wrap="word",
            bg="#171a27",
            fg=COLORS["text"],
            insertbackground=COLORS["text"],
            relief="flat",
            font=(FONT_FAMILY, 10),
            padx=10,
            pady=8,
        )
        self.publish_release_notes_editor.grid(
            row=next_row,
            column=1,
            columnspan=3,
            sticky="ew",
            pady=(12, 6),
            padx=(10, 0),
        )
        next_row += 1

        self.field_label(form, "Update image").grid(row=next_row, column=0, sticky="w", pady=6)
        update_image_row = tk.Frame(form, bg=COLORS["panel_alt"])
        update_image_row.grid(row=next_row, column=1, columnspan=3, sticky="ew", pady=6, padx=(10, 0))
        update_image_row.columnconfigure(0, weight=1)
        ttk.Entry(
            update_image_row,
            textvariable=self.publish_release_image_text,
            style="Dark.TEntry",
        ).grid(row=0, column=0, sticky="ew", padx=(0, 8))
        self.portal_button(
            update_image_row,
            "Browse",
            self.browse_publish_release_image,
            compact=True,
            subtle=True,
        ).grid(row=0, column=1)
        next_row += 1

        footer = tk.Frame(form, bg=COLORS["panel_alt"])
        footer.grid(row=next_row, column=1, columnspan=3, sticky="ew", padx=(10, 0), pady=(12, 0))
        footer.columnconfigure(0, weight=1)
        tk.Label(
            footer,
            textvariable=self.publish_status_text,
            bg=COLORS["panel_alt"],
            fg=COLORS["muted"],
            font=(FONT_FAMILY, 9),
            wraplength=720,
            justify="left",
        ).grid(row=0, column=0, sticky="w")
        self.portal_button(
            footer,
            "Publish to Shared Hub",
            self.publish_from_form,
            accent=True,
        ).grid(row=0, column=1, sticky="e", padx=(18, 0))

    def render_update_guide(self) -> None:
        self.content.columnconfigure(0, weight=1)
        self.content.rowconfigure(0, weight=1)
        panel = self.portal_panel(self.content)
        panel.grid(row=0, column=0, sticky="nsew")
        panel.columnconfigure(0, weight=1)
        panel.rowconfigure(0, weight=1)

        _canvas, inner = self.scroll_area(panel, row=0)
        inner.columnconfigure(0, weight=1)
        page = tk.Frame(inner, bg=COLORS["panel"])
        page.grid(row=0, column=0, sticky="new", padx=58, pady=28)
        page.columnconfigure(0, weight=1)
        tk.Label(
            page,
            text="Update Guide",
            bg=COLORS["panel"],
            fg=COLORS["text"],
            font=(FONT_FAMILY, 24, "bold"),
        ).grid(row=0, column=0, sticky="w")
        guide = (
            "How publishing works\n\n"
            "1. Put the company-shared hub folder in OneDrive or SharePoint sync. It "
            "must contain catalog.json and usually contains an Apps folder.\n\n"
            "2. To create a new app, choose Create new app in Publish Apps. Give it a "
            "name, version, optional PNG/ICO icon, app description, executable name, "
            "version update notes, optional update image, and either a .zip, .exe, "
            "or folder. The hub creates Apps/<app>/Releases, copies or zips the "
            "package, writes a SHA-256 hash, and adds the app to catalog.json.\n\n"
            "3. To update an existing app, choose Update existing app, select the app, "
            "enter the new version and update name, write the version update notes, "
            "optionally attach a .png/.jpg/.gif/.ico update image, then provide the "
            "new package. The hub adds or replaces that release, marks it allowed, "
            "makes it the default version, and shows the notes/image as a read-only "
            "update card on the app page.\n\n"
            "4. To change only an app icon, choose Change icon only, select the app, "
            "and pick a .png or .ico file. This copies the icon into the app folder and "
            "updates catalog.json without changing releases or latest.json.\n\n"
            "5. To edit the general app description, choose Edit description only. "
            "That description is the app's store/library blurb; release-specific "
            "changes belong in Version updates when publishing a release.\n\n"
            "6. Employee machines read catalog.json from the shared folder. Downloading "
            "installs the selected release into the user's local app-data folder, then "
            "the hub launches that local copy. Deleting an app only removes the local "
            "installed copy from that computer.\n\n"
            "7. Desktop app shortcuts should point back through the hub. That keeps the "
            "Desktop clean and lets the hub decide where the current local executable is.\n\n"
            "8. Keep company-private release files in the shared hub folder. The public "
            "source repository should stay generic."
        )
        text = tk.Text(
            page,
            height=24,
            wrap="word",
            bg=COLORS["panel_alt"],
            fg=COLORS["text"],
            insertbackground=COLORS["text"],
            relief="flat",
            font=(FONT_FAMILY, 11),
            padx=18,
            pady=16,
        )
        text.grid(row=1, column=0, sticky="ew", pady=(18, 0))
        text.insert("1.0", guide)
        text.configure(state="disabled")

    def field_label(self, parent: tk.Widget, text: str) -> tk.Label:
        return tk.Label(
            parent,
            text=text,
            bg=COLORS["panel_alt"],
            fg=COLORS["text"],
            font=(FONT_FAMILY, 9, "bold"),
        )

    def browse_publish_package_file(self) -> None:
        path = filedialog.askopenfilename(
            title="Choose app release package",
            filetypes=(
                ("App packages", "*.zip *.exe"),
                ("ZIP files", "*.zip"),
                ("Executable files", "*.exe"),
                ("All files", "*.*"),
            ),
        )
        if path:
            self.publish_package_text.set(path)

    def browse_publish_package_folder(self) -> None:
        path = filedialog.askdirectory(title="Choose folder to package")
        if path:
            self.publish_package_text.set(path)

    def browse_publish_icon(self) -> None:
        path = filedialog.askopenfilename(
            title="Choose app icon",
            filetypes=(
                ("App icon files", "*.png *.ico"),
                ("PNG files", "*.png"),
                ("ICO files", "*.ico"),
                ("All files", "*.*"),
            ),
        )
        if path:
            self.publish_icon_text.set(path)

    def browse_publish_release_image(self) -> None:
        path = filedialog.askopenfilename(
            title="Choose update image",
            filetypes=(
                ("Update images", "*.png *.jpg *.jpeg *.gif *.ico"),
                ("PNG files", "*.png"),
                ("JPEG files", "*.jpg *.jpeg"),
                ("GIF files", "*.gif"),
                ("ICO files", "*.ico"),
                ("All files", "*.*"),
            ),
        )
        if path:
            self.publish_release_image_text.set(path)

    def publish_selected_existing_app_id(self) -> str:
        value = self.publish_app_id_text.get().strip()
        if value.endswith("]") and "[" in value:
            return value.rsplit("[", 1)[-1].rstrip("]").strip()
        return value

    def publish_from_form(self) -> None:
        if self.hub_folder is None:
            messagebox.showinfo(APP_NAME, "Choose a hub folder before publishing.")
            return
        mode_text = self.publish_mode_text.get().lower()
        if mode_text.startswith("edit description"):
            editor = getattr(self, "publish_description_editor", None)
            description = editor.get("1.0", "end").strip() if editor is not None else ""
            app_id = self.publish_selected_existing_app_id()
            if not app_id:
                messagebox.showinfo(APP_NAME, "Choose an existing app before editing its description.")
                return
            try:
                update_catalog_app_fields(self.hub_folder, app_id, {"description": description})
            except Exception as exc:
                self.publish_status_text.set("Description save failed.")
                messagebox.showerror(APP_NAME, f"Could not save description:\n\n{exc}")
                return
            self.publish_status_text.set(f"Saved description for {app_id}. Catalog refreshed.")
            self.refresh_catalog()
            self.selected_app_id = app_id
            self.detail_back_view = "publish"
            self.current_view = "detail"
            self.render_current_view()
            return
        icon_text = self.publish_icon_text.get().strip()
        if mode_text.startswith("change icon"):
            if not icon_text:
                messagebox.showinfo(APP_NAME, "Choose a .png or .ico file before changing the app icon.")
                return
            try:
                published_app_id = update_app_icon_only(
                    self.hub_folder,
                    self.publish_selected_existing_app_id(),
                    Path(icon_text),
                )
            except Exception as exc:
                self.publish_status_text.set("Icon update failed.")
                messagebox.showerror(APP_NAME, f"Could not change app icon:\n\n{exc}")
                return
            self.icon_images.clear()
            self.publish_status_text.set(f"Changed icon for {published_app_id}. Catalog refreshed.")
            self.refresh_catalog()
            self.selected_app_id = published_app_id
            self.detail_back_view = "publish"
            self.current_view = "detail"
            self.render_current_view()
            return

        package_text = self.publish_package_text.get().strip()
        if not package_text:
            messagebox.showinfo(APP_NAME, "Choose a .zip, .exe, or folder to publish.")
            return
        description = ""
        editor = getattr(self, "publish_description_editor", None)
        if editor is not None:
            description = editor.get("1.0", "end").strip()
        release_notes = ""
        release_notes_editor = getattr(self, "publish_release_notes_editor", None)
        if release_notes_editor is not None:
            release_notes = release_notes_editor.get("1.0", "end").strip()
        release_image_text = self.publish_release_image_text.get().strip()
        try:
            published_app_id = publish_app_package(
                self.hub_folder,
                mode=self.publish_mode_text.get(),
                existing_app_id=self.publish_selected_existing_app_id(),
                app_name=self.publish_new_name_text.get(),
                app_id=self.publish_new_id_text.get(),
                description=description,
                version=self.publish_version_text.get(),
                release_name=self.publish_release_name_text.get(),
                executable_name=self.publish_executable_text.get(),
                package_input=Path(package_text),
                icon_input=Path(icon_text) if icon_text else None,
                release_description=release_notes,
                release_image_input=Path(release_image_text) if release_image_text else None,
            )
        except Exception as exc:
            self.publish_status_text.set("Publish failed.")
            messagebox.showerror(APP_NAME, f"Could not publish app package:\n\n{exc}")
            return
        self.publish_status_text.set(f"Published {published_app_id}. Catalog refreshed.")
        self.refresh_catalog()
        self.selected_app_id = published_app_id
        self.detail_back_view = "publish"

    def save_github_update_preference(self) -> None:
        save_github_update_settings(
            self.github_updates_enabled.get(),
            self.github_release_url_text.get(),
        )
        self.download_text.set("Hub update settings saved.")

    def check_github_updates_on_startup(self) -> None:
        if self.github_updates_enabled.get():
            self.start_github_update_thread(show_no_update=False)

    def check_github_updates_now(self) -> None:
        self.save_github_update_preference()
        self.download_text.set("Checking GitHub for hub updates...")
        self.start_github_update_thread(show_no_update=True)

    def start_github_update_thread(self, *, show_no_update: bool) -> None:
        api_url = self.github_release_url_text.get().strip() or DEFAULT_GITHUB_RELEASES_API_URL

        def worker() -> None:
            release: dict[str, str] | None = None
            error: Exception | None = None
            try:
                release = fetch_latest_github_release(api_url)
            except Exception as exc:
                error = exc
            self.after(
                0,
                lambda: self.handle_github_update_result(
                    release,
                    error,
                    show_no_update=show_no_update,
                ),
            )

        threading.Thread(target=worker, daemon=True).start()

    def handle_github_update_result(
        self,
        release: dict[str, str] | None,
        error: Exception | None,
        *,
        show_no_update: bool,
    ) -> None:
        if error is not None:
            if show_no_update:
                messagebox.showerror(
                    APP_NAME,
                    "Could not check GitHub releases.\n\n"
                    f"{error}\n\n"
                    "This is not the same as being up to date. It usually means the URL "
                    "is wrong, the repo is private/inaccessible, or no GitHub release has "
                    "been published yet.",
                )
            else:
                self.download_text.set(
                    "GitHub hub update check failed. Check the releases URL in Settings."
                )
            return
        if release is None:
            return
        latest = release["tag"]
        if not is_newer_version(latest, APP_VERSION):
            self.available_hub_release_url = ""
            self.available_hub_release_version = ""
            self.available_hub_release_asset_url = ""
            self.available_hub_release_asset_name = ""
            self.hub_update_button.grid_remove()
            self.download_text.set(f"Hub is up to date. Current version: {APP_VERSION}.")
            if show_no_update:
                messagebox.showinfo(APP_NAME, f"Hub is up to date.\n\nCurrent: {APP_VERSION}")
            return
        self.available_hub_release_version = latest
        self.available_hub_release_url = release.get("url", "") or "https://github.com/"
        self.available_hub_release_asset_url = release.get("asset_url", "")
        self.available_hub_release_asset_name = release.get("asset_name", "")
        self.hub_update_button.grid()
        self.download_text.set(f"Hub update available: {APP_VERSION} -> {latest}")
        self.set_downloads_bar_bg(COLORS["download_flash"])
        if show_no_update or not app_data_settings().get(f"seen_hub_release_{latest}", False):
            if messagebox.askyesno(
                APP_NAME,
                f"A new {APP_NAME} release is available.\n\n"
                f"Current: {APP_VERSION}\nLatest: {latest}\n\n"
                "Update now?",
            ):
                self.open_available_hub_update()
            settings = app_data_settings()
            settings[f"seen_hub_release_{latest}"] = True
            save_app_data_settings(settings)

    def open_available_hub_update(self) -> None:
        if not self.available_hub_release_version:
            self.check_github_updates_now()
            return
        if not getattr(sys, "frozen", False):
            if self.available_hub_release_url:
                webbrowser.open(self.available_hub_release_url)
            messagebox.showinfo(
                APP_NAME,
                "Hub self-update is available from the packaged EXE.\n\n"
                "Because this copy is running from source, I opened the GitHub release page instead.",
            )
            return
        if not self.available_hub_release_asset_url:
            messagebox.showinfo(
                APP_NAME,
                "GitHub found a newer release, but no release ZIP asset was attached.\n\n"
                "Open the release page and attach a packaged hub ZIP to enable in-app updating.",
            )
            webbrowser.open(self.available_hub_release_url)
            return
        if not messagebox.askyesno(
            APP_NAME,
            f"Update {APP_NAME} from {APP_VERSION} to {self.available_hub_release_version}?\n\n"
            "The hub will close, copy the new files into this install folder, and reopen.",
        ):
            return
        self.download_progress.set(12)
        self.download_text.set(
            f"Downloading {APP_NAME} {self.available_hub_release_version}..."
        )
        self.pulse_downloads_bar()

        def worker() -> None:
            error: Exception | None = None
            zip_path = (
                APP_DATA_FOLDER
                / "HubUpdates"
                / (self.available_hub_release_asset_name or f"{APP_NAME} {self.available_hub_release_version}.zip")
            )
            try:
                download_url_to_file(self.available_hub_release_asset_url, zip_path)
            except Exception as exc:
                error = exc
            self.after(0, lambda: self.finish_hub_self_update_download(zip_path, error))

        threading.Thread(target=worker, daemon=True).start()

    def finish_hub_self_update_download(self, zip_path: Path, error: Exception | None) -> None:
        if error is not None:
            self.download_progress.set(0)
            self.download_text.set("Hub update download failed.")
            messagebox.showerror(APP_NAME, f"Could not download hub update:\n\n{error}")
            return
        try:
            self.download_progress.set(86)
            self.download_text.set("Installing hub update and reopening...")
            validate_zip_member_paths(zip_path)
            start_hub_self_update(zip_path)
        except Exception as exc:
            self.download_progress.set(0)
            self.download_text.set("Hub update install failed.")
            messagebox.showerror(APP_NAME, f"Could not start hub self-update:\n\n{exc}")
            return
        self.after(250, self.destroy)

    def render_settings(self) -> None:
        self.content.columnconfigure(0, weight=1)
        self.content.rowconfigure(0, weight=1)
        panel = self.portal_panel(self.content)
        panel.grid(row=0, column=0, sticky="nsew")
        panel.columnconfigure(0, weight=1)
        panel.rowconfigure(0, weight=1)

        _canvas, inner = self.scroll_area(panel, row=0)
        inner.columnconfigure(0, weight=1)
        page = tk.Frame(inner, bg=COLORS["panel"])
        page.grid(row=0, column=0, sticky="new", padx=42, pady=28)
        page.columnconfigure(0, weight=1)

        tk.Label(
            page,
            text="Settings",
            bg=COLORS["panel"],
            fg=COLORS["text"],
            font=(FONT_FAMILY, 24, "bold"),
        ).grid(row=0, column=0, sticky="w")
        tk.Label(
            page,
            text="Company folder, catalog refresh, and local hub preferences.",
            bg=COLORS["panel"],
            fg=COLORS["muted"],
            font=(FONT_FAMILY, 10),
        ).grid(row=1, column=0, sticky="w", pady=(4, 24))

        folder_box = tk.Frame(
            page,
            bg=COLORS["panel_alt"],
            highlightbackground=COLORS["border"],
            highlightthickness=1,
            padx=18,
            pady=16,
        )
        folder_box.grid(row=2, column=0, sticky="ew")
        folder_box.columnconfigure(1, weight=1)
        tk.Label(
            folder_box,
            text="Hub Folder",
            bg=COLORS["panel_alt"],
            fg=COLORS["text"],
            font=(FONT_FAMILY, 12, "bold"),
        ).grid(row=0, column=0, columnspan=4, sticky="w", pady=(0, 12))
        tk.Label(
            folder_box,
            text="Path",
            bg=COLORS["panel_alt"],
            fg=COLORS["muted"],
            font=(FONT_FAMILY, 9, "bold"),
        ).grid(row=1, column=0, sticky="w", padx=(0, 10))
        self.path_entry = ttk.Entry(folder_box, textvariable=self.path_text, style="Dark.TEntry")
        self.path_entry.grid(row=1, column=1, sticky="ew", padx=(0, 10))
        self.portal_button(folder_box, "Browse", self.browse_hub_folder, compact=True).grid(
            row=1, column=2, padx=(0, 8)
        )
        self.portal_button(folder_box, "Refresh", self.refresh_catalog, compact=True).grid(
            row=1, column=3
        )
        tk.Label(
            folder_box,
            textvariable=self.status_text,
            bg=COLORS["panel_alt"],
            fg=COLORS["muted"],
            font=(FONT_FAMILY, 9),
        ).grid(row=2, column=1, columnspan=3, sticky="w", pady=(10, 0))

        note = (
            "Once a valid hub folder is confirmed, this computer reuses it on launch. "
            "Other employees choose or auto-discover their own local sync path."
        )
        tk.Label(
            folder_box,
            text=note,
            bg=COLORS["panel_alt"],
            fg=COLORS["muted"],
            font=(FONT_FAMILY, 9),
            wraplength=900,
            justify="left",
        ).grid(row=3, column=1, columnspan=3, sticky="w", pady=(12, 0))

        shortcut_box = tk.Frame(
            page,
            bg=COLORS["panel_alt"],
            highlightbackground=COLORS["border"],
            highlightthickness=1,
            padx=18,
            pady=16,
        )
        shortcut_box.grid(row=3, column=0, sticky="ew", pady=(18, 0))
        shortcut_box.columnconfigure(0, weight=1)
        tk.Label(
            shortcut_box,
            text="Desktop Shortcut",
            bg=COLORS["panel_alt"],
            fg=COLORS["text"],
            font=(FONT_FAMILY, 12, "bold"),
        ).grid(row=0, column=0, sticky="w")
        tk.Label(
            shortcut_box,
            text=(
                "Creates a Desktop .lnk that points to this app. The app files stay in their "
                "install folder, which keeps future updates away from the Desktop."
            ),
            bg=COLORS["panel_alt"],
            fg=COLORS["muted"],
            font=(FONT_FAMILY, 9),
            wraplength=900,
            justify="left",
        ).grid(row=1, column=0, sticky="w", pady=(6, 0))
        self.portal_button(
            shortcut_box,
            "Create Desktop Shortcut",
            self.create_desktop_shortcut,
            compact=True,
            accent=True,
        ).grid(row=0, column=1, rowspan=2, sticky="e", padx=(18, 0))

        update_box = tk.Frame(
            page,
            bg=COLORS["panel_alt"],
            highlightbackground=COLORS["border"],
            highlightthickness=1,
            padx=18,
            pady=16,
        )
        update_box.grid(row=4, column=0, sticky="ew", pady=(18, 0))
        update_box.columnconfigure(1, weight=1)
        tk.Label(
            update_box,
            text="Hub Updates",
            bg=COLORS["panel_alt"],
            fg=COLORS["text"],
            font=(FONT_FAMILY, 12, "bold"),
        ).grid(row=0, column=0, columnspan=3, sticky="w", pady=(0, 10))
        tk.Checkbutton(
            update_box,
            text="Check public GitHub releases on startup",
            variable=self.github_updates_enabled,
            command=self.save_github_update_preference,
            bg=COLORS["panel_alt"],
            fg=COLORS["text"],
            selectcolor=COLORS["panel"],
            activebackground=COLORS["panel_alt"],
            activeforeground=COLORS["text"],
            font=(FONT_FAMILY, 9),
        ).grid(row=1, column=0, columnspan=3, sticky="w")
        tk.Label(
            update_box,
            text="GitHub releases page/API",
            bg=COLORS["panel_alt"],
            fg=COLORS["muted"],
            font=(FONT_FAMILY, 9, "bold"),
        ).grid(row=2, column=0, sticky="w", pady=(12, 0), padx=(0, 10))
        ttk.Entry(
            update_box,
            textvariable=self.github_release_url_text,
            style="Dark.TEntry",
        ).grid(row=2, column=1, sticky="ew", pady=(12, 0), padx=(0, 8))
        self.portal_button(
            update_box,
            "Save",
            self.save_github_update_preference,
            compact=True,
            subtle=True,
        ).grid(row=2, column=2, pady=(12, 0), padx=(0, 8))
        self.portal_button(
            update_box,
            "Check Now",
            self.check_github_updates_now,
            compact=True,
            accent=True,
        ).grid(row=2, column=3, pady=(12, 0))

        coder_box = tk.Frame(
            page,
            bg=COLORS["panel_alt"],
            highlightbackground=COLORS["border"],
            highlightthickness=1,
            padx=18,
            pady=16,
        )
        coder_box.grid(row=5, column=0, sticky="ew", pady=(18, 0))
        coder_box.columnconfigure(0, weight=1)
        tk.Label(
            coder_box,
            text="Coder Settings",
            bg=COLORS["panel_alt"],
            fg=COLORS["text"],
            font=(FONT_FAMILY, 12, "bold"),
        ).grid(row=0, column=0, sticky="w")
        tk.Label(
            coder_box,
            text=(
                "These settings are saved only on this computer. Admin mode unlocks "
                "Publish Apps and Update Guide for this device."
            ),
            bg=COLORS["panel_alt"],
            fg=COLORS["muted"],
            font=(FONT_FAMILY, 9),
            wraplength=900,
            justify="left",
        ).grid(row=1, column=0, sticky="w", pady=(6, 0))
        tk.Checkbutton(
            coder_box,
            text="Open Advanced Coder Settings",
            variable=self.coder_settings_open,
            command=self.toggle_coder_settings,
            bg=COLORS["panel_alt"],
            fg=COLORS["text"],
            selectcolor=COLORS["panel"],
            activebackground=COLORS["panel_alt"],
            activeforeground=COLORS["text"],
            font=(FONT_FAMILY, 9),
        ).grid(row=2, column=0, sticky="w", pady=(12, 0))
        if self.coder_settings_open.get():
            tk.Checkbutton(
                coder_box,
                text="Make This Device Admin",
                variable=self.device_admin,
                command=self.save_coder_settings_preference,
                bg=COLORS["panel_alt"],
                fg=COLORS["text"],
                selectcolor=COLORS["panel"],
                activebackground=COLORS["panel_alt"],
                activeforeground=COLORS["text"],
                font=(FONT_FAMILY, 9),
            ).grid(row=3, column=0, sticky="w", pady=(8, 0))

    def toggle_coder_settings(self) -> None:
        save_coder_settings(self.coder_settings_open.get(), self.device_admin.get())
        self.render_current_view()

    def save_coder_settings_preference(self) -> None:
        save_coder_settings(self.coder_settings_open.get(), self.device_admin.get())
        if not self.device_admin.get() and self.current_view in self.admin_nav_views:
            self.current_view = "settings"
        self.paint_nav()
        self.render_current_view()

    def portal_panel(self, parent: tk.Widget) -> tk.Frame:
        return tk.Frame(
            parent,
            bg=COLORS["panel"],
            highlightbackground=COLORS["border"],
            highlightthickness=1,
            padx=16,
            pady=14,
        )

    def build_store_grid_page(
        self,
        parent: tk.Frame,
        title: str,
        subtitle: str,
        apps: list[HubApp],
        empty_title: str,
        empty_detail: str,
        *,
        mode: str,
    ) -> None:
        parent.columnconfigure(0, weight=1)
        parent.rowconfigure(1, weight=1)

        toolbar = tk.Frame(parent, bg=COLORS["panel"])
        toolbar.grid(row=0, column=0, sticky="ew", pady=(0, 10))
        toolbar.columnconfigure(0, weight=1)
        tk.Label(
            toolbar,
            text=subtitle,
            bg=COLORS["panel"],
            fg=COLORS["muted"],
            font=(FONT_FAMILY, 9),
        ).grid(row=0, column=0, sticky="w")

        search_var = self.find_search_text if mode == "find" else self.my_search_text

        _canvas, inner = self.scroll_area(parent, row=1)

        def repopulate(_event: object | None = None) -> None:
            self.populate_store_grid(
                inner,
                self.filter_apps(apps, search_var.get()),
                empty_title,
                empty_detail,
                mode=mode,
            )

        repopulate()

    def filter_apps(self, apps: list[HubApp], search: str) -> list[HubApp]:
        needle = search.strip().lower()
        if not needle:
            return apps
        filtered: list[HubApp] = []
        for app in apps:
            haystack = " ".join(
                [
                    app.name,
                    app.app_id,
                    app.description,
                    app.default_version,
                    app.executable_name,
                ]
            ).lower()
            if needle in haystack:
                filtered.append(app)
        return filtered

    def populate_store_grid(
        self,
        parent: tk.Widget,
        apps: list[HubApp],
        empty_title: str,
        empty_detail: str,
        *,
        mode: str,
    ) -> None:
        for child in parent.winfo_children():
            child.destroy()
        self.card_frames.clear()
        for row_index in range(12):
            parent.rowconfigure(row_index, weight=0)
        for column in range(12):
            parent.columnconfigure(column, weight=0, minsize=0)
        if not apps:
            parent.columnconfigure(0, weight=1)
            parent.columnconfigure(1, weight=0)
            parent.columnconfigure(2, weight=1)
            parent.rowconfigure(0, weight=1)
            parent.rowconfigure(2, weight=1)
            self.empty_list_card(parent, empty_title, empty_detail, mode, row=1, column=1)
            return

        parent.columnconfigure(0, weight=1)
        parent.columnconfigure(1, weight=0)
        parent.columnconfigure(2, weight=1)
        grid_holder = tk.Frame(parent, bg=COLORS["panel"])
        grid_holder.grid(row=0, column=1, sticky="n", pady=(22, 0))
        for column in range(5):
            grid_holder.columnconfigure(column, weight=0)
        for index, app in enumerate(apps):
            self.create_store_tile(grid_holder, app, index // 5, index % 5)
        self.paint_cards()

    def create_store_tile(self, parent: tk.Widget, app: HubApp, row: int, column: int) -> None:
        installed = self.is_app_installed(app)
        update_available = self.app_update_available(app)
        tile = tk.Frame(
            parent,
            bg=COLORS["store_card"],
            highlightbackground=COLORS["border"],
            highlightthickness=1,
            padx=14,
            pady=13,
            cursor="hand2",
        )
        tile.grid(row=row, column=column, sticky="nsew", padx=8, pady=8)
        tile.columnconfigure(0, weight=1)
        setattr(tile, "_hub_card_base_bg", COLORS["store_card"])
        self.card_frames[app.app_id] = tile

        icon = self.load_app_icon(app, 96)
        if icon:
            icon_label = tk.Label(tile, image=icon, bg=COLORS["store_card"], height=104)
        else:
            icon_label = tk.Label(
                tile,
                text=self.app_initials(app.name),
                bg=COLORS["purple"],
                fg="#ffffff",
                width=8,
                height=4,
                font=(FONT_FAMILY, 20, "bold"),
            )
        icon_label.grid(row=0, column=0, sticky="n", pady=(0, 10))
        tk.Label(
            tile,
            text=app.name,
            bg=COLORS["store_card"],
            fg=COLORS["text"],
            font=(FONT_FAMILY, 12, "bold"),
            wraplength=190,
            justify="center",
        ).grid(row=1, column=0, sticky="ew")
        tk.Label(
            tile,
            text=self.short_description(app.description, limit=75),
            bg=COLORS["store_card"],
            fg=COLORS["muted"],
            font=(FONT_FAMILY, 9),
            wraplength=190,
            justify="center",
        ).grid(row=2, column=0, sticky="ew", pady=(7, 0))
        status = "Update Available" if update_available else "Installed" if installed else "Available"
        status_color = (
            COLORS["update_green"]
            if update_available
            else COLORS["success"] if installed else COLORS["accent"]
        )
        tk.Label(
            tile,
            text=status,
            bg=COLORS["store_card"],
            fg=status_color,
            font=(FONT_FAMILY, 8, "bold"),
        ).grid(row=3, column=0, sticky="ew", pady=(9, 0))
        self.bind_card_click(tile, app.app_id)

    def build_app_list(
        self,
        parent: tk.Frame,
        title: str,
        subtitle: str,
        apps: list[HubApp],
        empty_title: str,
        empty_detail: str,
        *,
        mode: str,
    ) -> None:
        parent.columnconfigure(0, weight=1)
        parent.rowconfigure(2, weight=1)
        tk.Label(
            parent,
            text=title,
            bg=COLORS["panel"],
            fg=COLORS["text"],
            font=(FONT_FAMILY, 16, "bold"),
        ).grid(row=0, column=0, sticky="w")
        tk.Label(
            parent,
            text=subtitle,
            bg=COLORS["panel"],
            fg=COLORS["muted"],
            font=(FONT_FAMILY, 9),
        ).grid(row=1, column=0, sticky="w", pady=(2, 12))

        _canvas, inner = self.scroll_area(parent)
        if not apps:
            self.empty_list_card(inner, empty_title, empty_detail, mode)
            return
        for row, app in enumerate(apps):
            self.create_app_card(inner, app, row)

    def scroll_area(self, parent: tk.Widget, *, row: int = 2) -> tuple[tk.Canvas, tk.Frame]:
        shell = tk.Frame(parent, bg=COLORS["panel"])
        shell.grid(row=row, column=0, sticky="nsew")
        shell.columnconfigure(0, weight=1)
        shell.rowconfigure(0, weight=1)
        canvas = tk.Canvas(shell, bg=COLORS["panel"], highlightthickness=0, bd=0)
        scroll_canvas = tk.Canvas(
            shell,
            width=12,
            bg=COLORS["panel"],
            highlightthickness=0,
            bd=0,
        )
        canvas.grid(row=0, column=0, sticky="nsew")
        scroll_canvas.grid(row=0, column=1, sticky="ns", padx=(8, 0))
        inner = tk.Frame(canvas, bg=COLORS["panel"])
        window_id = canvas.create_window((0, 0), window=inner, anchor="nw")

        thumb_hovered = False
        thumb_top = 8
        thumb_bottom = 44
        thumb_drag_offset = 18

        def draw_thumb(first: float = 0.0, last: float = 1.0) -> None:
            nonlocal thumb_top, thumb_bottom
            if last - first >= 0.995:
                scroll_canvas.grid_remove()
                return
            if not scroll_canvas.winfo_ismapped():
                scroll_canvas.grid()
            height = max(scroll_canvas.winfo_height(), 1)
            width = max(scroll_canvas.winfo_width(), 1)
            scroll_canvas.delete("thumb")
            scroll_canvas.create_rectangle(
                width // 2 - 2,
                6,
                width // 2 + 2,
                height - 6,
                fill=COLORS["scrollbar_track"],
                outline="",
                tags="thumb",
            )
            top = max(8, int(first * height))
            bottom = min(height - 8, int(last * height))
            if bottom - top < 36:
                bottom = min(height - 8, top + 36)
            thumb_top = top
            thumb_bottom = bottom
            x0 = width // 2 - 4
            x1 = width // 2 + 4
            radius = 4
            thumb_color = (
                COLORS["scrollbar_thumb_hover"] if thumb_hovered else COLORS["scrollbar_thumb"]
            )
            scroll_canvas.create_rectangle(
                x0,
                top + radius,
                x1,
                bottom - radius,
                fill=thumb_color,
                outline="",
                tags="thumb",
            )
            scroll_canvas.create_oval(
                x0,
                top,
                x1,
                top + radius * 2,
                fill=thumb_color,
                outline="",
                tags="thumb",
            )
            scroll_canvas.create_oval(
                x0,
                bottom - radius * 2,
                x1,
                bottom,
                fill=thumb_color,
                outline="",
                tags="thumb",
            )

        def set_scrollbar(first: str, last: str) -> None:
            draw_thumb(float(first), float(last))

        def move_thumb_to(top: float) -> None:
            height = max(scroll_canvas.winfo_height(), 1)
            thumb_height = max(thumb_bottom - thumb_top, 36)
            travel = max(height - 16 - thumb_height, 1)
            top = min(max(top, 8), 8 + travel)
            first, last = canvas.yview()
            visible = max(last - first, 0.0)
            max_fraction = max(1.0 - visible, 0.0)
            canvas.yview_moveto(((top - 8) / travel) * max_fraction)

        def on_scroll_press(event: tk.Event) -> None:
            nonlocal thumb_drag_offset
            if thumb_top <= event.y <= thumb_bottom:
                thumb_drag_offset = event.y - thumb_top
            else:
                thumb_drag_offset = max(18, (thumb_bottom - thumb_top) // 2)
                move_thumb_to(event.y - thumb_drag_offset)

        def on_scroll_drag(event: tk.Event) -> None:
            move_thumb_to(event.y - thumb_drag_offset)

        def on_mousewheel(event: tk.Event) -> None:
            delta = int(-1 * (event.delta / 120)) if event.delta else 0
            canvas.yview_scroll(delta, "units")

        def set_thumb_hover(is_hovered: bool) -> None:
            nonlocal thumb_hovered
            thumb_hovered = is_hovered
            first, last = canvas.yview()
            draw_thumb(first, last)

        def sync_canvas_window() -> None:
            width = max(canvas.winfo_width(), 1)
            viewport_height = max(canvas.winfo_height(), 1)
            requested_height = max(inner.winfo_reqheight(), viewport_height)
            canvas.itemconfigure(window_id, width=width, height=requested_height)
            canvas.configure(scrollregion=canvas.bbox("all"))
            first, last = canvas.yview()
            draw_thumb(first, last)

        canvas.configure(yscrollcommand=set_scrollbar)
        scroll_canvas.bind("<Button-1>", on_scroll_press)
        scroll_canvas.bind("<B1-Motion>", on_scroll_drag)
        scroll_canvas.bind("<Enter>", lambda _event: set_thumb_hover(True))
        scroll_canvas.bind("<Leave>", lambda _event: set_thumb_hover(False))
        canvas.bind("<MouseWheel>", on_mousewheel)
        inner.bind("<MouseWheel>", on_mousewheel)

        def on_inner_configure(_event: tk.Event) -> None:
            sync_canvas_window()

        def on_canvas_configure(event: tk.Event) -> None:
            sync_canvas_window()

        inner.bind("<Configure>", on_inner_configure)
        canvas.bind("<Configure>", on_canvas_configure)
        return canvas, inner

    def empty_list_card(
        self,
        parent: tk.Widget,
        title: str,
        detail: str,
        mode: str,
        *,
        row: int = 0,
        column: int = 0,
    ) -> None:
        card = tk.Frame(
            parent,
            bg=COLORS["card"],
            highlightbackground=COLORS["border"],
            highlightthickness=1,
            padx=34,
            pady=28,
        )
        card.grid(row=row, column=column, sticky="", padx=24, pady=72)
        card.columnconfigure(0, weight=1)
        tk.Label(
            card,
            text=title,
            bg=COLORS["card"],
            fg=COLORS["text"],
            font=(FONT_FAMILY, 16, "bold"),
        ).grid(row=0, column=0, sticky="ew")
        tk.Label(
            card,
            text=detail,
            bg=COLORS["card"],
            fg=COLORS["muted"],
            font=(FONT_FAMILY, 10),
            wraplength=420,
            justify="center",
        ).grid(row=1, column=0, sticky="ew", pady=(12, 0))
        if mode == "my":
            self.portal_button(card, "Find Apps", lambda: self.switch_view("find")).grid(
                row=2, column=0, pady=(20, 0)
            )

    def create_app_card(self, parent: tk.Widget, app: HubApp, row: int) -> None:
        installed = self.is_app_installed(app)
        update_available = self.app_update_available(app)
        card = tk.Frame(
            parent,
            bg=COLORS["card"],
            highlightbackground=COLORS["border"],
            highlightthickness=1,
            padx=12,
            pady=12,
            cursor="hand2",
        )
        card.grid(row=row, column=0, sticky="ew", pady=(0, 10))
        parent.columnconfigure(0, weight=1)
        card.columnconfigure(1, weight=1)
        setattr(card, "_hub_card_base_bg", COLORS["card"])
        self.card_frames[app.app_id] = card

        icon = self.load_app_icon(app, 58)
        if icon:
            icon_label = tk.Label(card, image=icon, bg=COLORS["card"], width=64, height=64)
        else:
            icon_label = tk.Label(
                card,
                text=self.app_initials(app.name),
                bg=COLORS["purple"],
                fg="#ffffff",
                width=6,
                height=3,
                font=(FONT_FAMILY, 14, "bold"),
            )
        icon_label.grid(row=0, column=0, rowspan=3, sticky="nw", padx=(0, 12))
        tk.Label(
            card,
            text=app.name,
            bg=COLORS["card"],
            fg=COLORS["text"],
            font=(FONT_FAMILY, 13, "bold"),
        ).grid(row=0, column=1, sticky="w")
        status = "Update Available" if update_available else self.installed_version_text(app) if installed else "Available"
        status_color = (
            COLORS["update_green"]
            if update_available
            else COLORS["success"] if installed else COLORS["accent"]
        )
        tk.Label(
            card,
            text=status,
            bg=COLORS["card"],
            fg=status_color,
            font=(FONT_FAMILY, 9, "bold"),
        ).grid(row=0, column=2, sticky="e", padx=(8, 0))
        tk.Label(
            card,
            text=self.short_description(app.description, limit=160),
            bg=COLORS["card"],
            fg=COLORS["muted"],
            font=(FONT_FAMILY, 10),
            wraplength=450,
            justify="left",
        ).grid(row=1, column=1, columnspan=2, sticky="w", pady=(6, 0))
        tk.Label(
            card,
            text=f"{app.default_version or '-'}  |  {self.release_status(app)}",
            bg=COLORS["card"],
            fg=COLORS["muted"],
            font=(FONT_FAMILY, 8),
        ).grid(row=2, column=1, sticky="w", pady=(7, 0))
        self.bind_card_click(card, app.app_id)

    def bind_card_click(self, widget: tk.Widget, app_id: str) -> None:
        widget.bind("<Button-1>", lambda _event, item_id=app_id: self.select_app(item_id))
        for child in widget.winfo_children():
            self.bind_card_click(child, app_id)

    def selected_app(self) -> HubApp | None:
        if self.selected_app_id is None:
            return None
        return self.app_rows.get(self.selected_app_id)

    def select_app(self, app_id: str) -> None:
        app = self.app_rows.get(app_id)
        if app is None:
            return
        self.selected_app_id = app_id
        self.detail_version_text.set("")
        if self.current_view in ("find", "my"):
            self.detail_back_view = self.current_view
        self.current_view = "detail"
        self.paint_nav()
        self.render_current_view()

    def paint_cards(self) -> None:
        for app_id, card in self.card_frames.items():
            selected = app_id == self.selected_app_id
            app = self.app_rows.get(app_id)
            update_available = app is not None and self.app_update_available(app)
            base_bg = str(getattr(card, "_hub_card_base_bg", COLORS["card"]))
            bg = COLORS["card_selected"] if selected else base_bg
            if update_available and self.app_update_flash_on:
                border = COLORS["update_green"]
                thickness = 2
            else:
                border = COLORS["accent"] if selected else COLORS["border"]
                thickness = 2 if selected else 1
            card.configure(bg=bg, highlightbackground=border, highlightthickness=thickness)
            self.paint_children(card, bg)

    def paint_children(self, widget: tk.Widget, bg: str) -> None:
        for child in widget.winfo_children():
            if isinstance(child, tk.Label) and child.cget("bg") in (
                COLORS["card"],
                COLORS["card_selected"],
                COLORS["store_card"],
            ):
                child.configure(bg=bg)
            if isinstance(child, tk.Frame):
                child.configure(bg=bg)
                self.paint_children(child, bg)

    def render_app_detail_page(self, app: HubApp) -> None:
        panel = self.portal_panel(self.content)
        panel.grid(row=0, column=0, sticky="nsew")
        panel.columnconfigure(0, weight=1)
        panel.rowconfigure(0, weight=1)

        _canvas, inner = self.scroll_area(panel, row=0)
        inner.columnconfigure(0, weight=1)
        page = tk.Frame(inner, bg=COLORS["panel"])
        page.grid(row=0, column=0, sticky="new", padx=58, pady=(6, 28))
        page.columnconfigure(0, weight=1)

        top_row = tk.Frame(page, bg=COLORS["panel"])
        top_row.grid(row=0, column=0, sticky="ew", pady=(0, 14))
        top_row.columnconfigure(1, weight=1)
        self.portal_button(
            top_row,
            "< Back to My Apps" if self.detail_back_view == "my" else "< Back to Find Apps",
            lambda: self.switch_view(self.detail_back_view),
            compact=True,
            subtle=True,
        ).grid(row=0, column=0, sticky="w", padx=(0, 12))
        tk.Label(
            top_row,
            text="APP PAGE",
            bg=COLORS["panel"],
            fg=COLORS["muted"],
            font=(FONT_FAMILY, 9, "bold"),
        ).grid(row=0, column=1, sticky="e")

        installed = self.is_app_installed(app)
        hero = tk.Frame(
            page,
            bg=COLORS["panel_alt"],
            highlightbackground=COLORS["border"],
            highlightthickness=1,
            padx=26,
            pady=24,
        )
        hero.grid(row=1, column=0, sticky="ew")
        hero.columnconfigure(1, weight=1)

        icon = self.load_app_icon(app, 132)
        if icon:
            icon_label = tk.Label(hero, image=icon, bg=COLORS["panel_alt"], width=144, height=144)
        else:
            icon_label = tk.Label(
                hero,
                text=self.app_initials(app.name),
                bg=COLORS["purple"],
                fg="#ffffff",
                width=9,
                height=5,
                font=(FONT_FAMILY, 24, "bold"),
            )
        icon_label.grid(row=0, column=0, rowspan=3, sticky="nw", padx=(0, 22))
        tk.Label(
            hero,
            text=app.name,
            bg=COLORS["panel_alt"],
            fg=COLORS["text"],
            font=(FONT_FAMILY, 28, "bold"),
        ).grid(row=0, column=1, sticky="w")
        tk.Label(
            hero,
            text=(
                f"{app.app_id}  |  Default {app.default_version or '-'}  |  "
                f"{self.installed_version_text(app)}"
            ),
            bg=COLORS["panel_alt"],
            fg=COLORS["muted"],
            font=(FONT_FAMILY, 10),
        ).grid(row=1, column=1, sticky="w", pady=(6, 0))
        versions = app_release_versions(app)
        selected_version = self.selected_detail_version(app)
        action_stack = tk.Frame(hero, bg=COLORS["panel_alt"])
        action_stack.grid(row=2, column=1, sticky="w", pady=(18, 0))
        self.portal_button(
            action_stack,
            "Run App",
            self.launch_selected_app,
            state="normal" if installed else "disabled",
        ).grid(row=0, column=0, sticky="w", padx=(0, 12))
        tk.Label(
            action_stack,
            text="Version",
            bg=COLORS["panel_alt"],
            fg=COLORS["muted"],
            font=(FONT_FAMILY, 9, "bold"),
        ).grid(row=0, column=1, sticky="w", padx=(0, 8))
        version_box = ttk.Combobox(
            action_stack,
            textvariable=self.detail_version_text,
            values=versions,
            state="readonly" if versions else "disabled",
            style="Dark.TCombobox",
            width=15,
        )
        version_box.grid(row=0, column=2, sticky="w", padx=(0, 12))
        version_box.bind("<<ComboboxSelected>>", lambda _event: self.render_current_view())
        self.portal_button(
            action_stack,
            self.detail_action_text(app, selected_version),
            lambda selected=app: self.queue_download(selected, self.selected_detail_version(selected)),
            accent=True,
            state="normal" if versions else "disabled",
        ).grid(row=0, column=3, sticky="w", padx=(0, 12))
        tk.Checkbutton(
            action_stack,
            text="Create Desktop shortcut after download",
            variable=self.create_shortcut_on_download,
            command=self.save_shortcut_download_preference,
            bg=COLORS["panel_alt"],
            fg=COLORS["muted"],
            selectcolor=COLORS["panel"],
            activebackground=COLORS["panel_alt"],
            activeforeground=COLORS["text"],
            font=(FONT_FAMILY, 9),
        ).grid(row=0, column=4, sticky="w")

        action_row = tk.Frame(page, bg=COLORS["panel"])
        action_row.grid(row=2, column=0, sticky="ew", pady=(14, 0))
        for col in range(3):
            action_row.columnconfigure(col, weight=1)
        self.portal_button(
            action_row,
            "Open Source Folder",
            self.open_selected_source_folder,
        ).grid(row=0, column=0, sticky="ew", padx=(0, 6))
        self.portal_button(
            action_row,
            "Create Shortcut",
            self.create_selected_app_shortcut,
            state="normal" if installed else "disabled",
        ).grid(row=0, column=1, sticky="ew", padx=6)
        self.portal_button(
            action_row,
            "Delete Local Install",
            self.delete_selected_app,
            state="normal" if installed else "disabled",
        ).grid(row=0, column=2, sticky="ew", padx=(6, 0))

        description_panel = tk.Frame(
            page,
            bg=COLORS["panel_alt"],
            highlightbackground=COLORS["border"],
            highlightthickness=1,
            padx=20,
            pady=16,
        )
        description_panel.grid(row=3, column=0, sticky="ew", pady=(14, 14))
        description_panel.columnconfigure(0, weight=1)
        tk.Label(
            description_panel,
            text="Shared Company Description",
            bg=COLORS["panel_alt"],
            fg=COLORS["text"],
            font=(FONT_FAMILY, 12, "bold"),
        ).grid(row=0, column=0, sticky="w")
        tk.Label(
            description_panel,
            text=app.description or "No company description has been added yet.",
            bg="#171a27",
            fg=COLORS["text"],
            font=(FONT_FAMILY, 10),
            wraplength=1120,
            justify="left",
            anchor="nw",
            padx=12,
            pady=10,
        ).grid(row=1, column=0, sticky="ew", pady=(8, 0))

        releases_panel = tk.Frame(page, bg=COLORS["panel"])
        releases_panel.grid(row=4, column=0, sticky="ew", pady=(16, 0))
        releases_panel.columnconfigure(0, weight=1)
        releases_panel.rowconfigure(1, weight=1)
        tk.Label(
            releases_panel,
            text="VERSION UPDATES",
            bg=COLORS["panel"],
            fg=COLORS["text"],
            font=(FONT_FAMILY, 12, "bold"),
        ).grid(row=0, column=0, sticky="w", pady=(0, 6))
        self.render_release_update_cards(releases_panel, app)

    def render_release_update_cards(self, parent: tk.Widget, app: HubApp) -> None:
        releases = sorted_app_releases(app)
        if not releases:
            empty = tk.Frame(
                parent,
                bg=COLORS["panel_alt"],
                highlightbackground=COLORS["border"],
                highlightthickness=1,
                padx=18,
                pady=14,
            )
            empty.grid(row=1, column=0, sticky="ew")
            tk.Label(
                empty,
                text="No approved releases yet.",
                bg=COLORS["panel_alt"],
                fg=COLORS["muted"],
                font=(FONT_FAMILY, 10),
            ).grid(row=0, column=0, sticky="w")
            return
        installed_record = self.install_record_for(app)
        for row, release in enumerate(releases, start=1):
            card = tk.Frame(
                parent,
                bg=COLORS["panel_alt"],
                highlightbackground=COLORS["border"],
                highlightthickness=1,
                padx=16,
                pady=13,
            )
            card.grid(row=row, column=0, sticky="ew", pady=(0, 10))
            card.columnconfigure(1, weight=1)

            media = tk.Frame(card, bg=COLORS["panel_alt"])
            media.grid(row=0, column=0, rowspan=3, sticky="nw", padx=(0, 16))
            image = self.load_release_image(app, release, 150)
            if image:
                tk.Label(
                    media,
                    image=image,
                    bg=COLORS["panel_alt"],
                    width=160,
                    height=96,
                ).grid(row=0, column=0, sticky="nw")

            badge_bg = COLORS["accent"] if release.version == app.default_version else COLORS["panel_high"]
            tk.Label(
                media,
                text=release.version,
                bg=badge_bg,
                fg=COLORS["background"] if release.version == app.default_version else COLORS["text"],
                font=(FONT_FAMILY, 10, "bold"),
                padx=12,
                pady=7,
            ).grid(row=1 if image else 0, column=0, sticky="w", pady=(8 if image else 0, 0))

            title = release.update_name or f"Release {release.version}"
            title_bits = [title]
            if release.date:
                title_bits.append(release.date)
            if release.version == app.default_version:
                title_bits.append("Default")
            if installed_record is not None and installed_record.version == release.version:
                title_bits.append("Installed")
            tk.Label(
                card,
                text="  |  ".join(title_bits),
                bg=COLORS["panel_alt"],
                fg=COLORS["text"],
                font=(FONT_FAMILY, 11, "bold"),
                anchor="w",
            ).grid(row=0, column=1, sticky="ew")
            detail = (
                release.update_description
                or release.notes
                or "No detailed update notes were added for this release."
            )
            tk.Label(
                card,
                text=detail,
                bg=COLORS["panel_alt"],
                fg=COLORS["muted"],
                font=(FONT_FAMILY, 9),
                wraplength=980 if image else 1120,
                justify="left",
                anchor="w",
            ).grid(row=1, column=1, sticky="ew", pady=(6, 0))

    def load_release_image(
        self,
        app: HubApp,
        release: AppRelease,
        max_size: int,
    ) -> tk.PhotoImage | None:
        if self.hub_folder is None:
            return None
        key = f"release:{app.app_id}:{release.version}:{release.update_image}:{max_size}"
        if key in self.icon_images:
            return self.icon_images[key]
        path = resolve_release_update_image_path(self.hub_folder, app, release)
        if path is None:
            return None
        image = load_icon_photo_image(path, max_size)
        if image is None:
            return None
        self.icon_images[key] = image
        return image

    def default_detail_version(self, app: HubApp) -> str:
        return latest_app_version(app) or app.default_version

    def selected_detail_version(self, app: HubApp) -> str:
        versions = app_release_versions(app)
        selected = self.detail_version_text.get().strip()
        if selected in versions:
            return selected
        fallback = self.default_detail_version(app)
        if fallback:
            self.detail_version_text.set(fallback)
        return fallback

    def detail_action_text(self, app: HubApp, selected_version: str) -> str:
        record = self.install_record_for(app)
        if record is None or not Path(record.executable_path).is_file():
            return "Download"
        if selected_version and record.version != selected_version:
            if is_newer_version(selected_version, record.version):
                return "Update"
            return "Change Version"
        return "Update / Repair"

    def queue_download(self, app: HubApp, version: str = "") -> None:
        selected_version = version.strip() or self.default_detail_version(app)
        queued_ids = {(queued.app.app_id, queued.version) for queued in self.download_queue}
        if self.active_download is not None:
            queued_ids.add((self.active_download.app.app_id, self.active_download.version))
        task_key = (app.app_id, selected_version)
        if task_key in queued_ids:
            self.download_text.set(f"{app.name} {selected_version or ''} is already in the update queue.")
            return
        self.download_queue.append(DownloadTask(app=app, version=selected_version))
        self.update_download_status()
        if self.active_download is None:
            self.start_next_download()

    def start_next_download(self) -> None:
        if not self.download_queue:
            self.active_download = None
            self.download_progress.set(0)
            self.update_download_status()
            return
        self.active_download = self.download_queue.pop(0)
        self.download_progress.set(0)
        self.update_download_status()
        self.pulse_downloads_bar()
        self.after(80, self.tick_download)

    def tick_download(self) -> None:
        if self.active_download is None:
            return
        progress = min(self.download_progress.get() + 4, 100)
        self.download_progress.set(progress)
        version = f" {self.active_download.version}" if self.active_download.version else ""
        self.download_text.set(f"Downloading {self.active_download.app.name}{version}... {progress}%")
        if progress >= 100:
            self.finish_active_download()
            return
        self.after(80, self.tick_download)

    def finish_active_download(self) -> None:
        if self.active_download is None:
            return
        finished = self.active_download
        if self.hub_folder is None:
            self.download_text.set("Download failed: no hub folder selected.")
            self.active_download = None
            self.update_download_status()
            self.after(900, self.start_next_download)
            return
        try:
            record = install_app_release(self.hub_folder, finished.app, finished.version)
            save_install_record(record)
            if self.create_shortcut_on_download.get():
                create_app_desktop_shortcut_file(finished.app, record, self.hub_folder)
        except Exception as exc:
            self.download_text.set(f"{finished.app.name} install failed.")
            messagebox.showerror(APP_NAME, f"Could not install {finished.app.name}:\n\n{exc}")
            self.active_download = None
            self.reload_install_state()
            self.update_download_status()
            self.render_current_view()
            self.after(900, self.start_next_download)
            return
        self.reload_install_state()
        self.download_text.set(f"{finished.app.name} {record.version} is installed and ready in My Apps.")
        self.active_download = None
        self.update_download_status()
        self.render_current_view()
        self.after(900, self.start_next_download)

    def update_download_status(self) -> None:
        count = len(self.download_queue) + (1 if self.active_download is not None else 0)
        self.download_queue_text.set(f"Queue: {count}")
        if self.active_download is None and not self.download_queue:
            if not self.download_text.get().endswith("ready in My Apps."):
                self.download_text.set("No active downloads.")
            if not self.available_hub_release_version:
                self.set_downloads_bar_bg(COLORS["download_idle"])

    def pulse_downloads_bar(self) -> None:
        active = self.active_download is not None or bool(self.download_queue)
        if not active:
            self.set_downloads_bar_bg(COLORS["download_idle"])
            return
        self.download_flash_on = not self.download_flash_on
        self.set_downloads_bar_bg(
            COLORS["download_flash"] if self.download_flash_on else COLORS["download_idle"]
        )
        self.after(420, self.pulse_downloads_bar)

    def set_downloads_bar_bg(self, color: str) -> None:
        self.downloads_bar.configure(bg=color)
        for child in self.downloads_bar.winfo_children():
            try:
                child.configure(bg=color)
            except tk.TclError:
                pass

    def load_app_icon(self, app: HubApp, max_size: int) -> tk.PhotoImage | None:
        if self.hub_folder is None:
            return None
        key = f"{app.app_id}:{max_size}"
        if key in self.icon_images:
            return self.icon_images[key]
        path = resolve_app_icon_path(self.hub_folder, app)
        if path is None:
            return None
        image = load_icon_photo_image(path, max_size)
        if image is None:
            return None
        self.icon_images[key] = image
        return image

    def app_initials(self, name: str) -> str:
        parts = [part for part in name.replace("-", " ").split() if part]
        if len(parts) >= 2:
            return (parts[0][0] + parts[1][0]).upper()
        if parts:
            return parts[0][:2].upper()
        return "AP"

    def short_description(self, description: str, limit: int = 130) -> str:
        text = " ".join(description.split()) or "No description yet. Click to edit this app page."
        if len(text) <= limit:
            return text
        return text[: limit - 3].rstrip() + "..."

    def release_status(self, app: HubApp) -> str:
        count = len(app.published_releases)
        if count == 0:
            return "No allowed releases"
        if count == 1:
            return "1 allowed release"
        return f"{count} allowed releases"

    def app_source_folder(self, app: HubApp) -> Path | None:
        if self.hub_folder is None:
            return None
        return resolve_app_source_folder(self.hub_folder, app)

    def open_selected_source_folder(self) -> None:
        app = self.selected_app()
        if app is None:
            return
        source = self.app_source_folder(app)
        if source is None or not source.exists():
            messagebox.showinfo(APP_NAME, "This app does not have a source folder configured yet.")
            return
        open_path(source)

    def install_selected_placeholder(self) -> None:
        app = self.selected_app()
        if app is not None:
            self.queue_download(app)

    def launch_selected_app(self) -> None:
        app = self.selected_app()
        if app is None:
            return
        record = self.install_record_for(app)
        if record is None:
            messagebox.showinfo(APP_NAME, f"{app.name} is not installed on this computer yet.")
            return
        popup: tk.Toplevel | None = None
        try:
            popup = show_status_popup(self, "App Loading", f"Opening {app.name}...")
            self.update()
            launch_install_record(record)
        except Exception as exc:
            if popup is not None:
                popup.destroy()
            messagebox.showerror(APP_NAME, f"Could not launch {app.name}:\n\n{exc}")
            return
        if popup is not None:
            self.after(1400, popup.destroy)

    def launch_selected_placeholder(self) -> None:
        self.launch_selected_app()

    def create_selected_app_shortcut(self) -> None:
        app = self.selected_app()
        if app is None:
            return
        record = self.install_record_for(app)
        if record is None:
            messagebox.showinfo(APP_NAME, f"Download {app.name} before creating a shortcut.")
            return
        try:
            shortcut_path = create_app_desktop_shortcut_file(app, record, self.hub_folder)
        except Exception as exc:
            messagebox.showerror(APP_NAME, f"Could not create app shortcut:\n\n{exc}")
            return
        messagebox.showinfo(APP_NAME, f"Desktop shortcut created:\n\n{shortcut_path}")

    def delete_selected_app(self) -> None:
        app = self.selected_app()
        if app is None:
            return
        if not messagebox.askyesno(
            APP_NAME,
            f"Delete the local installed copy of {app.name} from this computer?\n\n"
            "The shared catalog and releases will not be changed.",
        ):
            return
        try:
            delete_app_install(app)
        except Exception as exc:
            messagebox.showerror(APP_NAME, f"Could not delete {app.name}:\n\n{exc}")
            return
        self.reload_install_state()
        self.download_text.set(f"Deleted local install for {app.name}.")
        self.render_current_view()

    def open_hub_folder(self) -> None:
        if self.hub_folder is None:
            messagebox.showinfo(APP_NAME, "No hub folder selected.")
            return
        open_path(self.hub_folder)

    def open_github_help(self) -> None:
        webbrowser.open("https://github.com/")

    def create_desktop_shortcut(self) -> None:
        try:
            shortcut_path = create_desktop_shortcut_file()
        except Exception as exc:
            messagebox.showerror(APP_NAME, f"Could not create Desktop shortcut:\n\n{exc}")
            return
        messagebox.showinfo(APP_NAME, f"Desktop shortcut created:\n\n{shortcut_path}")


def launch_app_from_cli(app_id: str) -> None:
    root = tk.Tk()
    root.withdraw()
    record = load_install_records().get(app_id)
    if record is None:
        messagebox.showerror(
            APP_NAME,
            f"That app is not installed through {APP_NAME} on this computer:\n\n{app_id}",
        )
        root.destroy()
        return
    app: HubApp | None = None
    hub_folder = load_saved_hub_folder()
    if hub_folder is not None:
        try:
            app = catalog_app_by_id(load_catalog(hub_folder), app_id)
        except Exception:
            app = None
    if app is not None and app_update_available_for_record(app, record):
        latest = latest_app_version(app)
        if messagebox.askyesno(
            APP_NAME,
            f"{app.name} has an update available.\n\n"
            f"Installed: {record.version}\nLatest: {latest}\n\n"
            "Update before launching?",
        ):
            popup = show_status_popup(
                root,
                "Updating",
                f"Updating {app.name} to {latest}...",
            )
            root.update()
            try:
                record = install_app_release(hub_folder, app, latest)
                save_install_record(record)
                create_app_desktop_shortcut_file(app, record, hub_folder)
            except Exception as exc:
                popup.destroy()
                if not messagebox.askyesno(
                    APP_NAME,
                    f"Could not update {app.name}:\n\n{exc}\n\nLaunch the installed version anyway?",
                ):
                    root.destroy()
                    return
            else:
                popup.destroy()
    popup: tk.Toplevel | None = None
    try:
        name = app.name if app is not None else app_id
        popup = show_status_popup(root, "App Loading", f"Opening {name}...")
        root.update()
        launch_install_record(record)
    except Exception as exc:
        if popup is not None:
            popup.destroy()
        messagebox.showerror(APP_NAME, f"Could not launch app:\n\n{exc}")
        root.destroy()
        return
    root.after(1400, root.destroy)
    root.mainloop()


def show_status_popup(root: tk.Tk, title: str, message: str) -> tk.Toplevel:
    popup = tk.Toplevel(root)
    popup.title(title)
    popup.configure(bg=COLORS["panel"])
    popup.resizable(False, False)
    popup.attributes("-topmost", True)
    popup.columnconfigure(0, weight=1)
    tk.Label(
        popup,
        text=message,
        bg=COLORS["panel"],
        fg=COLORS["text"],
        font=(FONT_FAMILY, 11, "bold"),
        padx=26,
        pady=18,
        wraplength=420,
        justify="center",
    ).grid(row=0, column=0, sticky="ew")
    progress = ttk.Progressbar(
        popup,
        mode="indeterminate",
        style="Download.Horizontal.TProgressbar",
        length=320,
    )
    progress.grid(row=1, column=0, sticky="ew", padx=26, pady=(0, 22))
    progress.start(12)
    popup.update_idletasks()
    width = popup.winfo_width()
    height = popup.winfo_height()
    screen_width = popup.winfo_screenwidth()
    screen_height = popup.winfo_screenheight()
    popup.geometry(f"+{(screen_width - width) // 2}+{(screen_height - height) // 2}")
    return popup


def main() -> None:
    if len(sys.argv) >= 3 and sys.argv[1] == "--launch-app":
        launch_app_from_cli(sys.argv[2])
        return
    app = SteamStyleBusinessAppHub()
    app.mainloop()


if __name__ == "__main__":
    main()
