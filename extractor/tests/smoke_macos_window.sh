#!/usr/bin/env bash
# Open the frozen .app, screenshot its window, and reject a blank Tk window.
#   bash tests/smoke_macos_window.sh "/path/Pick-up point extractor.app" /tmp/window.png
set -euo pipefail

if [[ "$(uname -s)" != "Darwin" ]]; then
  echo "smoke_macos_window.sh must run on macOS." >&2
  exit 1
fi
if [[ $# -lt 1 ]]; then
  echo "usage: smoke_macos_window.sh App.app [screenshot.png]" >&2
  exit 2
fi

APP="$1"
SHOT="${2:-/tmp/ppe-window.png}"
NAME="Pick-up point extractor"
BIN="$APP/Contents/MacOS/$NAME"
HERE="$(cd "$(dirname "$0")" && pwd)"
PY="${PYTHON:-python3}"
WORKDIR="$(mktemp -d /tmp/ppe-window.XXXXXX)"
SWIFT_SRC="$WORKDIR/find_window.swift"
FINDER="$WORKDIR/find_window"
LOG="$WORKDIR/app.log"
pid=""

on_exit() {
  status=$?
  if [[ -n "$pid" ]]; then
    kill "$pid" 2>/dev/null || true
    wait "$pid" 2>/dev/null || true
  fi
  pkill -x "$NAME" 2>/dev/null || true
  exit "$status"
}
trap on_exit EXIT

if [[ ! -x "$BIN" ]]; then
  echo "missing app binary: $BIN" >&2
  exit 1
fi
xattr -dr com.apple.quarantine "$APP" 2>/dev/null || true

mkdir -p "$(dirname "$SHOT")"
"$PY" "$HERE/check_window_bmp.py" --self-test

cat > "$SWIFT_SRC" <<'SWIFT'
import CoreGraphics
import Foundation

let ownerName = CommandLine.arguments[1]
var wanted = Set<Int32>()
for arg in CommandLine.arguments.dropFirst(2) {
    if let n = Int32(arg) { wanted.insert(n) }
}

func num(_ v: Any?) -> Double {
    if let n = v as? Double { return n }
    if let n = v as? Int { return Double(n) }
    if let n = v as? NSNumber { return n.doubleValue }
    return 0
}

func bounds(_ w: [String: Any]) -> (Double, Double, Double, Double) {
    let b = w[kCGWindowBounds as String] as? [String: Any] ?? [:]
    return (num(b["X"]), num(b["Y"]), num(b["Width"]), num(b["Height"]))
}

func ownerPID(_ w: [String: Any]) -> Int32 {
    let v = w[kCGWindowOwnerPID as String]
    if let n = v as? Int32 { return n }
    if let n = v as? Int { return Int32(n) }
    if let n = v as? NSNumber { return n.int32Value }
    return -1
}

let deadline = Date().addingTimeInterval(25)
var found: [String: Any]? = nil
let list = CGWindowListOption(arrayLiteral: .optionOnScreenOnly, .excludeDesktopElements)
while Date() < deadline {
    let info = CGWindowListCopyWindowInfo(list, kCGNullWindowID) as? [[String: Any]] ?? []
    let matches = info.filter { w in
        let name = w[kCGWindowOwnerName as String] as? String ?? ""
        let pid = ownerPID(w)
        let b = bounds(w)
        let named = name == ownerName || name.hasPrefix(ownerName)
        return (named || wanted.contains(pid)) && b.2 * b.3 > 1000
    }
    if let best = matches.max(by: { bounds($0).2 * bounds($0).3 < bounds($1).2 * bounds($1).3 }) {
        found = best
        break
    }
    Thread.sleep(forTimeInterval: 0.25)
}

guard let found else {
    let info = CGWindowListCopyWindowInfo(list, kCGNullWindowID) as? [[String: Any]] ?? []
    fputs("no window for \(ownerName) pids=\(wanted)\n", stderr)
    for w in info {
        let name = w[kCGWindowOwnerName as String] as? String ?? ""
        let title = w[kCGWindowName as String] as? String ?? ""
        let b = bounds(w)
        fputs("  pid=\(ownerPID(w)) owner=\(name) title=\(title) \(Int(b.2))x\(Int(b.3))\n", stderr)
    }
    exit(1)
}

let b = bounds(found)
let wid = Int(num(found[kCGWindowNumber as String]))
print("\(wid) \(Int(b.0)) \(Int(b.1)) \(Int(b.2)) \(Int(b.3))")
SWIFT

swiftc -o "$FINDER" "$SWIFT_SRC"

"$BIN" >"$LOG" 2>&1 &
pid=$!
# The bootloader can replace itself; also match whatever is now named the app.
sleep 0.4
extra="$(pgrep -x "$NAME" || true)"

# shellcheck disable=SC2086
line="$("$FINDER" "$NAME" $pid $extra)"
echo "window $line"
set -- $line
wid=$1
x=$2
y=$3
w=$4
h=$5

# Best-effort activate. Accessibility permission is not always granted; don't block on it.
osascript -e "tell application \"System Events\" to set frontmost of process \"$NAME\" to true" >/dev/null 2>&1 &
ax=$!
i=0
while kill -0 "$ax" 2>/dev/null; do
  i=$((i + 1))
  if [[ "$i" -ge 8 ]]; then
    kill "$ax" 2>/dev/null || true
    break
  fi
  sleep 0.25
done
wait "$ax" 2>/dev/null || true
sleep 0.6

bmp="${SHOT%.png}.bmp"
capture_id() {
  screencapture -x -l "$wid" -o "$SHOT"
  sips -s format bmp "$SHOT" --out "$bmp" >/dev/null
}
capture_region() {
  screencapture -x -R "${x},${y},${w},${h}" "$SHOT"
  sips -s format bmp "$SHOT" --out "$bmp" >/dev/null
}

set +e
capture_id
id_status=$?
"$PY" "$HERE/check_window_bmp.py" "$bmp" --crop-top-frac 0.14
check_status=$?
set -e
if [[ "$id_status" -ne 0 || "$check_status" -ne 0 ]]; then
  echo "window-id capture was not a drawn UI (capture=$id_status check=$check_status); retrying region ${w}x${h}"
  capture_region
  "$PY" "$HERE/check_window_bmp.py" "$bmp" --crop-top-frac 0.14
fi
echo "screenshot $SHOT"
echo "app log:"
cat "$LOG" || true
