# ArrayCalc → Vectorworks Hoists

## Defaults
- **Flown arrays only** (`Mounting = 0` in ArrayCalc). Ground / FF / GND are skipped.
- **Front + rear** pick points per flying frame.
- In Vectorworks, a dialog lists flown sources:
  - **Tick a checkbox only if that source is actually a single-point hang.** Unticked = front + rear.
  - **Per source: Load tags LEFT or RIGHT** (default RIGHT). Use opposite sides for neighbouring hangs that would overlap in Top/Plan.

## 1. Extract pick points (outside Vectorworks)
Double-click `Extract ArrayCalc Hoists.bat` (or run `extract_arraycalc_hoists.py`).
A file picker opens — choose the `.dbpr` even if several share a folder.
CSV is written **next to that project** as `<name>_hoist_picks.csv`.

Or from a terminal:
```bat
python extract_arraycalc_hoists.py
python extract_arraycalc_hoists.py "Bishkek Arena Vi Fest v2.dbpr"
```

## 2. Place hoists (inside Vectorworks 2026)
1. Open `SOUND MOTORS.vwx` (or your venue file). Confirm drawing units match the venue (script converts metres → document units).
2. **Tools → Plug-ins → Run Script…** and choose `PlaceArrayCalcHoists.py`.
3. Confirm checkboxes (leave all clear for front+rear).
4. Click **Place**.

Hoists are created as Spotlight/Braceworks `Hoist` (`BrxHoist`) objects at ArrayCalc XY, with **insertion Z** set from ArrayCalc frame/origin height. Pick loads (kg) get a short leader + text mark beside each point, and are written into Function / name / `ArrayCalc Pick` record.

## Notes
- Align your Vectorworks origin / axes with ArrayCalc before placing (same zero and X/Y directions).
- Symbol / capacity still use the Hoist tool defaults — change via OIP after place, or we can extend the script.
- Re-run the extractor after ArrayCalc changes, then run the placer again (or delete previous ArrayCalc-named hoists first).
