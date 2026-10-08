# ArrayCalc hoists → AutoCAD 2025 (`ACHOISTS`)

This is the AutoCAD version of `vw-scripts/PlaceArrayCalcHoists.py`. It reads the CSV made by
`vw-scripts/extract_arraycalc_hoists.py` (or `Extract ArrayCalc Hoists.bat`) and places one hoist
block for each pick point, at the hoist's real X, Y **and Z**.

## Files
| File | What it is |
|---|---|
| `PlaceArrayCalcHoists.lsp` | The tool (UTF-8). Command **`ACHOISTS`** |
| `HoistPoint.dwg` | The hoist symbol, drawn in mm: circle, two solid quarters, crosshair, attributes `PT-NAME` (department) and `LOAD` (weight). It's loaded into the drawing as block **`точка`** |
| `dev/` | Only needed to rebuild the block or re-test: `make_block.lsp`, the original DWG from your friend, `test_core.lsp`, `test_layout.lsp` |

Keep `HoistPoint.dwg` in the same folder as the `.lsp`.

## Loading
* **Once:** `APPLOAD` → pick `PlaceArrayCalcHoists.lsp` → **Load**.
* **Always:** `APPLOAD` → **Startup Suite → Contents… → Add…** → the `.lsp` file.
  If AutoCAD shows a security prompt, choose "Always load", or add this folder under
  Options → Files → **Trusted Locations** (and **Support File Search Path**, which lets the tool
  always find `HoistPoint.dwg`).

## Workflow
1. In ArrayCalc, save the project, then run `Extract ArrayCalc Hoists.bat` → `<project>_hoist_picks.csv`.
2. In AutoCAD, type `ACHOISTS` and pick the CSV. The file picker opens in the drawing's folder, or at the last CSV you used.
3. The dialog:
   * **Single-point**: tick a source only if it really hangs from one point. The box is greyed out
     when ArrayCalc has no single pick for that source. Everything else gets front + rear.
   * **Label layout** (applies to every source whose Labels column says `as layout`):
     * **Left / right (auto-mirror close pairs)**: the original look. `Sound` and the weight sit to the
       right of the symbol, and the lower-X hoist of a close front/rear pair is mirrored to the left.
     * **Top / bottom (name above, weight below)**: `Sound` is centred above the symbol and the weight is centred
       below it, about 60 mm clear of the crosshair at scale 1. This fixes the SUBS LR1/LR2 overlap.
       Front/rear pairs that are too close for stacked labels keep `auto` left/right, which is
       the rings and OUT LR at scale 1. Those pairs are less than one label width (0.85 m × scale) apart
       in X and less than 1.5 m × scale apart in Y. The summary tells you how many pairs did this.
   * **Labels** (per source): `as layout` · `auto L/R` (left/right with mirroring, whatever the layout) ·
     `right` · `left` · `top/bottom` (always top/bottom for this source, never falls back).
     For example, keep the layout on Left / right and set only SUBS LR1 and SUBS LR2 to `top/bottom`.
   * **Solid colour…**: the AutoCAD colour dialog (Index / True Color / Color Books). It colours
     only the two solid quarters. The outline, crosshair and texts follow the layer.
   * **Department text** (default `Sound`, you can type `Звук`), **Weight suffix** (default ` kg`, or ` кг`),
     **Symbol scale** (1 = drawn size, about 0.57 m circle; try 0.5 when hoists are dense).
   * **Rotation (applied before inserting)**:
     * **Rotate layout about 0,0 (degrees, CCW +)**: turns the whole hoist layout around the drawing origin, the
       same as AutoCAD's ROTATE with base point 0,0 (90 = counter-clockwise, -90 or 270 = clockwise).
       Z (hoist height) does not change. This always starts at 0.
     * **Rotate symbols too (labels stay upright)**: when this is ticked, each symbol is also rotated by the angle.
       When it's off (the default), the symbols stay upright. The labels are always upright on the page,
       never upside down. The left/right mirroring and the top/bottom fallback are worked out on the rotated
       positions, so labels still avoid each other after a 90° or 180° turn.
   * **Delete hoist inserts from previous runs**: removes the hoists this tool placed before.
4. Done. A summary lists the count, the unit factor, the single-point sources, and the block and tags used.
   The whole run is one undo step (`U`).

Settings you change in the dialog are remembered. The defaults are at the top of the `.lsp`:
block name, layer, tags, department, suffix, colour, scale.

## How it works
* **Units:** CSV metres × factor from `INSUNITS` (mm ×1000, cm ×100, m ×1, in ÷0.0254 …). If the drawing
  is unitless, the tool asks once on the command line. It never changes `INSUNITS`.
* **Block scale:** the block's units are converted to drawing units (mm block in a metre drawing → 0.001)
  × the symbol scale. The insert rotation is 0, or the dialog angle when "Rotate symbols too" is ticked.
  In both cases the attributes are put back upright on the page.
* **Label positions:** worked out per insert from the block's geometry extents (circle + crosshair)
  × the insert scale, so they fit at symbol scale 0.5, 1 or anything else. Top/bottom uses
  `PT-NAME` justified Center (baseline) and `LOAD` justified Top-Center. Settings at the top of the `.lsp`:
  `*ach:label-layout*`, `*ach:tb-gap-ratio*`, `*ach:tb-fallback*`, `*ach:tb-clear-x-m*`, `*ach:tb-clear-y-m*`.
* **Attributes:** `PT-NAME` = department text, `LOAD` = rounded kg + suffix (664.1 → `664 kg`).
  Inserted through ActiveX, so no attribute prompts appear.
* **Text style:** the attributes always use the block's own style `x-2D_RIG_POINTS$0$RIG_POINTS`
  (TrueType **Arial Narrow**). Each run checks it, and the summary shows `Text style: … (Arial Narrow)`.
  If an attribute ended up on another style, it is put back. If the style's font is missing
  (it would fall back to `simplex.shx`), the style is set back to Arial Narrow (`*ach:text-font*`).
* **Blocky text in 3D views:** in a shaded visual style (Realistic, Shaded…), and especially in perspective,
  AutoCAD turns TrueType text into triangles at the zoom level of the last regen. If you zoom in a long way
  or orbit, the glyphs can look crude or broken until you type **`REGEN`**. This is a display effect,
  not the font: in 2D Wireframe or after `REGEN` the same text is smooth.
* **Colour:** the hatch in the block definition is set to ByBlock, and each insert gets the chosen colour.
  You can run it again with another colour, or use other departments with different colours. Note that a delete-previous run
  removes all earlier ACHOISTS inserts, whatever their department.
* **Layer** `AC_HOISTS` (created white if it's missing; turned on, thawed and unlocked if needed).
* **Rerun cleanup:** inserts carry xdata `ACHOISTS` (source, pick, frame id, kg). Inserts of the hoist
  block on `AC_HOISTS` are also treated as "previous".
* **For scripts** (no dialog):
  * `(achoists-run "C:/path/file.csv" '("RING 1") 1 "Sound" " kg" T)`: as before. It uses `*ach:label-layout*` (default left/right).
  * `(achoists-run-layout "C:/path/file.csv" nil 1 "Sound" " kg" T "topbottom")`: the same with an explicit layout (`"side"` or `"topbottom"`).
  * `(achoists-run-ex CSV SINGLES COLOR DEPT SUFFIX DELETEOLD OPTS)` takes every option. For example:
    `'(("layout" . "topbottom") ("rotation" . 90.0) ("rotate-symbols" . T) ("scale" . 0.5) ("sides" . (("SUBS LR1" . "topbottom"))))`.
