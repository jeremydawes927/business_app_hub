from __future__ import annotations

import json
import os
import subprocess
import sys
import webbrowser
from dataclasses import dataclass
from pathlib import Path
from tkinter import filedialog, messagebox, ttk
import tkinter as tk


APP_NAME = "Business App Hub"
APP_VERSION = "0.1.1"
HUB_FOLDER_NAME = "Business App Hub"
FONT_FAMILY = "Georgia"
APP_DATA_FOLDER = Path(os.environ.get("LOCALAPPDATA", Path.home())) / "Business App Hub"
SETTINGS_FILE = APP_DATA_FOLDER / "settings.json"
CATALOG_FILE_NAME = "catalog.json"
HUB_SETTINGS_FILE_NAME = "hub_settings.json"
APPS_FOLDER_NAME = "Apps"
BUNDLED_HEADER_IMAGE_NAME = "hub_header.png"
IMAGE_EXTENSIONS = (".png", ".gif", ".ppm", ".pgm")
ICON_CANDIDATE_NAMES = (
    "icon.png",
    "app.png",
    "logo.png",
    "tile.png",
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


@dataclass(frozen=True)
class AppRelease:
    version: str
    package: str = ""
    sha256: str = ""
    notes: str = ""
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


def home_relative_suffix(path: Path) -> str:
    normalized = normalize_path(path)
    try:
        return str(normalized.relative_to(Path.home()))
    except ValueError:
        return str(normalized)


def load_hub_settings(folder: Path) -> dict[str, object]:
    settings_path = folder / HUB_SETTINGS_FILE_NAME
    if not settings_path.is_file():
        return {}
    try:
        raw = json.loads(settings_path.read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError):
        return {}
    return raw if isinstance(raw, dict) else {}


def save_company_hub_folder_preference(folder: Path) -> None:
    normalized = normalize_path(folder)
    data = load_hub_settings(normalized)
    data["preferred_hub_folder_suffix"] = home_relative_suffix(normalized)
    data["hub_folder_name"] = HUB_FOLDER_NAME
    (normalized / HUB_SETTINGS_FILE_NAME).write_text(
        json.dumps(data, indent=2),
        encoding="utf-8",
    )


def load_installed_app_ids() -> set[str]:
    installed = app_data_settings().get("installed_apps", [])
    if not isinstance(installed, list):
        return set()
    return {str(app_id).strip() for app_id in installed if str(app_id).strip()}


def save_installed_app_ids(app_ids: set[str]) -> None:
    settings = app_data_settings()
    settings["installed_apps"] = sorted(app_ids)
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


def running_app_shortcut_target() -> tuple[Path, str, Path]:
    if getattr(sys, "frozen", False):
        executable = Path(sys.executable)
        return executable, "", executable.parent
    script = Path(__file__).resolve()
    return Path(sys.executable), f'"{script}"', script.parent.parent


def desktop_shortcut_path() -> Path:
    desktop = Path(os.environ.get("USERPROFILE", str(Path.home()))) / "Desktop"
    return desktop / f"{APP_NAME}.lnk"


def create_desktop_shortcut_file() -> Path:
    if not sys.platform.startswith("win"):
        raise RuntimeError("Desktop shortcut creation is currently supported on Windows only.")
    shortcut_path = desktop_shortcut_path()
    shortcut_path.parent.mkdir(parents=True, exist_ok=True)
    target, arguments, working_dir = running_app_shortcut_target()
    script = "\n".join(
        [
            "$ErrorActionPreference = 'Stop'",
            "$shell = New-Object -ComObject WScript.Shell",
            f"$shortcut = $shell.CreateShortcut({powershell_string(shortcut_path)})",
            f"$shortcut.TargetPath = {powershell_string(target)}",
            f"$shortcut.Arguments = {powershell_string(arguments)}",
            f"$shortcut.WorkingDirectory = {powershell_string(working_dir)}",
            f"$shortcut.IconLocation = {powershell_string(target)}",
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
        try:
            image = tk.PhotoImage(file=str(path))
        except tk.TclError:
            return None
        max_dimension = max(image.width(), image.height())
        if max_dimension > max_size:
            scale = max(1, (max_dimension + max_size - 1) // max_size)
            image = image.subsample(scale, scale)
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
        messagebox.showinfo(
            APP_NAME,
            f"{app.name} is visible in the catalog.\n\n"
            "Install/update logic comes next. This first build only discovers the hub folder "
            "and reads the app catalog safely.",
        )

    def launch_selected_placeholder(self) -> None:
        app = self.selected_app()
        if app is None:
            return
        messagebox.showinfo(
            APP_NAME,
            f"{app.name} launch support comes after local install tracking is added.",
        )

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
        self.installed_app_ids = load_installed_app_ids()
        self.selected_app_id: str | None = None
        self.current_view = "find"
        self.detail_back_view = "find"
        self.hovered_nav_view: str | None = None
        self.download_queue: list[HubApp] = []
        self.active_download: HubApp | None = None
        self.download_flash_on = False
        self.header_texture_image: tk.PhotoImage | None = None

        self.path_text = tk.StringVar()
        self.status_text = tk.StringVar(value="Choose the Business App Hub folder.")
        self.find_search_text = tk.StringVar()
        self.my_search_text = tk.StringVar()
        self.download_text = tk.StringVar(value="No active downloads.")
        self.download_queue_text = tk.StringVar(value="Queue: 0")
        self.download_progress = tk.IntVar(value=0)

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
            "Dark.TEntry",
            fieldbackground=COLORS["panel"],
            foreground=COLORS["text"],
            bordercolor=COLORS["border"],
            lightcolor=COLORS["border"],
            darkcolor=COLORS["border"],
        )
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
        self.nav_frame.columnconfigure(3, weight=1)
        self.nav_buttons: dict[str, tk.Label] = {}
        self.build_nav_tab("my", "MY APPS", 0)
        self.build_nav_tab("find", "FIND APPS", 1)
        self.build_nav_tab("settings", "SETTINGS", 2)

        self.nav_search_frame = tk.Frame(self.nav_frame, bg=COLORS["background"])
        self.nav_search_frame.grid(row=0, column=4, sticky="e")
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
        self.portal_button(
            self.downloads_bar,
            "Open Hub Folder",
            self.open_hub_folder,
            compact=True,
            subtle=True,
        ).grid(row=0, column=3, rowspan=2, sticky="e", padx=(0, 8), pady=16)
        self.portal_button(
            self.downloads_bar,
            "GitHub Help",
            self.open_github_help,
            compact=True,
            subtle=True,
        ).grid(row=0, column=4, rowspan=2, sticky="e", padx=(0, 18), pady=16)

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
        self.current_view = view
        if view in ("my", "find", "settings"):
            self.detail_back_view = view
        self.paint_nav()
        self.render_current_view()

    def paint_nav(self) -> None:
        active_view = self.detail_back_view if self.current_view == "detail" else self.current_view
        for view, label in self.nav_buttons.items():
            active = view == active_view
            hovered = view == self.hovered_nav_view
            label.configure(
                bg=COLORS["background"],
                fg=COLORS["accent"] if active or hovered else COLORS["nav_text"],
                font=(FONT_FAMILY, 10, "bold"),
                highlightthickness=0,
            )
        if hasattr(self, "nav_search_frame"):
            search_var = self.active_search_var()
            if search_var is None:
                self.nav_search_frame.grid_remove()
            else:
                self.nav_search_frame.grid()
                self.nav_search_entry.configure(textvariable=search_var)

    def start_folder_discovery(self) -> None:
        saved = load_saved_hub_folder()
        if saved is not None:
            self.set_hub_folder(saved, remember_company=False)
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

    def set_hub_folder(self, folder: Path, *, remember_company: bool = True) -> None:
        self.hub_folder = normalize_path(folder)
        self.path_text.set(str(self.hub_folder))
        save_hub_folder(self.hub_folder)
        if remember_company:
            try:
                save_company_hub_folder_preference(self.hub_folder)
            except OSError:
                pass
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
        for child in self.content.winfo_children():
            child.destroy()
        self.card_frames.clear()
        if self.current_view == "my":
            self.render_my_apps()
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
        apps = [app for app in self.catalog.apps if app.app_id in self.installed_app_ids]
        self.build_store_grid_page(
            panel,
            "MY APPS",
            "Apps downloaded on this computer. Click one to launch, update, or inspect releases.",
            apps,
            "Your library is empty",
            "Go to Find Apps and download an app to add it here.",
            mode="my",
        )

    def render_settings(self) -> None:
        self.content.columnconfigure(0, weight=1)
        self.content.rowconfigure(0, weight=1)
        panel = self.portal_panel(self.content)
        panel.grid(row=0, column=0, sticky="nsew")
        panel.columnconfigure(0, weight=1)

        page = tk.Frame(panel, bg=COLORS["panel"])
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
            "The shared company hub also stores a relative folder preference in "
            f"{HUB_SETTINGS_FILE_NAME}."
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

    def create_store_tile(self, parent: tk.Widget, app: HubApp, row: int, column: int) -> None:
        installed = app.app_id in self.installed_app_ids
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
        tk.Label(
            tile,
            text="Installed" if installed else "Available",
            bg=COLORS["store_card"],
            fg=COLORS["success"] if installed else COLORS["accent"],
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

        def draw_thumb(first: float = 0.0, last: float = 1.0) -> None:
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

        def scroll_to_event(event: tk.Event) -> None:
            height = max(scroll_canvas.winfo_height(), 1)
            fraction = min(1.0, max(0.0, event.y / height))
            canvas.yview_moveto(fraction)

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
        scroll_canvas.bind("<Button-1>", scroll_to_event)
        scroll_canvas.bind("<B1-Motion>", scroll_to_event)
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
        installed = app.app_id in self.installed_app_ids
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
        status = "Installed" if installed else "Available"
        status_color = COLORS["success"] if installed else COLORS["accent"]
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
        if self.current_view in ("find", "my"):
            self.detail_back_view = self.current_view
        self.current_view = "detail"
        self.paint_nav()
        self.render_current_view()

    def paint_cards(self) -> None:
        for app_id, card in self.card_frames.items():
            selected = app_id == self.selected_app_id
            bg = COLORS["card_selected"] if selected else COLORS["card"]
            border = COLORS["accent"] if selected else COLORS["border"]
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

        installed = app.app_id in self.installed_app_ids
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
                f"{'Installed on this computer' if installed else 'Not installed'}"
            ),
            bg=COLORS["panel_alt"],
            fg=COLORS["muted"],
            font=(FONT_FAMILY, 10),
        ).grid(row=1, column=1, sticky="w", pady=(6, 0))
        self.portal_button(
            hero,
            "Update / Repair" if installed else "Download",
            lambda selected=app: self.queue_download(selected),
            accent=True,
        ).grid(row=2, column=1, sticky="w", pady=(18, 0))

        description_panel = tk.Frame(
            page,
            bg=COLORS["panel_alt"],
            highlightbackground=COLORS["border"],
            highlightthickness=1,
            padx=20,
            pady=16,
        )
        description_panel.grid(row=2, column=0, sticky="ew", pady=(14, 14))
        description_panel.columnconfigure(0, weight=1)
        tk.Label(
            description_panel,
            text="Shared Company Description",
            bg=COLORS["panel_alt"],
            fg=COLORS["text"],
            font=(FONT_FAMILY, 12, "bold"),
        ).grid(row=0, column=0, sticky="w")
        self.description_editor = tk.Text(
            description_panel,
            height=6,
            width=105,
            wrap="word",
            bg="#171a27",
            fg=COLORS["text"],
            insertbackground=COLORS["text"],
            relief="flat",
            font=(FONT_FAMILY, 10),
            padx=10,
            pady=8,
        )
        self.description_editor.grid(row=1, column=0, sticky="ew", pady=(8, 8))
        self.description_editor.insert("1.0", app.description or "")
        self.portal_button(
            description_panel,
            "Save Shared Description",
            self.save_selected_description,
            compact=True,
        ).grid(row=2, column=0, sticky="e")

        detail_grid = tk.Frame(page, bg=COLORS["panel"])
        detail_grid.grid(row=3, column=0, sticky="ew")
        for col in range(3):
            detail_grid.columnconfigure(col, weight=1)
        self.info_tile(detail_grid, "Executable", app.executable_name or "-", 0)
        self.info_tile(detail_grid, "Source Folder", app.source_folder or "-", 1)
        self.info_tile(detail_grid, "Releases", self.release_status(app), 2)

        releases_panel = tk.Frame(page, bg=COLORS["panel"])
        releases_panel.grid(row=4, column=0, sticky="ew", pady=(16, 0))
        releases_panel.columnconfigure(0, weight=1)
        releases_panel.rowconfigure(1, weight=1)
        tk.Label(
            releases_panel,
            text="APPROVED RELEASES",
            bg=COLORS["panel"],
            fg=COLORS["text"],
            font=(FONT_FAMILY, 12, "bold"),
        ).grid(row=0, column=0, sticky="w", pady=(0, 6))
        release_list = tk.Listbox(
            releases_panel,
            bg=COLORS["panel_alt"],
            fg=COLORS["text"],
            relief="flat",
            activestyle="none",
            font=(FONT_FAMILY, 10),
            width=115,
            height=6,
        )
        release_list.grid(row=1, column=0, sticky="ew")
        releases = app.published_releases
        if not releases:
            release_list.insert("end", "No allowed releases yet.")
        else:
            for release in releases:
                release_list.insert("end", f"{release.version}    {release.notes or 'No notes'}")

        action_row = tk.Frame(page, bg=COLORS["panel"])
        action_row.grid(row=5, column=0, sticky="ew", pady=(14, 0))
        for col in range(3):
            action_row.columnconfigure(col, weight=1)
        self.portal_button(
            action_row,
            "Open Source Folder",
            self.open_selected_source_folder,
            subtle=True,
        ).grid(row=0, column=0, sticky="ew", padx=(0, 6))
        self.portal_button(
            action_row,
            "Launch",
            self.launch_selected_placeholder,
            state="normal" if installed else "disabled",
        ).grid(row=0, column=1, sticky="ew", padx=6)
        self.portal_button(
            action_row,
            "Download",
            lambda selected=app: self.queue_download(selected),
            accent=True,
        ).grid(row=0, column=2, sticky="ew", padx=(6, 0))

    def show_app_detail(self, app: HubApp | None) -> None:
        for child in self.detail_panel.winfo_children():
            child.destroy()
        self.detail_panel.columnconfigure(0, weight=1)
        self.detail_panel.rowconfigure(4, weight=1)

        if app is None:
            detail = "Choose an app to view downloads, releases, and company notes."
            if self.current_view == "my":
                detail = "Your downloaded apps appear here after you install one."
            tk.Label(
                self.detail_panel,
                text="Select an app",
                bg=COLORS["panel"],
                fg=COLORS["text"],
                font=(FONT_FAMILY, 22, "bold"),
            ).grid(row=0, column=0, sticky="w")
            tk.Label(
                self.detail_panel,
                text=detail,
                bg=COLORS["panel"],
                fg=COLORS["muted"],
                font=(FONT_FAMILY, 11),
                wraplength=560,
                justify="left",
            ).grid(row=1, column=0, sticky="w", pady=(10, 0))
            return

        installed = app.app_id in self.installed_app_ids
        hero = tk.Frame(self.detail_panel, bg=COLORS["panel"])
        hero.grid(row=0, column=0, sticky="ew")
        hero.columnconfigure(1, weight=1)
        icon = self.load_app_icon(app, 112)
        if icon:
            icon_label = tk.Label(hero, image=icon, bg=COLORS["panel"], width=124, height=124)
        else:
            icon_label = tk.Label(
                hero,
                text=self.app_initials(app.name),
                bg=COLORS["purple"],
                fg="#ffffff",
                width=8,
                height=4,
                font=(FONT_FAMILY, 20, "bold"),
            )
        icon_label.grid(row=0, column=0, rowspan=3, sticky="nw", padx=(0, 18))
        tk.Label(
            hero,
            text=app.name,
            bg=COLORS["panel"],
            fg=COLORS["text"],
            font=(FONT_FAMILY, 24, "bold"),
        ).grid(row=0, column=1, sticky="w")
        tk.Label(
            hero,
            text=(
                f"{app.app_id}  |  Default {app.default_version or '-'}  |  "
                f"{'Installed' if installed else 'Not installed'}"
            ),
            bg=COLORS["panel"],
            fg=COLORS["muted"],
            font=(FONT_FAMILY, 10),
        ).grid(row=1, column=1, sticky="w", pady=(5, 0))
        self.portal_button(
            hero,
            "Update / Repair" if installed else "Download",
            lambda selected=app: self.queue_download(selected),
            accent=True,
        ).grid(row=2, column=1, sticky="w", pady=(16, 0))

        notes = tk.Frame(
            self.detail_panel,
            bg=COLORS["panel_alt"],
            highlightbackground=COLORS["border"],
            highlightthickness=1,
            padx=12,
            pady=10,
        )
        notes.grid(row=1, column=0, sticky="ew", pady=(18, 14))
        notes.columnconfigure(0, weight=1)
        tk.Label(
            notes,
            text="Company Description",
            bg=COLORS["panel_alt"],
            fg=COLORS["text"],
            font=(FONT_FAMILY, 11, "bold"),
        ).grid(row=0, column=0, sticky="w")
        self.description_editor = tk.Text(
            notes,
            height=7,
            wrap="word",
            bg="#1b1e2b",
            fg=COLORS["text"],
            insertbackground=COLORS["text"],
            relief="flat",
            font=(FONT_FAMILY, 10),
            padx=10,
            pady=8,
        )
        self.description_editor.grid(row=1, column=0, sticky="ew", pady=(8, 8))
        self.description_editor.insert("1.0", app.description or "")
        self.portal_button(
            notes,
            "Save Shared Description",
            self.save_selected_description,
            compact=True,
        ).grid(row=2, column=0, sticky="e")

        detail_grid = tk.Frame(self.detail_panel, bg=COLORS["panel"])
        detail_grid.grid(row=2, column=0, sticky="ew")
        for col in range(3):
            detail_grid.columnconfigure(col, weight=1)
        self.info_tile(detail_grid, "Executable", app.executable_name or "-", 0)
        self.info_tile(detail_grid, "Source Folder", app.source_folder or "-", 1)
        self.info_tile(detail_grid, "Releases", self.release_status(app), 2)

        tk.Label(
            self.detail_panel,
            text="APPROVED RELEASES",
            bg=COLORS["panel"],
            fg=COLORS["text"],
            font=(FONT_FAMILY, 12, "bold"),
        ).grid(row=3, column=0, sticky="w", pady=(18, 6))
        release_list = tk.Listbox(
            self.detail_panel,
            bg=COLORS["panel_alt"],
            fg=COLORS["text"],
            relief="flat",
            activestyle="none",
            font=(FONT_FAMILY, 10),
            height=8,
        )
        release_list.grid(row=4, column=0, sticky="nsew")
        releases = app.published_releases
        if not releases:
            release_list.insert("end", "No allowed releases yet.")
        else:
            for release in releases:
                release_list.insert("end", f"{release.version}    {release.notes or 'No notes'}")

        action_row = tk.Frame(self.detail_panel, bg=COLORS["panel"])
        action_row.grid(row=5, column=0, sticky="ew", pady=(14, 0))
        for col in range(3):
            action_row.columnconfigure(col, weight=1)
        self.portal_button(
            action_row,
            "Open Source Folder",
            self.open_selected_source_folder,
            subtle=True,
        ).grid(row=0, column=0, sticky="ew", padx=(0, 6))
        self.portal_button(
            action_row,
            "Launch",
            self.launch_selected_placeholder,
            state="normal" if installed else "disabled",
        ).grid(row=0, column=1, sticky="ew", padx=6)
        self.portal_button(
            action_row,
            "Download",
            lambda selected=app: self.queue_download(selected),
            accent=True,
        ).grid(row=0, column=2, sticky="ew", padx=(6, 0))

    def info_tile(self, parent: tk.Widget, label: str, value: str, column: int) -> None:
        tile = tk.Frame(parent, bg=COLORS["panel_alt"], padx=10, pady=8)
        tile.grid(row=0, column=column, sticky="ew", padx=(0 if column == 0 else 6, 0))
        tk.Label(
            tile,
            text=label,
            bg=COLORS["panel_alt"],
            fg=COLORS["muted"],
            font=(FONT_FAMILY, 8, "bold"),
        ).grid(row=0, column=0, sticky="w")
        tk.Label(
            tile,
            text=value,
            bg=COLORS["panel_alt"],
            fg=COLORS["text"],
            font=(FONT_FAMILY, 9),
            wraplength=190,
            justify="left",
        ).grid(row=1, column=0, sticky="w", pady=(4, 0))

    def save_selected_description(self) -> None:
        app = self.selected_app()
        if app is None or self.hub_folder is None:
            return
        description = self.description_editor.get("1.0", "end").strip()
        try:
            update_catalog_app_fields(self.hub_folder, app.app_id, {"description": description})
        except Exception as exc:
            messagebox.showerror(APP_NAME, f"Could not save description:\n\n{exc}")
            return
        self.status_text.set(f"Saved description for {app.name}.")
        self.refresh_catalog()

    def queue_download(self, app: HubApp) -> None:
        queued_ids = {queued.app_id for queued in self.download_queue}
        if self.active_download is not None:
            queued_ids.add(self.active_download.app_id)
        if app.app_id in queued_ids:
            self.download_text.set(f"{app.name} is already in the update queue.")
            return
        self.download_queue.append(app)
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
        self.download_text.set(f"Downloading {self.active_download.name}... {progress}%")
        if progress >= 100:
            self.finish_active_download()
            return
        self.after(80, self.tick_download)

    def finish_active_download(self) -> None:
        if self.active_download is None:
            return
        finished = self.active_download
        self.installed_app_ids.add(finished.app_id)
        save_installed_app_ids(self.installed_app_ids)
        self.download_text.set(f"{finished.name} is ready in My Apps.")
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
        try:
            image = tk.PhotoImage(file=str(path))
        except tk.TclError:
            return None
        max_dimension = max(image.width(), image.height())
        if max_dimension > max_size:
            scale = max(1, (max_dimension + max_size - 1) // max_size)
            image = image.subsample(scale, scale)
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

    def launch_selected_placeholder(self) -> None:
        app = self.selected_app()
        if app is None:
            return
        messagebox.showinfo(
            APP_NAME,
            f"{app.name} launch support comes after real install extraction is added.",
        )

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


def main() -> None:
    app = SteamStyleBusinessAppHub()
    app.mainloop()


if __name__ == "__main__":
    main()
