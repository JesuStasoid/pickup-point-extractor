#!/usr/bin/env bash
# Build "Pick-up point extractor.app" and "Pick-up point extractor v1.0.dmg".
#
# One universal2 app covers Apple Silicon and Intel. python.org's universal2
# installer ships Tcl/Tk 8.6, which is what actually draws on current macOS
# (Apple's system Tk, and the old Intel-only Tk 8.6.8, show a black window).
# pypdf is pure Python, so there is no native wheel to merge and no second
# Intel runner.
#
#   bash packaging/macos/build_macos.sh
#   PYTHON=/path/to/python.org/python3 bash packaging/macos/build_macos.sh
#
# Ad-hoc signature only (codesign -). After download, Control-click the app
# and choose Open the first time. Gatekeeper does not trust an ad-hoc signature.
set -euo pipefail

if [[ "$(uname -s)" != "Darwin" ]]; then
  echo "build_macos.sh must run on macOS." >&2
  exit 1
fi

ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
BUILD="$ROOT/_build"
VENV="$BUILD/.venv"
NAME="Pick-up point extractor"
PY="${PYTHON:-python3}"

has_arch() {
  # has_arch arm64 x86_64 arm64
  local want="$1"
  shift
  local a
  for a in "$@"; do
    if [[ "$a" == "$want" ]]; then
      return 0
    fi
  done
  return 1
}

echo "Using $PY"
EXE="$("$PY" -c 'import sys; print(sys.executable)')"
ARCHS="$(lipo -archs "$EXE" 2>/dev/null || true)"
echo "interpreter: $EXE"
echo "archs: ${ARCHS:-<not a Mach-O>}"
# shellcheck disable=SC2086
if ! has_arch arm64 $ARCHS || ! has_arch x86_64 $ARCHS; then
  echo "Need a universal2 Python (arm64 and x86_64). Install the python.org macOS installer and set PYTHON." >&2
  exit 1
fi

ROOT="$ROOT" "$PY" - <<'PY'
import os, sys, tkinter as tk
sys.path.insert(0, os.path.join(os.environ["ROOT"], "src"))
import version
print(f"app {version.APP_NAME} {version.VERSION}")
root = tk.Tk()
root.withdraw()
patch = str(root.tk.call("info", "patchlevel"))
print(f"tk {patch}")
parts = tuple(int(p) for p in patch.split("."))
root.destroy()
if parts < (8, 6):
    raise SystemExit(f"Tk {patch} is older than 8.6")
PY

VERSION="$(ROOT="$ROOT" "$PY" -c 'import os, sys; sys.path.insert(0, os.path.join(os.environ["ROOT"], "src")); import version; print(version.VERSION)')"
WIN_TITLE="$(ROOT="$ROOT" "$PY" -c 'import os, sys; sys.path.insert(0, os.path.join(os.environ["ROOT"], "src")); import version; print(version.WINDOW_TITLE)')"

mkdir -p "$BUILD"
rm -rf "$VENV"
"$PY" -m venv "$VENV"
"$VENV/bin/python" -m pip install --disable-pip-version-check -q -r "$ROOT/requirements-build.txt"

# Same excludes as build_windows.ps1.
# Do NOT exclude email or urllib: Path.as_uri() imports them on Python 3.14
# (Windows) when the .dbpr is opened read-only.
EXCLUDES=(
  numpy PIL matplotlib pandas scipy cryptography Crypto
  unittest pydoc doctest test lib2to3 distutils setuptools
  pip venv ensurepip idlelib turtle turtledemo tkinter.test
  xmlrpc http.server multiprocessing concurrent asyncio
  curses pdb bz2 lzma _bz2 _lzma
  ssl _ssl _hashlib _zstd compression.zstd
)
EXCLUDE_ARGS=()
for mod in "${EXCLUDES[@]}"; do
  EXCLUDE_ARGS+=("--exclude-module=$mod")
done

"$VENV/bin/python" -m PyInstaller --noconfirm --clean --windowed --onedir --noupx \
  --target-architecture universal2 \
  --name "$NAME" \
  --osx-bundle-identifier "com.stanislavbelov.pickuppointextractor" \
  --hidden-import core \
  --hidden-import version \
  --hidden-import _diag \
  --hidden-import extract_arraycalc_hoists \
  --hidden-import extract_soundvision_hoists \
  --hidden-import pypdf \
  --hidden-import tkinter \
  --hidden-import tkinter.ttk \
  --hidden-import tkinter.filedialog \
  --paths "$ROOT/src" \
  --distpath "$BUILD/dist-mac" --workpath "$BUILD/work-mac" --specpath "$BUILD" \
  "${EXCLUDE_ARGS[@]}" \
  "$ROOT/src/app.py"

APP="$BUILD/dist-mac/$NAME.app"
PL="$APP/Contents/Info.plist"
MAIN="$APP/Contents/MacOS/$NAME"

plist_set() {
  local key="$1" type="$2" value="$3" rendered
  if [[ "$type" == "string" ]]; then
    rendered="\"$value\""
  else
    rendered="$value"
  fi
  if /usr/libexec/PlistBuddy -c "Set :$key $rendered" "$PL" 2>/dev/null; then
    return 0
  fi
  /usr/libexec/PlistBuddy -c "Add :$key $type $rendered" "$PL"
}
plist_set CFBundleShortVersionString string "$VERSION"
plist_set CFBundleVersion string "$VERSION"
plist_set CFBundleName string "$NAME"
plist_set CFBundleDisplayName string "$NAME"
plist_set NSHighResolutionCapable bool true
# The Mach-O minos is what macOS actually enforces. Publish the same floor in
# Info.plist (python.org 3.13 universal2 is 11.0 on both slices).
if command -v vtool >/dev/null 2>&1; then
  MINOS="$(vtool -show-build "$MAIN" | awk '/minos/{print $2; exit}')"
  if [[ -n "${MINOS}" ]]; then
    plist_set LSMinimumSystemVersion string "$MINOS"
  fi
fi

# Ad-hoc, inside-out. No Developer ID and no timestamp server.
while IFS= read -r -d '' f; do
  if file -b "$f" | grep -q 'Mach-O'; then
    codesign --force --sign - "$f"
  fi
done < <(find "$APP" -type f -print0)
while IFS= read -r bundle; do
  codesign --force --sign - "$bundle"
done < <(find "$APP" -depth \( -name '*.framework' -o -name '*.app' -o -name '*.xpc' -o -name '*.bundle' \) -print)
codesign --verify --verbose=2 "$APP"

bad=0
while IFS= read -r -d '' f; do
  if file -b "$f" | grep -q 'Mach-O'; then
    archs="$(lipo -archs "$f" 2>/dev/null || true)"
    printf '%s\n' "$archs  $f"
    # shellcheck disable=SC2086
    if ! has_arch arm64 $archs || ! has_arch x86_64 $archs; then
      echo "Not universal2: $f ($archs)" >&2
      bad=1
    fi
  fi
done < <(find "$APP" -type f -print0)
if [[ "$bad" -ne 0 ]]; then
  exit 1
fi

tcl="$(find "$APP" -name init.tcl -print | head -n 1)"
tkdata="$(find "$APP" -name tk.tcl -print | head -n 1)"
if [[ -z "$tcl" || -z "$tkdata" ]]; then
  echo "Tcl/Tk scripts were not packaged (init.tcl=${tcl:-missing}, tk.tcl=${tkdata:-missing})." >&2
  exit 1
fi
echo "tcl $tcl"
echo "tk  $tkdata"

if command -v vtool >/dev/null 2>&1; then
  vtool -show-build "$MAIN" || true
fi
echo "LSMinimumSystemVersion=$(plutil -extract LSMinimumSystemVersion raw "$PL" 2>/dev/null || echo '<unset>')"

DMG="$ROOT/$WIN_TITLE.dmg"
rm -f "$DMG"
hdiutil create -volname "$NAME" -srcfolder "$APP" -ov -format UDZO "$DMG"
bytes="$(stat -f%z "$DMG")"
echo "Built: $DMG ($bytes bytes)"

{
  echo "version=$VERSION"
  echo "dmg=$DMG"
  echo "dmg_bytes=$bytes"
  echo "python=$EXE"
  echo "python_archs=$ARCHS"
  echo "tk_scripts=$tcl"
} > "$BUILD/build-info.txt"
