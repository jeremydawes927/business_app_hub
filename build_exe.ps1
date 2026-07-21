param(
  [string]$Version = "0.1.0",
  [string]$ReleaseRoot = ""
)

$ErrorActionPreference = "Stop"
$projectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$sourcePath = Join-Path $projectRoot "src\business_app_hub.py"
$assetsPath = Join-Path $projectRoot "assets"
$distPath = Join-Path $projectRoot "dist"
$buildPath = Join-Path $projectRoot "build"

if (-not (Test-Path -LiteralPath $sourcePath)) {
  throw "Could not find source file: $sourcePath"
}

$pyInstallerArgs = @(
  "--noconfirm",
  "--clean",
  "--windowed",
  "--name", "Business App Hub",
  "--distpath", $distPath,
  "--workpath", $buildPath
)

if (Test-Path -LiteralPath $assetsPath) {
  $pyInstallerArgs += @("--add-data", "$assetsPath;assets")
}

$pyInstallerArgs += $sourcePath
python -m PyInstaller @pyInstallerArgs

$distRoot = Join-Path $distPath "Business App Hub"
if (-not (Test-Path (Join-Path $distRoot "Business App Hub.exe"))) {
  throw "Build finished, but Business App Hub.exe was not found in $distRoot."
}

if ($ReleaseRoot) {
  $releaseDir = Join-Path $ReleaseRoot "Releases"
  New-Item -ItemType Directory -Force -Path $releaseDir | Out-Null
  $zipPath = Join-Path $releaseDir ("Business App Hub " + $Version + ".zip")
  if (Test-Path $zipPath) {
    Remove-Item -LiteralPath $zipPath -Force
  }
  Compress-Archive -Path (Join-Path $distRoot "*") -DestinationPath $zipPath -Force
  $zipHash = (Get-FileHash -Algorithm SHA256 -LiteralPath $zipPath).Hash
  $manifest = [ordered]@{
    version = $Version
    package = "Releases/Business App Hub $Version.zip"
    notes = "Business App Hub $Version"
    sha256 = $zipHash
  }
  $manifest | ConvertTo-Json | Set-Content -LiteralPath (Join-Path $ReleaseRoot "latest.json") -Encoding UTF8
  Write-Host "Release zip: $zipPath"
  Write-Host "SHA-256:     $zipHash"
}

Write-Host "Build complete: $distRoot"
