<#
  Build "Pick-up point extractor v1.0.exe" with PyInstaller.
  Uses its own venv in _build\.venv (the global Python is not touched).

  .\build_windows.ps1            # onefile exe -> .\Pick-up point extractor v1.0.exe
  .\build_windows.ps1 -OneDir    # onedir build -> _build\dist-onedir\ (for comparison)
  .\build_windows.ps1 -Python "C:\Python314\python.exe"
#>
param(
    [switch]$OneDir,
    [string]$Python = "python"
)
$ErrorActionPreference = "Stop"
$Root  = Split-Path -Parent $MyInvocation.MyCommand.Path
$Build = Join-Path $Root "_build"
$Venv  = Join-Path $Build ".venv"
$Name  = "Pick-up point extractor v1.0"
New-Item -ItemType Directory -Force $Build | Out-Null

if (-not (Test-Path (Join-Path $Venv "Scripts\python.exe"))) {
    Write-Host "Creating venv in $Venv"
    & $Python -m venv $Venv
}
$Py = Join-Path $Venv "Scripts\python.exe"
& $Py -m pip install --disable-pip-version-check -q -r (Join-Path $Root "requirements-build.txt")
if ($LASTEXITCODE) { throw "pip install failed" }

# Modules never needed by the app (keeps the exe small even if something drags them in).
# Do NOT exclude "email" or "urllib": Path.as_uri() imports them on Python 3.14 (Windows).
$Excludes = @(
  "numpy", "PIL", "matplotlib", "pandas", "scipy", "cryptography", "Crypto",
  "unittest", "pydoc", "doctest", "test", "lib2to3", "distutils", "setuptools",
  "pip", "venv", "ensurepip", "idlelib", "turtle", "turtledemo", "tkinter.test",
  "xmlrpc", "http.server", "multiprocessing", "concurrent", "asyncio",
  "curses", "pdb", "bz2", "lzma", "_bz2", "_lzma",
  "ssl", "_ssl", "_hashlib", "_zstd", "compression.zstd"   # -7 MB (OpenSSL); hashlib falls back to built-in md5/sha
) | ForEach-Object { "--exclude-module=$_" }

$Mode = if ($OneDir) { "--onedir" } else { "--onefile" }
$Dist = if ($OneDir) { Join-Path $Build "dist-onedir" } else { Join-Path $Build "dist" }

& $Py -m PyInstaller --noconfirm --clean $Mode --noconsole --noupx `
    --name $Name `
    --version-file (Join-Path $Root "packaging\windows\version_info.txt") `
    --paths (Join-Path $Root "src") `
    --distpath $Dist --workpath (Join-Path $Build "work") --specpath $Build `
    @Excludes `
    (Join-Path $Root "src\app.py")
if ($LASTEXITCODE) { throw "PyInstaller failed" }

if (-not $OneDir) {
    Copy-Item -Force (Join-Path $Dist "$Name.exe") (Join-Path $Root "$Name.exe")
    $size = (Get-Item (Join-Path $Root "$Name.exe")).Length / 1MB
    Write-Host ("Built: {0}  ({1:N1} MB)" -f (Join-Path $Root "$Name.exe"), $size)
} else {
    Write-Host "Built: $Dist\$Name\$Name.exe"
}
