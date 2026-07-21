# Business App Hub

Business App Hub is a lightweight launcher, installer, and update portal for small custom company apps.

The hub is built around a Steam-inspired portal layout:

- finds a local or OneDrive-synced `Business App Hub` folder
- asks the user to confirm the folder it found
- lets the user browse to a folder if auto-discovery fails
- reads `catalog.json`
- shows a `Find Apps` page for the shared company catalog
- shows a `My Apps` page for apps downloaded on the current computer
- shows app icons, descriptions, allowed releases, and source folders
- installs approved release ZIPs into a local app-data install folder
- launches installed apps from the hub or from hub-managed Desktop shortcuts
- lets local users delete installed copies without changing the shared catalog
- includes a publish page for adding new apps and approved app releases to the shared hub
- provides a bottom update/download bar with queue status and progress
- checks the public GitHub releases feed for new Business App Hub versions
- stores only local preferences and installed-app status in `%LOCALAPPDATA%\Business App Hub`

## Portal Layout

`Find Apps` is the company app store. It reads every app card from the shared `catalog.json`, including the app name, icon, description, default version, allowed releases, and source folder.

Clicking an app opens its detail page. The description editor saves back to the shared company `catalog.json`, so description changes are shared with other employees in the same company folder.

`My Apps` is the local library. It only shows apps that this computer has installed. Local install records are stored in:

```text
%LOCALAPPDATA%\Business App Hub\settings.json
```

The bottom `UPDATES` bar is the update queue surface. It flashes while work is active, shows queue count, displays progress for the current app, and reveals an **Update Hub** button when the public GitHub release check finds a newer hub version.

The Settings page includes **Create Desktop Shortcut**, which creates a Windows `.lnk` pointing back through the hub. App detail pages can also create app-specific Desktop shortcuts. Those app shortcuts open the app through Business App Hub, so the Desktop stays clean and the hub can keep track of the current local install.

The `Publish Apps` page can create new shared app entries or publish updates to existing app entries. It accepts a `.zip`, `.exe`, or folder, writes the package into the app's `Releases` folder, calculates a SHA-256 hash, updates `catalog.json`, and writes that app's `latest.json`.

Company-specific app metadata belongs in the company OneDrive/SharePoint folder, not in GitHub:

- `catalog.json`
- app icons
- release ZIPs
- private documents
- company-specific instructions
- credentials or internal links

## Hub Folder

The company/shared folder should contain:

```text
Business App Hub/
  catalog.json
  Apps/
```

For now the empty catalog should be:

```json
{
  "hub_version": "1.0.0",
  "apps": []
}
```

Each app can live inside `Apps/` or point to an existing release folder through `source_folder`.

## App Icons

Each app can show an icon in the hub library. The simplest setup is to place a PNG in that app's folder:

```text
Business App Hub/
  Apps/
    Inventory Helper/
      icon.png
      latest.json
      Releases/
```

If the catalog does not name an icon, the hub automatically looks for common names such as `icon.png`, `app.png`, `logo.png`, or `tile.png` in the app folder, `assets/`, or `icons/`.

You can also set a specific icon in `catalog.json`:

```json
{
  "id": "inventory-helper",
  "name": "Inventory Helper",
  "icon": "Apps/Inventory Helper/icon.png"
}
```

PNG is recommended because it works without extra runtime dependencies.

## Header Image

The hub ships with a bundled header image in `assets/hub_header.png`, and the build script packages that asset with the app. If that bundled image is unavailable, the app can fall back to a PNG or GIF in the shared company folder:

```text
Business App Hub/
  header.png
```

The fallback search also checks `hub_header.png`, `portal_header.png`, `background.png`, and the same names inside `Business App Hub/assets/`. Company-specific images stay in OneDrive or SharePoint, while the public repo can keep the generic app shell.

## Example Catalog Entry

```json
{
  "hub_version": "1.0.0",
  "apps": [
    {
      "id": "inventory-helper",
      "name": "Inventory Helper",
      "description": "Example internal operations app.",
      "icon": "Apps/Inventory Helper/icon.png",
      "source_folder": "Apps/Inventory Helper",
      "executable_name": "Inventory Helper.exe",
      "default_version": "1.0.0",
      "allowed_versions": ["1.0.0"],
      "blocked_versions": [],
      "releases": [
        {
          "version": "1.0.0",
          "zip": "Releases/Inventory Helper 1.0.0.zip",
          "sha256": "PUT_REAL_SHA256_HERE",
          "notes": "First approved release"
        }
      ]
    }
  ]
}
```

## Run From Source

```powershell
python .\src\business_app_hub.py
```

## Run Tests

```powershell
.\run_tests.ps1
```

## Package

Install build dependency:

```powershell
python -m pip install -r requirements-dev.txt
```

Build an EXE:

```powershell
.\build_exe.ps1
```

Build and write a release ZIP/manifest to a release folder:

```powershell
.\build_exe.ps1 -Version "0.1.2" -ReleaseRoot "C:\Path\To\Business App Hub"
```

## First-Time Company Setup

Use these steps the first time your company installs Business App Hub.

1. Create a shared OneDrive or SharePoint folder named:

```text
Business App Hub
```

2. Inside that folder, create this layout:

```text
Business App Hub/
  catalog.json
  Apps/
```

3. Put this starter content in `catalog.json`:

```json
{
  "hub_version": "1.0.0",
  "apps": []
}
```

4. Download and run Business App Hub on each user's computer.

5. On first launch, the app will try to find the shared `Business App Hub` folder automatically. If it finds the wrong folder or cannot find one, choose the correct folder with the Browse button.

6. When apps are ready to publish, use the **Publish Apps** tab to create a new app entry or add a new approved version to an existing app.

The GitHub project contains the generic hub app only. Your company's app catalog, release ZIPs, documents, credentials, and private files should stay in your own shared company folder.
