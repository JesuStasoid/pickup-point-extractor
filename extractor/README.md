# Pick-up point extractor v1.0

Small desktop tool that turns a **d&b ArrayCalc project (.dbpr)** or an **L-Acoustics Soundvision
report (.pdf)** into the hoist CSV used by ACHOISTS (AutoCAD) and the Vectorworks placement scripts.

## Using it
1. Start `Pick-up point extractor v1.0.exe`. You can also drop a file onto the exe to pre-fill it.
2. **Browse…** to a `.dbpr` or `.pdf` file, then press **Extract** (or Enter).
3. The status line shows the result, for example
   `Done: 40 pick-up points (10 sources) -> Bishkek Arena Vi Fest v2_hoist_picks.csv`.
   The CSV is saved **next to the input file** as `<input name>_hoist_picks.csv`. An existing
   CSV with that name is overwritten. If that CSV is open in another program (e.g. Excel), the
   tool saves `<name>_hoist_picks (2).csv` instead and says so.

"Pick-up points" counts the hoists that will be placed by default, i.e. front + rear picks.
Optional single-point alternatives are in the CSV but are not counted.
On failure the status shows a short reason. Only an unexpected crash writes
`<input name>_extractor_error.log` next to the input.

The file type is detected from the file contents (SQLite → ArrayCalc, %PDF → Soundvision), so a
wrong extension does not matter.

## What is extracted
- **ArrayCalc:** flown sources only, front + rear picks plus the optional single pick
  (same output as `extract_arraycalc_hoists.py`).
- **Soundvision:** flown sources with motors. A 2-motor source gives front + rear rows; a
  1-motor source gives one front row plus an identical "single" row. Metres and kg only.
  (Same output as `extract_soundvision_hoists.py`.)

13 columns: `source, pick_kind, x_m, y_m, z_m, hole, weight_kg, total_weight_kg, system,
horizontal_aiming_deg, flying_frame_id, source_group_id, single_available`.

## Resource use (measured on BELOVWORK3, i9-13900HX, Windows 11, v1.0 onefile build)
- exe: 11.8 MB (onefile, no UPX)
- window on screen about 0.28 s after launch
- idle: 0 ms CPU over 10 s; about 43 MB working set (34 MB app + 8 MB onefile launcher), 19 MB private
- extracting the 48-page Soundvision sample: 0.46 s, peak working set 55 MB (app process)
- ArrayCalc sample: peak 25 MB (CLI mode)

The window is event-driven: no timers, polling or background threads. The path field uses a
steady (non-blinking) caret, because a blinking caret wakes the process about 3 times a second.
pypdf and sqlite3 are only loaded when you press Extract.

onefile vs onedir: onefile unpacks to %TEMP% on every start. That adds about 0.16 s before the window
appears, plus about 0.4 s of cleanup after it closes, which you don't see. onedir is a 22 MB folder
of 62 files. onefile is shipped because it is a single file.

## Source layout
```
src/app.py                         Tk window + hidden test flags (--cli, --version-json, --demo)
src/core.py                        type detection, extraction, CSV writing (no GUI, cross-platform)
src/extract_arraycalc_hoists.py    ArrayCalc extractor (also runs stand-alone)
src/extract_soundvision_hoists.py  Soundvision extractor (also runs stand-alone)
src/version.py                     name / version
src/_diag.py                       peak-memory readout for --cli tests only
packaging/windows/version_info.txt exe version resource
packaging/macos/build_macos.sh     macOS universal2 .app + .dmg
tests/                             core checks + Soundvision parser checks
build_windows.ps1                  Windows build
```

## Building
Windows (uses its own venv in `_build\.venv`, so the global Python is not touched):
```
powershell -ExecutionPolicy Bypass -File build_windows.ps1            # onefile exe
powershell -ExecutionPolicy Bypass -File build_windows.ps1 -OneDir    # onedir, for comparison
```
macOS, from the `extractor/` directory (the script finds its own root):

```
bash packaging/macos/build_macos.sh
```

Needs a **python.org universal2** Python 3.12+ (or `actions/setup-python`, which installs that build). Its Tcl/Tk is 8.6. Apple's system Tk, and the old Intel-only python.org Tk 8.6.8, draw a black window on current macOS, so the script refuses anything older than Tk 8.6 and refuses a single-architecture interpreter. Set `PYTHON` if `python3` is not that install.

One `.dmg` is a universal2 app (Apple Silicon and Intel). pypdf is pure Python, so there is no native wheel to merge, and a second Intel runner is not required. The `.app` is onedir (`--windowed`), not onefile: a macOS app bundle does not suit a onefile unpack-to-temp layout. The Windows exe stays onefile.

The app is **ad-hoc signed** (`codesign --sign -`). There is no Apple Developer ID, so Gatekeeper will block the first open after the `.dmg` is downloaded. Control-click **Pick-up point extractor** and choose **Open**, then Open again in the dialog. After that it launches normally. The same unsigned-download warning on Windows is SmartScreen; the exe is not Authenticode-signed.

Built with the python.org 3.13 universal2 installer, the app's minimum macOS is **10.13** on Intel and **11** on Apple Silicon. python.org warns that on **macOS 27** Tk file dialogs can hang; CI builds on macOS 26.

Do not add `email` or `urllib` to the PyInstaller excludes on either platform. On Python 3.14 (Windows), `Path.as_uri()` (used to open the .dbpr read-only) imports them.

Requirements: Python 3.10+ with tkinter, `pypdf`; `pyinstaller` for building
(versions pinned in `requirements*.txt`). UPX is deliberately not used, to avoid antivirus false positives.

## Tests
```
python tests/test_core.py                      # bad/corrupt inputs, counting
set PPE_SAMPLES=<folder>  &  python tests/test_core.py   # + byte-for-byte check vs reference CSVs
python tests/soundvision_parser_checks.py      # Soundvision wording / units edge cases
python tests/check_window_bmp.py --self-test   # blank-window screenshot checker
python tests/smoke_frozen.py --exe "Pick-up point extractor v1.0.exe"
"Pick-up point extractor v1.0.exe" --cli <file> --report result.json   # frozen build, no window
.\tests\test_frozen_windows.ps1 -Exe <exe> -Sample "a.dbpr=ref.csv",...   # exe vs reference CSVs + broken files
.\tests\measure_windows.ps1 -Exe <exe> [-OneDirExe <exe>] -DemoFile <pdf>  # startup / RAM / CPU
```

GitHub Actions (`.github/workflows/build.yml`) runs the pure-Python tests and a frozen `--cli` / `--version-json` smoke test on macOS and Windows. On macOS it also screenshots the real window and rejects a blank image. The workflow runs on `workflow_dispatch` and on tags `v*`. A tag run attaches the `.dmg` and the `.exe` to the GitHub Release. Client samples are not in the repo; the smoke test uses a synthetic `.dbpr` and a synthetic PDF.
