# Pick-up point extractor + hoist placement scripts

*Made with the help of Grok models.*

Video tutorial: https://www.youtube.com/watch?v=_y_PgrNg_jc

The workflow:
1. **Extract.** Run **Pick-up point extractor** and pick a d&b ArrayCalc project (`.dbpr`) or an L-Acoustics Soundvision report (`.pdf`). It saves a `..._hoist_picks.csv` next to that file.
2. **Place.** In Vectorworks or AutoCAD, run the placement script and choose that CSV. Hoists are placed at their pick-up positions and heights, with weight marks.

## Release files

| File | Used for |
|---|---|
| `Pick-up point extractor v1.0.exe` | Windows extractor |
| `Pick-up point extractor v1.0.dmg` | macOS extractor (Apple Silicon and Intel, macOS 11+) |
| `PlaceArrayCalcHoistsV3.py` | Vectorworks 2026 placement script |
| `Sound_Hoist_Class.vwx` | Vectorworks data tag style "Sound_Hoist" used by the script |
| `PlaceArrayCalcHoists.lsp` | AutoCAD placement script for Windows and Mac (commands `ACHOISTS`, `ACHOISTS_CLI`) |
| `HoistPoint.dwg` | AutoCAD hoist block used by the script; keep it next to the `.lsp` |

---

## 1. Pick-up point extractor

**Windows:** run the `.exe`. If Windows shows "Windows protected your PC", click **More info**, then **Run anyway**. This happens because the program isn't signed.

**macOS:**
1. Open the `.dmg` and drag **Pick-up point extractor** into **Applications**.
2. Open **Terminal** and run:
   ```
   xattr -cr "/Applications/Pick-up point extractor.app"
   ```
3. Open the app from Applications.

The command clears the "downloaded from the internet" flag, which otherwise makes macOS say the app can't be opened. Don't run it on the mounted disk image: you'll get "Read-only file system" errors.

---

## 2. Vectorworks 2026 (Windows and macOS)

### Install the data tag style
Copy `Sound_Hoist_Class.vwx` into your user library folder:

- **Windows:** `C:\Users\<you>\AppData\Roaming\Nemetschek\Vectorworks\2026\Libraries\Annotations\Data Tag (styles)\`
- **macOS:** `~/Library/Application Support/Vectorworks/2026/Libraries/Annotations/Data Tag (styles)/`

These are the default user folders. If you moved yours, check **Vectorworks Preferences › User Folders** (Mac: **Vectorworks › Preferences**; Windows: **Tools › Options › Vectorworks Preferences**). Create any missing subfolders. On macOS, press **Cmd+Shift+.** in Finder to show the hidden `Library` folder.

Then, in the Resource Manager, right-click **User Libraries** and choose **Refresh**.

### Add the script as a menu command
1. Go to **Tools › Plug-ins › Plug-in Manager**, open the **Custom Plug-ins** tab, click **New…**, choose **Command** and name it `PlaceArrayCalcHoistsV3`.
2. Select it, click **Edit Script…**, choose **Python** as the language, paste the whole contents of `PlaceArrayCalcHoistsV3.py`, and click OK.
3. Go to **Tools › Workspaces › Workspaces**, select your workspace and click **Edit**. On the **Menus** tab, find the command in the list on the left (under Miscellaneous or the category you chose) and drag it into a menu on the right.

When a new version of the script comes out, paste the new code into the same command (**Edit Script…**). Updating the `.py` file alone does nothing.

### Use it
Run the command, pick the CSV, choose the options and click **Place**:
- **Data tag style:** default `Sound_Hoist`.
- **Quarter colour:** sets the class `Hoist_Quarters`.
- **Lift tags to hoist height:** on by default.
- **Replace hoists + tags from earlier runs.**
- **Single-point:** tick only the sources that hang from a single point.

If the summary says the style was **NOT FOUND**, import `Sound_Hoist` with the Resource Manager and run the script again. If a drawing has an old copy of `Sound_Hoist` in its resources, delete it first so the script imports the current one.

---

## 3. AutoCAD (Windows and Mac)

Tested on AutoCAD 2025 for Windows and AutoCAD for Mac 2024/2025. It's one script for both systems.

### Install
1. Put `PlaceArrayCalcHoists.lsp` and `HoistPoint.dwg` in the same folder, for example `C:\AutoCAD Hoists\` or, on Mac, `~/AutoCAD Hoists/`. On a Mac, keep it **outside Desktop and Documents** (macOS restricts app access to them). Otherwise allow access in **System Settings › Privacy & Security › Files & Folders** by turning on Desktop/Documents for AutoCAD.
2. Add that folder to **Trusted Locations** (below).

### Trusted Locations
AutoCAD only loads code from trusted folders without complaint. Without this, you get a security warning on load, or loading fails with `LOAD failed`.

- **Windows:** type `OPTIONS` › **Files** tab › expand **Trusted Locations** › **Add**, then **Browse** to the folder › OK. If AutoCAD warns that the folder isn't read-only, accept it. You can add the same folder under **Support File Search Path** too.
- **Mac:** **AutoCAD › Preferences › Application** tab › **Trusted Locations**, then add the folder.
- **Mac, from the command line:** type `TRUSTEDPATHS` and enter the path, e.g. `/Users/name/AutoCAD Hoists`. End it with `/...` to include subfolders. **The value replaces the existing list**, so if it isn't empty, join the paths with `;`.

### Load it
Type `APPLOAD` (Mac: also **Tools › Load Application**), select `PlaceArrayCalcHoists.lsp` and click **Load**. To load it in every session, click **Contents…** under **Startup Suite**, then **Add…**. This works the same on Windows and Mac.

When it has loaded, the command line shows `ACHOISTS loaded (Windows)` or `ACHOISTS loaded (Mac)`. If you don't see that and `ACHOISTS` doesn't autocomplete, check the trusted folder and folder access.

### Use it
In a millimetre drawing, type `ACHOISTS` and pick the CSV. The dialog lets you choose:
- the label layout (side or top/bottom, per source);
- single-point sources;
- the department text and weight suffix;
- the solid colour, symbol scale and rotation;
- whether to delete earlier hoists.

The hoists are placed on layer `AC_HOISTS` at their heights. Rows without a weight (empty or 0) are skipped and listed in the summary.

**Command-line version:** `ACHOISTS_CLI` asks the same questions as prompts. Use it if the dialog misbehaves (on a Mac it also starts automatically if the dialog can't open). Notes:
- single-point sources: type numbers, e.g. `3,4`;
- colour: type a name such as `green` or a colour number; an unknown name asks again;
- the label layout applies to all sources;
- weight suffix with a leading space: type it in quotes, `" kg"`, or AutoCAD drops the space.

If labels look blocky in a 3D/Realistic view, type `REGEN`.
