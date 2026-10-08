# Pick-up point extractor

A utility to extract pickup points from an L-Acoustics Soundvision report or a d&b ArrayCalc project, and scripts for Vectorworks and AutoCAD that place those points and mark loads.

## extractor/

Desktop app, "Pick-up point extractor". Python 3 and Tkinter. It reads an ArrayCalc project (`.dbpr`, SQLite) or a Soundvision report (`.pdf`) and writes `<name>_hoist_picks.csv` next to that file.

Builds: a Windows onefile `.exe`, and a macOS universal2 `.app` inside `Pick-up point extractor v1.0.dmg`. Details are in `extractor/README.md`.

The macOS app is ad-hoc signed (there is no Apple Developer ID). The first time you open it after a download, Control-click the app and choose **Open**.

## autocad/

AutoCAD 2025 AutoLISP command `ACHOISTS` (`PlaceArrayCalcHoists.lsp`) and the `HoistPoint.dwg` block. See `autocad/README.md`.

## vectorworks/

Vectorworks 2026 Python scripts that place the hoists from the CSV. See `vectorworks/README.md`.

Client projects (`.dbpr`, `.pdf`) and generated CSVs are not in this repository.
