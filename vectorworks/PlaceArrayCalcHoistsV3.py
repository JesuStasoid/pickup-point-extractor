# Place ArrayCalc Hoists V3
# Vectorworks 2026 Python - Tools > Plug-ins > Run Script... / workspace menu
#
# Reads the hoist CSV written by the ArrayCalc / Soundvision extractors
# (or "Pick-up point extractor v1.0"), all values in metres / kg.
#
# V3 compared with V2:
#   * No own load marks / leaders any more. Each hoist gets a Vectorworks
#     DATA TAG with the style chosen in the dialog (default "Sound_Hoist").
#     The tag's dynamic text reads #ArrayCalc Pick#.#Load Text# from the hoist.
#   * Hoists are always lifted to the CSV height (z_m), like V1.
#   * Optional fill colour for class "Hoist_Quarters" (the tag's filled
#     quarters must be set to fill By Class for this to show).
#     Colour is set with the Python form vs.SetClFillFore(cls, (r, g, b))
#     (0-65535) and read back with GetClFillFore; the summary shows the values.
#   * Tag size: script-created tags came out page-based (layout size x layer
#     scale). Each tag gets the world-based flag forced on (or the settings of
#     a tag placed with the Data Tag tool, if one is in the drawing); the first tag is measured, and if the size did not drop by the layer
#     scale the script falls back to Scaling Symmetric, Factor = 1/layer scale.
#     All Data Tag parameters of the first tag are listed in the summary.
#   * Optional (off by default): "Lift tags to hoist height" puts each tag on
#     its own horizontal 3D plane at its hoist's Z (SetEntityMatrix), like the
#     Data Tag tool does in a 3D view. Check DWG export when using it.
#   * Data tags are NOT lifted: they stay normal planar annotations on the
#     layer plane at the hoist's X/Y (V2 showed that lifted 2D marks vanish in
#     DWG export).
#   * If the tag style is not in the drawing, it is imported from the user
#     library folder ...\Libraries\Annotations\Data Tag (styles)\*.vwx.
#
# Re-running: "Replace hoists + tags from earlier runs" (on by default) removes
#   - hoists from earlier runs (hoist objects carrying the 'ArrayCalc Pick'
#     record) and the tags this script placed ("AC Tag ..."),
#   - leftover V2 load marks ("AC Load ..." objects + "AC Load Mark ..." symbols).
#
# UNTESTED IN VECTORWORKS - checked only with a mocked `vs` module.

import csv
import os

import vs

SCRIPT_TITLE = "Place ArrayCalc Hoists V3"
HOIST_PIO_CANDIDATES = ("Hoist", "BrxHoist")
RECORD_NAME = "ArrayCalc Pick"
DATA_TAG_PIO = "Data Tag"
DEFAULT_TAG_STYLE = "Sound_Hoist"
TAG_NAME_PREFIX = "AC Tag "
V2_MARK_PREFIX = "AC Load"
V2_MARK_SYMBOLS = ("AC Load Mark Right", "AC Load Mark Left",
                   "AC Load Mark Above", "AC Load Mark Below")
# Plug-in styles live in the resource list as symbol definitions (type 16)
RES_TYPE_SYMBOL = 16
# Vectorworks folder index for "Libraries"; negative = the user's folder
FOLDER_LIBRARIES = 13
DATA_TAG_LIB_SUBFOLDER = os.path.join("Annotations", "Data Tag (styles)")
T_PLUGIN_OBJECT = 86

# Fill colour for the tag quarters (class fill, RGB 0-65535 per channel)
QUARTERS_CLASS = "Hoist_Quarters"
KEEP_COLOR = "Keep current"
COLOR_CHOICES = [
    (KEEP_COLOR, None),
    ("Red", (65535, 0, 0)),
    ("Orange", (65535, 32896, 0)),
    ("Yellow", (65535, 65535, 0)),
    ("Green", (0, 49344, 0)),
    ("Cyan", (0, 65535, 65535)),
    ("Blue", (0, 0, 65535)),
    ("Magenta", (65535, 0, 65535)),
    ("White", (65535, 65535, 65535)),
    ("Black", (0, 0, 0)),
    ("Grey", (32896, 32896, 32896)),
]
FILL_SOLID = 1  # fill pattern index 1 = solid (Appendix E: 1 solid back, 2 solid fore)

# Tag size check / correction
# Data Tag parameter names seen in Vectorworks 2026 Plug-ins\DataTag.vlb / .vwr
# (not documented; the script also lists the real field names in the summary)

# Dialog item ids
K_TITLE = 10
K_HELP = 11
K_FILE_LABEL = 13
K_TAG_CHECK = 20
K_STYLE_LABEL = 21
K_STYLE_EDIT = 22
K_IDLABEL_CHECK = 24
K_REPLACE_CHECK = 26
K_COLOR_LABEL = 28
K_COLOR_MENU = 29
K_FIT_CHECK = 30
K_SCALE_LABEL = 32
K_SCALE_EDIT = 33
K_LIFT_CHECK = 34
K_CHECK_START = 100

# ---------------------------------------------------------------------------
# Error collection: every vs call goes through vcall()
# ---------------------------------------------------------------------------
ERRORS = []
MAX_ERRORS_SHOWN = 12

# Calls suspected of the native crash in b420d24a - OFF unless proven safe.
USE_UPDATE_PIO_FROM_STYLE = False   # vs.UpdatePIOFromStyle: Python form takes NO handle (VAR param)
READ_STYLE_SYMBOL = False           # read world-based value from the style's symbol definition

# Crash breadcrumbs: one line per step, file opened/flushed/closed every time,
# so after a hard crash V3_run_log.txt shows the last step reached.
RUN_LOG = None
CRUMB_VERBOSE = False
CRUMB_ALWAYS = {"ForEachObject", "DelObject", "DT_ResetAllDataTags", "UpdatePIOFromStyle",
                "FInSymDef", "GetLScale", "GetLayer", "GetPluginStyle", "ImportResourceToCurrentFile",
                "BuildResourceListN", "SetClFillFore", "SetClFillBack", "NameClass"}


def crumb(msg):
    if not RUN_LOG:
        return
    try:
        import time
        with open(RUN_LOG, "a", encoding="utf-8") as fh:
            fh.write(time.strftime("%H:%M:%S ") + str(msg) + "\n")
            fh.flush()
            os.fsync(fh.fileno())
    except Exception:
        pass


def log_error(msg):
    ERRORS.append(str(msg))


def vcall(fname, *args, **kw):
    """Call vs.<fname>(*args). On failure log it (unless quiet) and return default."""
    default = kw.get("default")
    quiet = kw.get("quiet", False)
    fn = getattr(vs, fname, None)
    if CRUMB_VERBOSE or fname in CRUMB_ALWAYS:
        crumb(f"  vs.{fname}{_short_args(args)}")
    if fn is None:
        if not quiet:
            log_error(f"vs.{fname} is not available in this Vectorworks version")
        return default
    try:
        return fn(*args)
    except Exception as e:  # noqa: BLE001 - we want every failure reported
        if not quiet:
            log_error(f"vs.{fname}{_short_args(args)} failed: {e}")
        return default


def _short_args(args):
    out = []
    for a in args:
        s = repr(a)
        out.append(s if len(s) <= 30 else s[:27] + "...")
    return "(" + ", ".join(out) + ")"


def valid(h):
    if h is None:
        return False
    try:
        return vs.GetTypeN(h) > 0
    except Exception:
        return False


def same_handle(a, b):
    try:
        return a == b
    except Exception:
        return False


# ---------------------------------------------------------------------------
# Units and CSV (unchanged from V2)
# ---------------------------------------------------------------------------
def m_to_doc(meters):
    """Metres -> current document length units via GetUnits() upi."""
    units = vcall("GetUnits", default=None)
    upi = 25.4  # fallback: millimetre document
    try:
        upi = float(units[3])
    except Exception:
        log_error("GetUnits gave no units-per-inch; assuming millimetres")
    return float(meters) / 0.0254 * upi


def document_unit_info():
    units = vcall("GetUnits", default=None)
    try:
        return units[4] or "?", float(units[3])
    except Exception:
        return "?", 25.4


def side_label(y_m):
    return "R" if float(y_m) >= 0 else "L"


def pick_letter(kind):
    return {"front": "F", "rear": "R", "single": "S"}.get(kind, kind[:1].upper())


def format_load_kg(weight_kg):
    if weight_kg in (None, ""):
        return None
    try:
        w = float(weight_kg)
    except Exception:
        return None
    if w <= 0:
        return None
    if abs(w - round(w)) < 0.05:
        return f"{int(round(w))} kg"
    return f"{w:.1f} kg"


def read_csv(path):
    with open(path, newline="", encoding="utf-8-sig") as f:
        rows = list(csv.DictReader(f))
    if not rows:
        raise ValueError("CSV is empty")
    missing = [c for c in ("source", "pick_kind", "x_m", "y_m") if c not in rows[0]]
    if missing:
        raise ValueError("CSV is missing column(s): " + ", ".join(missing))
    # Skip empty picks (no real weight, e.g. weight -1 at 0,0 from empty
    # Soundvision/ArrayCalc frames) so no blank hoists land at the origin.
    del SKIPPED_ROWS[:]
    kept = []
    for r in rows:
        if format_load_kg(r.get("weight_kg")) is None:
            SKIPPED_ROWS.append(f"{r.get('source', '?')} {r.get('pick_kind', '?')} "
                                f"(frame {r.get('flying_frame_id', '?')}, weight {r.get('weight_kg', '')})")
        else:
            kept.append(r)
    if not kept:
        raise ValueError("CSV has no picks with a weight")
    return kept


SKIPPED_ROWS = []


def unique_sources(rows):
    seen = []
    meta = {}
    for r in rows:
        src = r["source"]
        if src not in meta:
            seen.append(src)
            meta[src] = {
                "single_available": str(r.get("single_available", "0")) in ("1", "true", "True"),
                "system": r.get("system") or "",
            }
        elif str(r.get("single_available", "0")) in ("1", "true", "True"):
            meta[src]["single_available"] = True
    return seen, meta


def filter_rows(rows, single_sources):
    out = []
    for r in rows:
        src = r["source"]
        kind = r["pick_kind"]
        if src in single_sources:
            if kind == "single":
                out.append(r)
        else:
            if kind in ("front", "rear"):
                out.append(r)
    return out


def _file_dialog_result(ok):
    if isinstance(ok, tuple):
        if len(ok) >= 2 and ok[0] in (True, 1):
            return ok[1]
        if len(ok) == 1 and isinstance(ok[0], str) and ok[0]:
            return ok[0]
        return None
    if isinstance(ok, str) and ok:
        return ok
    return None


def choose_csv_path():
    doc = vcall("GetFName", default="") or ""
    folder = ""
    full = vcall("GetFPathName", default="", quiet=True)
    if full:
        folder = os.path.dirname(full)

    candidates = []
    if folder:
        for name in (
            "hoist_pick_points_flown.csv",
            "hoist_pick_points.csv",
            os.path.splitext(os.path.basename(doc))[0] + "_hoist_picks.csv",
        ):
            candidates.append(os.path.join(folder, name))
        try:
            for fn in sorted(os.listdir(folder)):
                low = fn.lower()
                if low.endswith("_hoist_picks.csv") or low == "hoist_pick_points_flown.csv":
                    p = os.path.join(folder, fn)
                    if p not in candidates:
                        candidates.append(p)
        except Exception:
            pass

    for p in candidates:
        if os.path.isfile(p):
            return p
    return pick_csv_manually()


def pick_csv_manually():
    ok = vcall("GetFileN", "ArrayCalc / Soundvision hoist CSV", "", "csv", default=None)
    return _file_dialog_result(ok)


# ---------------------------------------------------------------------------
# Record + hoist (V2 behaviour)
# ---------------------------------------------------------------------------
def ensure_arraycalc_record():
    """Create the 'ArrayCalc Pick' record format if missing (same fields as V1/V2)."""
    if valid(vcall("GetObject", RECORD_NAME, quiet=True)):
        return True
    vcall("NewField", RECORD_NAME, "Source", "", 4, 0)  # 4 = text
    vcall("NewField", RECORD_NAME, "Pick", "", 4, 0)
    vcall("NewField", RECORD_NAME, "Load kg", "0", 1, 0)  # 1 = integer (as in V1/V2)
    vcall("NewField", RECORD_NAME, "Load Text", "", 4, 0)
    vcall("NewField", RECORD_NAME, "Hole", "", 4, 0)
    vcall("NewField", RECORD_NAME, "System", "", 4, 0)
    return valid(vcall("GetObject", RECORD_NAME, quiet=True))


def attach_arraycalc_record(h, row, load_text):
    vcall("SetRecord", h, RECORD_NAME)

    def sf(field, value):
        vcall("SetRField", h, RECORD_NAME, field, str(value))

    sf("Source", row.get("source") or "")
    sf("Pick", row.get("pick_kind") or "")
    w = row.get("weight_kg")
    if w not in (None, ""):
        try:
            # 'Load kg' is an Integer field: write a whole number
            sf("Load kg", str(int(round(float(w)))))
        except Exception:
            sf("Load kg", str(w))
    sf("Load Text", load_text or "")
    sf("Hole", row.get("hole") if row.get("hole") is not None else "")
    sf("System", row.get("system") or "")


def record_load_text(h):
    return vcall("GetRField", h, RECORD_NAME, "Load Text", default="", quiet=True) or ""


def set_hoist_fields(h, pio_name, hoist_id, hoist_name, load_text, notes, show_id_label):
    # Internal parameter names are not documented; V2 tried both spellings.
    def setf(field, value):
        vcall("SetRField", h, pio_name, field, str(value), quiet=True)

    setf("Param_HoistID", hoist_id)
    setf("Param_HoistName", hoist_name)
    setf("HoistID", hoist_id)
    setf("Hoist Name", hoist_name)
    setf("Param_Notes", notes)
    setf("Notes", notes)
    if load_text:
        setf("ParamFunction", load_text)
        setf("Function", load_text)
    flag = "True" if show_id_label else "False"
    setf("Param_ShowLabel", flag)
    setf("Show ID label", flag)


def create_hoist(x_doc, y_doc):
    for name in HOIST_PIO_CANDIDATES:
        h = vcall("CreateCustomObject", name, float(x_doc), float(y_doc), 0.0, quiet=True)
        if not valid(h):
            h = vcall("CreateCustomObject", name, (float(x_doc), float(y_doc)), 0.0, quiet=True)
        if valid(h):
            return h, name
    log_error(f"Could not create a hoist object ({' / '.join(HOIST_PIO_CANDIDATES)}) "
              f"at {x_doc:.0f}, {y_doc:.0f}")
    return None, None


# ---------------------------------------------------------------------------
# Hoist height (from V1, with the official GetSymLoc3D read-back)
# ---------------------------------------------------------------------------
def get_object_z(h):
    """Z of a plug-in object's insertion point (doc units), or None."""
    loc = vcall("GetSymLoc3D", h, default=None, quiet=True)
    try:
        if isinstance(loc, (list, tuple)):
            if len(loc) == 3 and not isinstance(loc[0], (list, tuple)):
                return float(loc[2])
            if len(loc) >= 1 and isinstance(loc[0], (list, tuple)) and len(loc[0]) >= 3:
                return float(loc[0][2])
    except Exception:
        pass
    # Fallback: plane matrix (Python returns ok, (x, y, z), rotX, rotY, rotZ)
    mat = vcall("GetEntityMatrix", h, default=None, quiet=True)
    try:
        if isinstance(mat, (list, tuple)) and len(mat) >= 2 and isinstance(mat[1], (list, tuple)):
            return float(mat[1][2])
    except Exception:
        pass
    return None


def set_hoist_z(h, z_m):
    """Lift the HOIST to z_m (metres, relative to its layer). Never used on tags."""
    z_doc = m_to_doc(z_m)
    # As in V1: make sure the hoist is a layer-plane object, not screen-plane
    vcall("SetObjectVariableBoolean", h, 1160, False, quiet=True)
    vcall("SetPlanarRef", h, -1, quiet=True)  # -1 = layer plane
    cur = get_object_z(h)
    if cur is None:
        cur = 0.0
    dz = z_doc - cur
    if abs(dz) > 1e-6:
        vcall("Move3DObj", h, 0.0, 0.0, dz)
    after = get_object_z(h)
    if after is None:
        return None  # could not verify
    return abs(after - z_doc) <= max(1.0, abs(z_doc) * 1e-6)


# ---------------------------------------------------------------------------
# Optional: lift a DATA TAG to its hoist's height. Same thing the Data Tag tool
# does in a 3D view (tag goes on the active plane): the tag is put on a
# horizontal plane at Z via the documented Python form
#   vs.SetEntityMatrix(h, (x, y, z), rotX, rotY, rotZ)
# No SetPlanarRefIDToGround (documented for use inside plug-in objects only),
# no Move3DObj on the tag.
# ---------------------------------------------------------------------------
def _plane_z(h):
    mat = vcall("GetEntityMatrix", h, default=None, quiet=True)
    try:
        if isinstance(mat, (list, tuple)) and len(mat) >= 2 and isinstance(mat[1], (list, tuple)):
            return float(mat[1][2])
    except Exception:
        pass
    return None


def lift_tag(tag, z_doc, x_doc, y_doc, hoist_id):
    """Returns (ok, text)."""
    crumb(f"lift {hoist_id}: plane z before={_plane_z(tag)} -> {z_doc:g}")
    if not hasattr(vs, "SetEntityMatrix"):
        return False, "vs.SetEntityMatrix not available"
    h_before = tag_height(tag)
    ok = vcall("SetEntityMatrix", tag, (0.0, 0.0, float(z_doc)), 0.0, 0.0, 0.0, default=False)
    vcall("ResetObject", tag)
    z_after = _plane_z(tag)
    recenter_tag(tag, x_doc, y_doc)
    h_after = tag_height(tag)
    crumb(f"lift {hoist_id}: SetEntityMatrix -> {ok}, plane z after={z_after}, size {h_before} -> {h_after}")
    if z_after is None or abs(z_after - float(z_doc)) > max(1.0, abs(float(z_doc)) * 1e-6):
        # did not take: put the tag back on the layer plane, like before
        vcall("SetPlanarRef", tag, -1, quiet=True)
        vcall("ResetObject", tag, quiet=True)
        recenter_tag(tag, x_doc, y_doc)
        return False, f"plane z read back {z_after} (wanted {z_doc:g}) - left on layer plane"
    if h_before and h_after and abs(h_after / h_before - 1.0) > 0.05:
        return True, f"lifted, but size changed {h_before:g} -> {h_after:g}"
    return True, "ok"


# ---------------------------------------------------------------------------
# Data tag style: find in drawing or import from user library
# ---------------------------------------------------------------------------
def user_data_tag_folders():
    folders = []
    lib = vcall("GetFolderPath", -FOLDER_LIBRARIES, default="", quiet=True) or ""
    if lib:
        folders.append(os.path.join(lib, DATA_TAG_LIB_SUBFOLDER))
    appdata = os.environ.get("APPDATA")
    if appdata:
        folders.append(os.path.join(appdata, "Nemetschek", "Vectorworks", "2026",
                                    "Libraries", DATA_TAG_LIB_SUBFOLDER))
    home = os.path.expanduser("~")
    folders.append(os.path.join(home, "Library", "Application Support", "Vectorworks",
                                "2026", "Libraries", DATA_TAG_LIB_SUBFOLDER))  # macOS
    out = []
    for f in folders:
        f = os.path.normpath(f)
        if f not in out and os.path.isdir(f):
            out.append(f)
    return out


def library_vwx_files():
    files = []
    for folder in user_data_tag_folders():
        for root, _dirs, names in os.walk(folder):
            for n in sorted(names):
                if n.lower().endswith(".vwx"):
                    files.append(os.path.join(root, n))
    return files


def style_in_document(style):
    return valid(vcall("GetObject", style, quiet=True))


def _list_and_count(res):
    if isinstance(res, (list, tuple)) and len(res) >= 2:
        return res[0], int(res[1] or 0)
    return res, 0


def import_style(style):
    """Return (ok, message). Looks in every .vwx under the user's
    Libraries\\Annotations\\Data Tag (styles) folder."""
    files = library_vwx_files()
    if not files:
        return False, "no .vwx found in the user Data Tag (styles) library folder"
    seen_names = []
    for path in files:
        res = vcall("BuildResourceListN", RES_TYPE_SYMBOL, path, default=None)
        list_id, n = _list_and_count(res)
        if not list_id or n <= 0:
            continue
        for i in range(1, n + 1):
            name = vcall("GetNameFromResourceList", list_id, i, default="") or ""
            if name and name not in seen_names:
                seen_names.append(name)
            if name != style:
                continue
            h = vcall("ImportResourceToCurrentFile", list_id, i, default=None)
            if style_in_document(style) or valid(h):
                return True, f"imported from {os.path.basename(path)}"
            return False, f"found in {os.path.basename(path)} but the import failed"
    hint = ""
    if seen_names:
        hint = " Resources seen: " + ", ".join(seen_names[:10])
    return False, f"'{style}' not found in {len(files)} library file(s).{hint}"


def ensure_tag_style(style):
    """Return (ok, status text for the summary)."""
    if style_in_document(style):
        return True, "found in this drawing"
    ok, msg = import_style(style)
    if ok:
        return True, msg
    return False, msg


# ---------------------------------------------------------------------------
# Data tag placement (official calls; tag stays on the layer plane)
# ---------------------------------------------------------------------------
def _xy_of(h):
    loc = vcall("GetSymLoc", h, default=None, quiet=True)
    try:
        if isinstance(loc, (list, tuple)):
            if len(loc) >= 2 and not isinstance(loc[0], (list, tuple)):
                return float(loc[0]), float(loc[1])
            if isinstance(loc[0], (list, tuple)):
                return float(loc[0][0]), float(loc[0][1])
    except Exception:
        pass
    return None


def place_tag(hoist, x_doc, y_doc, style, hoist_id):
    """Create a Data Tag at the hoist's X/Y, apply the style, associate it."""
    tag = vcall("CreateCustomObjectN", DATA_TAG_PIO, (float(x_doc), float(y_doc)), 0.0, False,
                quiet=True)
    if not valid(tag):
        tag = vcall("CreateCustomObjectN", DATA_TAG_PIO, float(x_doc), float(y_doc), 0.0, False)
    if not valid(tag):
        log_error(f"{hoist_id}: could not create a '{DATA_TAG_PIO}' object")
        return None
    if not vcall("SetPluginStyle", tag, style, default=False):
        log_error(f"{hoist_id}: SetPluginStyle('{style}') returned False")
    vcall("SetName", tag, TAG_NAME_PREFIX + hoist_id, quiet=True)
    if not vcall("DT_AssociateWithObj", tag, hoist, default=False):
        log_error(f"{hoist_id}: DT_AssociateWithObj returned False (tag placed but not linked)")
    update_from_style(tag)
    # Script-made tags start with the plug-in's default leader (Use Leader=True,
    # shoulder 15), unlike tool-placed tags that follow the style (no leader).
    # The leader shoulder pushes the tag body ~15 mm sideways, so switch it off.
    # (No X/Y Offset is written here.)
    vcall("SetRField", tag, DATA_TAG_PIO, "Use Leader", "False", quiet=True)
    crumb(f"{hoist_id}: Use Leader -> False")
    vcall("ResetObject", tag)
    vcall("DT_UpdateTaggedTags", hoist, quiet=True)
    recenter_tag(tag, x_doc, y_doc)
    return tag


def update_from_style(tag):
    """Only when USE_UPDATE_PIO_FROM_STYLE is switched on (off: suspected crash)."""
    if USE_UPDATE_PIO_FROM_STYLE and hasattr(vs, "UpdatePIOFromStyle"):
        vcall("UpdatePIOFromStyle", tag, quiet=True)


def recenter_tag(tag, x_doc, y_doc):
    """Keep the tag centred on the hoist in plan (offset 0,0). Planar move only:
    no Z, no entity matrix, so the tag stays a normal layer-plane annotation."""
    xy = _xy_of(tag)
    if xy is not None:
        dx, dy = float(x_doc) - xy[0], float(y_doc) - xy[1]
        if abs(dx) > 0.5 or abs(dy) > 0.5:
            vcall("HMove", tag, dx, dy)
            vcall("ResetObject", tag, quiet=True)


# ---------------------------------------------------------------------------
# Tag size: script-made tags can come out page-based (size x layer scale) even
# when the style is world-based. Force the style's world-based setting onto
# each tag, check, and fall back to Factor = 1/layer scale if that didn't work.
# ---------------------------------------------------------------------------
def tag_height(tag):
    """Height of the tag's bounding box in document units (circle diameter)."""
    bb = vcall("GetBBox", tag, default=None, quiet=True)
    try:
        (x1, y1), (x2, y2) = bb[0], bb[1]
        return abs(float(y1) - float(y2))
    except Exception:
        return None


def tag_param_info(tag):
    """(PIO record name, [field names]) of the Data Tag's parameter record."""
    rec = vcall("GetParametricRecord", tag, default=None, quiet=True)
    if rec is None:
        return "", []
    pio = vcall("GetName", rec, default="", quiet=True) or ""
    n = vcall("NumFields", rec, default=0, quiet=True) or 0
    names = []
    for i in range(1, int(n) + 1):
        nm = vcall("GetFldName", rec, i, default="", quiet=True)
        if nm:
            names.append(nm)
    return pio, names


def _truthy(v):
    return str(v).strip().lower() in ("true", "1", "yes", "on")


def _find(names, exact, contains):
    low = {n.lower(): n for n in names}
    out = [low[e.lower()] for e in exact if e.lower() in low]
    out += [n for n in names if any(c in n.lower() for c in contains) and n not in out]
    return out


def layer_scale_of(h):
    lay = vcall("GetLayer", h, default=None, quiet=True)
    if lay is None:
        lay = vcall("ActLayer", default=None, quiet=True)
    try:
        s = float(vcall("GetLScale", lay, default=1.0, quiet=True))
        return s if s > 0 else 1.0
    except Exception:
        return 1.0


def style_pio_values(style, fields, pio):
    """Values of `fields` on the PIO stored in the style's symbol definition (or {}).
    Off unless READ_STYLE_SYMBOL (fewer native calls while the crash is open)."""
    if not READ_STYLE_SYMBOL:
        return None
    sym = vcall("GetObject", style, default=None, quiet=True)
    if not valid(sym):
        return {}
    h = vcall("FInSymDef", sym, default=None, quiet=True)
    n = 0
    while valid(h) and n < 200:
        if vcall("GetTypeN", h, default=0, quiet=True) == T_PLUGIN_OBJECT:
            return {f: vcall("GetRField", h, pio, f, default="", quiet=True) for f in fields}
        h = vcall("NextObj", h, default=None, quiet=True)
        n += 1
    return {}


def find_reference_tag(style):
    """A Data Tag of the same style NOT made by this script (e.g. placed with the
    Data Tag tool). Callback only collects handles; everything else runs after."""
    cands = []

    def collect(h):
        try:
            if vs.GetTypeN(h) == T_PLUGIN_OBJECT and not (vs.GetName(h) or "").startswith(TAG_NAME_PREFIX):
                cands.append(h)
        except Exception:
            pass

    vcall("ForEachObject", collect, "ALL", quiet=True)
    crumb(f"reference scan: {len(cands)} plug-in objects to check")
    for h in cands[:500]:
        rec = vcall("GetParametricRecord", h, default=None, quiet=True)
        if rec is None or (vcall("GetName", rec, default="", quiet=True) or "") != DATA_TAG_PIO:
            continue
        if (vcall("GetPluginStyle", h, default="", quiet=True) or "") == style:
            return h
    return None


SIZE_FIELD_WORDS = ("world", "scal", "factor")


class TagScaleFixer(object):
    """First tag: log parameters, match a manual reference tag if one exists,
    otherwise force world-based; measure; choose one method. Later tags: repeat it."""

    def __init__(self, extra_factor, enabled=True, reference=None, style=""):
        self.extra = extra_factor if extra_factor and extra_factor > 0 else 1.0
        self.enabled = enabled
        self.ref = reference
        self.style = style
        self.ref_vals = {}
        self.ref_info = "none found (place one tag with the Data Tag tool to use as reference)"
        self.decided = False
        self.pio = DATA_TAG_PIO
        self.wb_fields = []
        self.scaling_f = []
        self.factor_f = []
        self.text_f = []
        self.base = 1.0             # factor that reproduces the reference (1 = Scaling None)
        self.factor = 1.0           # factor put on every tag
        self.layer_scale = 1.0
        self.h_ref = None
        self.h_before = None
        self.h_after = None
        self.wb_before = "?"
        self.wb_after = "?"
        self.style_wb = "?"
        self.method = "not run"
        self.param_dump = []
        self.ref_diff = []

    # -- helpers
    def _get(self, tag, f):
        return vcall("GetRField", tag, self.pio, f, default="", quiet=True)

    def _wb_text(self, tag):
        if not self.wb_fields:
            return "field not found"
        return ", ".join(f"{f}={self._get(tag, f)}" for f in self.wb_fields)

    def _apply(self, tag, factor):
        update_from_style(tag)
        if self.ref_vals and abs(factor - self.base) < 1e-12:
            # exactly what the Data Tag tool produced on the reference tag
            for f, v in self.ref_vals.items():
                vcall("SetRField", tag, self.pio, f, str(v), quiet=True)
        else:
            for f in self.wb_fields:
                vcall("SetRField", tag, self.pio, f,
                      str(self.ref_vals.get(f, "True")), quiet=True)
            if abs(factor - 1.0) < 1e-12:
                for f in self.scaling_f:
                    vcall("SetRField", tag, self.pio, f, "None", quiet=True)
            else:
                for f in self.scaling_f:
                    vcall("SetRField", tag, self.pio, f, "Symmetric", quiet=True)
                for f in self.text_f:
                    vcall("SetRField", tag, self.pio, f, "True", quiet=True)
                for f in self.factor_f:
                    vcall("SetRField", tag, self.pio, f, f"{factor:.8g}", quiet=True)
        vcall("ResetObject", tag)

    def _ref_base(self):
        mode = str(self.ref_vals.get(self.scaling_f[0], "")) if self.scaling_f else ""
        if mode and mode.strip().lower() not in ("none", "0"):
            for f in self.factor_f:
                try:
                    v = float(self.ref_vals.get(f, ""))
                    if v > 0:
                        return v
                except Exception:
                    pass
        return 1.0

    # -- main entry
    def handle(self, tag):
        if not self.enabled:
            if not self.decided:
                self.decided = True
                self.h_before = self.h_after = tag_height(tag)
                self.method = "switched off - tags left exactly as created (no size calls made)"
            return
        if self.decided:
            self._apply(tag, self.factor)
            return
        self.decided = True
        crumb("size fix: reading Data Tag parameters")
        pio, names = tag_param_info(tag)
        self.pio = pio or DATA_TAG_PIO
        self.param_dump = [f"{n}={self._get(tag, n)}" for n in names]
        self.wb_fields = _find(names, ("WorldBased",), ("world",))
        self.scaling_f = _find(names, ("Scaling",), ())
        self.factor_f = _find(names, ("Factor", "XScale", "YScale"), ())
        self.text_f = _find(names, ("ScaleText",), ())
        self.layer_scale = S = layer_scale_of(tag)
        sv = style_pio_values(self.style, self.wb_fields, self.pio)
        self.style_wb = ("not read (switched off)" if sv is None else
                         ", ".join(f"{f}={sv[f]}" for f in sv) if sv else "could not read style symbol")

        h0 = tag_height(tag)
        self.h_before = h0
        self.wb_before = self._wb_text(tag)
        was_world = bool(self.wb_fields) and all(_truthy(self._get(tag, f)) for f in self.wb_fields)

        target = None
        if valid(self.ref):
            size_fields = [n for n in names if any(w in n.lower() for w in SIZE_FIELD_WORDS)]
            self.ref_vals = {f: vcall("GetRField", self.ref, self.pio, f, default="", quiet=True)
                             for f in size_fields}
            for n in names:
                rv = vcall("GetRField", self.ref, self.pio, n, default="", quiet=True)
                tv = self._get(tag, n)
                if str(rv) != str(tv):
                    self.ref_diff.append(f"{n}: script={tv} / tool={rv}")
            self.base = self._ref_base()
            self.h_ref = tag_height(self.ref)
            target = self.h_ref * self.extra if self.h_ref else None
            self.ref_info = (f"'{vcall('GetName', self.ref, default='', quiet=True) or '(unnamed)'}' "
                             f"{'; '.join(f'{k}={v}' for k, v in self.ref_vals.items())}")

        crumb(f"size fix: layer 1:{S:g}, h0={h0}, world-based fields {self.wb_fields}, ref={'yes' if self.ref_vals else 'no'}")
        # Step 1: copy the reference's size settings (or force world-based), x extra factor
        f1 = self.base * self.extra
        self._apply(tag, f1)
        h1 = tag_height(tag)
        self.h_after = h1
        self.wb_after = self._wb_text(tag)
        self.factor = f1
        how1 = ("size settings copied from the manually placed tag" if self.ref_vals
                else "world-based forced on the tag")
        if not h0 or not h1:
            self.method = f"{how1}; could not measure the tag, no check possible"
            return
        if target:
            ok1 = abs(h1 / target - 1.0) < 0.1
        else:
            expected = h0 * f1 / (S if (not was_world and S > 1.0001) else 1.0)
            ok1 = abs(h1 / expected - 1.0) < 0.1
            target = expected
        if ok1:
            self.method = how1 + (f" (size / {S:g})" if abs(h0 / h1 - S) / S < 0.1 and S > 1.0001 else "")
            return
        # Step 2: settings did not stick -> Symmetric factor that brings it to the target
        if not self.factor_f:
            self.method = f"FAILED: {how1} did not give the expected size and no Factor field found"
            log_error(self.method)
            return
        f2 = f1 * target / h1
        crumb(f"size fix: fallback factor {f2:.6g}")
        self._apply(tag, f2)
        h2 = tag_height(tag)
        if h2 and abs(h2 / target - 1.0) < 0.1:
            self.factor = f2
            self.h_after = h2
            self.method = (f"fallback: Scaling Symmetric, Factor {f2:.6g} on every tag "
                           f"({how1} alone did not change the size)")
        else:
            self._apply(tag, f1)
            self.h_after = tag_height(tag)
            self.method = (f"FAILED: neither {how1} nor Factor {f2:.6g} changed the size "
                           f"(fields probably locked By Style) - see manual fix")
            log_error(self.method)


# ---------------------------------------------------------------------------
# Cleanup of earlier runs
# ---------------------------------------------------------------------------
def has_record(h, rec_name):
    n = vcall("NumRecords", h, default=0, quiet=True) or 0
    for i in range(1, int(n) + 1):
        r = vcall("GetRecord", h, i, quiet=True)
        if r is not None and (vcall("GetName", r, default="", quiet=True) or "") == rec_name:
            return True
    return False


def cleanup_previous(replace_previous):
    """Returns (v2_marks_removed, old_tags_removed, old_hoists_removed)."""
    marks, tags, hoists = [], [], []
    remove_v2_marks = replace_previous  # leftover V2 marks are earlier-run output too

    def collect(h):
        try:
            name = vs.GetName(h) or ""
        except Exception:
            name = ""
        if remove_v2_marks and name.startswith(V2_MARK_PREFIX):
            marks.append(h)
            return
        if replace_previous:
            if name.startswith(TAG_NAME_PREFIX):
                tags.append(h)
                return
            try:
                is_pio = vs.GetTypeN(h) == T_PLUGIN_OBJECT
            except Exception:
                is_pio = False
            if is_pio and has_record(h, RECORD_NAME):
                hoists.append(h)

    if replace_previous:
        vcall("ForEachObject", collect, "ALL")
    # tags first, then hoists (so no tag is left pointing at a deleted hoist)
    removed = []
    for group in (marks, tags, hoists):
        n = 0
        for h in group:
            if vcall("DelObject", h) is not False:
                n += 1
        removed.append(n)
    if remove_v2_marks:
        for sym in V2_MARK_SYMBOLS:
            sh = vcall("GetObject", sym, quiet=True)
            if valid(sh):
                vcall("DelObject", sh, quiet=True)
    return tuple(removed)


# ---------------------------------------------------------------------------
# Class colour for the tag quarters
# ---------------------------------------------------------------------------
def class_exists(name):
    n = vcall("ClassNum", default=0, quiet=True) or 0
    for i in range(1, int(n) + 1):
        if vcall("ClassList", i, default="", quiet=True) == name:
            return True
    return False


def set_quarters_color(choice):
    """Returns summary text. 'Keep current' leaves the class untouched."""
    rgb = dict(COLOR_CHOICES).get(choice)
    if rgb is None:
        return f"{KEEP_COLOR} (class '{QUARTERS_CLASS}' untouched)"
    created = ""
    if not class_exists(QUARTERS_CLASS):
        # NameClass creates the class but also makes it active: restore after
        active = vcall("ActiveClass", default="", quiet=True) or ""
        vcall("NameClass", QUARTERS_CLASS)
        if active:
            vcall("NameClass", active)
        if not class_exists(QUARTERS_CLASS):
            log_error(f"Could not create class '{QUARTERS_CLASS}'")
            return f"{choice} NOT applied (class '{QUARTERS_CLASS}' missing)"
        created = ", class created"
    vcall("SetClFPat", QUARTERS_CLASS, FILL_SOLID)
    fore = _set_class_color("SetClFillFore", "GetClFillFore", rgb)
    back = _set_class_color("SetClFillBack", "GetClFillBack", rgb)
    pat = vcall("GetClFPat", QUARTERS_CLASS, default="?", quiet=True)
    return (f"{choice} {tuple(rgb)} on class '{QUARTERS_CLASS}'{created}: "
            f"fore read back {fore[1]} via {fore[0]}, back read back {back[1]} via {back[0]}, "
            f"pattern {pat}")


def _rgb_of(value):
    try:
        if isinstance(value, (list, tuple)) and len(value) >= 3:
            return tuple(int(v) for v in value[:3])
    except Exception:
        pass
    return None


def _close(a, b, tol=300):
    return a is not None and all(abs(x - y) <= tol for x, y in zip(a, b))


def _set_class_color(setter, getter, rgb):
    """Python form per the official vs.py stub: vs.SetClFillFore(className, color)
    with color = (r, g, b) in 0-65535. Verify with the getter; fall back to the
    VectorScript-style separate ints, then to a colour index.
    Returns (method used, read-back rgb)."""
    r, g, b = rgb
    attempts = (
        ("tuple", lambda: vcall(setter, QUARTERS_CLASS, (r, g, b), quiet=True)),
        ("r,g,b", lambda: vcall(setter, QUARTERS_CLASS, r, g, b, quiet=True)),
        ("index", lambda: vcall(setter, QUARTERS_CLASS,
                                vcall("RGBToColorIndex", r, g, b, default=0, quiet=True),
                                quiet=True)),
    )
    got = None
    for label, attempt in attempts:
        attempt()
        got = _rgb_of(vcall(getter, QUARTERS_CLASS, default=None, quiet=True))
        if _close(got, rgb):
            return label, got
    log_error(f"{setter}: class colour read back as {got}, wanted {tuple(rgb)}")
    return "FAILED", got


# ---------------------------------------------------------------------------
# Dialog
# ---------------------------------------------------------------------------
class DialogState(object):
    def __init__(self, sources, meta, csv_path):
        self.sources = sources
        self.meta = meta
        self.csv_path = csv_path
        self.checks = {}
        self.single_sources = set()
        self.tag_hoists = True
        self.style = DEFAULT_TAG_STYLE
        self.show_id_label = False  # feature removed; ID label always off
        self.replace_prev = True
        self.color = KEEP_COLOR
        self.fix_scale = True
        self.lift_tags = True
        self.scale_factor = 1.0
        self.ok = False
        self.dialog = None


STATE = None


def dialog_handler(item, data):
    d = STATE.dialog
    if item == 12255:  # setup
        vcall("SetItemText", d, K_FILE_LABEL, STATE.csv_path or "(no file)")
        vcall("SetItemText", d, K_STYLE_EDIT, STATE.style)
        for i, (label, _rgb) in enumerate(COLOR_CHOICES):
            vcall("AddChoice", d, K_COLOR_MENU, label, i)
        vcall("SelectChoice", d, K_COLOR_MENU, 0, True)
        for cid, val in ((K_TAG_CHECK, STATE.tag_hoists),
                         (K_REPLACE_CHECK, STATE.replace_prev),
                         (K_LIFT_CHECK, STATE.lift_tags)):
            vcall("SetBooleanItem", d, cid, val)
        for src, cid in STATE.checks.items():
            vcall("SetBooleanItem", d, cid, False)
            if not STATE.meta[src]["single_available"]:
                vcall("EnableItem", d, cid, False)
        return None
    if item == K_TAG_CHECK:
        on = bool(vcall("GetBooleanItem", d, K_TAG_CHECK, default=True))
        vcall("EnableItem", d, K_STYLE_EDIT, on)
        return None
    if item == 1:
        STATE.single_sources = {src for src, cid in STATE.checks.items()
                                if vcall("GetBooleanItem", d, cid, default=False)}
        STATE.tag_hoists = bool(vcall("GetBooleanItem", d, K_TAG_CHECK, default=True))
        sel = vcall("GetSelectedChoiceInfo", d, K_COLOR_MENU, 0, default=None)
        STATE.color = KEEP_COLOR
        if isinstance(sel, (list, tuple)) and len(sel) >= 2:
            if sel[1] in dict(COLOR_CHOICES):
                STATE.color = sel[1]
            elif isinstance(sel[0], int) and 0 <= sel[0] < len(COLOR_CHOICES):
                STATE.color = COLOR_CHOICES[sel[0]][0]
        STATE.replace_prev = bool(vcall("GetBooleanItem", d, K_REPLACE_CHECK, default=True))
        STATE.lift_tags = bool(vcall("GetBooleanItem", d, K_LIFT_CHECK, default=True))
        txt = vcall("GetItemText", d, K_STYLE_EDIT, default=DEFAULT_TAG_STYLE)
        if isinstance(txt, (list, tuple)):
            txt = txt[-1]
        STATE.style = (str(txt or "").strip()) or DEFAULT_TAG_STYLE
        STATE.ok = True
        return 1
    if item == 2:
        STATE.ok = False
        return 2
    return None


def _edit_real(d, item, default):
    res = vcall("GetEditReal", d, item, 1, default=None)
    try:
        val = res[1] if isinstance(res, (list, tuple)) else res
        val = float(val)
        return val if val > 0 else default
    except Exception:
        return default


def build_dialog(sources, meta, csv_path):
    global STATE
    STATE = DialogState(sources, meta, csv_path)
    d = vcall("CreateLayout", SCRIPT_TITLE, True, "Place", "Cancel")
    STATE.dialog = d
    vcall("CreateStaticText", d, K_TITLE, "Flown sources only. Default = front + rear picks.", -1)
    vcall("CreateStaticText", d, K_FILE_LABEL, csv_path or "", -1)
    vcall("CreateCheckBox", d, K_TAG_CHECK, "Tag hoists with data tag style:")
    vcall("CreateEditText", d, K_STYLE_EDIT, DEFAULT_TAG_STYLE, 24)
    vcall("CreateStaticText", d, K_COLOR_LABEL, f"Tag quarter colour (class {QUARTERS_CLASS}):", -1)
    vcall("CreatePullDownMenu", d, K_COLOR_MENU, 16)
    vcall("CreateCheckBox", d, K_LIFT_CHECK, "Lift tags to hoist height")
    vcall("CreateCheckBox", d, K_REPLACE_CHECK,
          "Replace hoists + tags (and old V2 marks) from earlier runs")
    vcall("CreateStaticText", d, K_HELP,
          "Tick a source only if it is actually a single-point hang:", -1)

    vcall("SetFirstLayoutItem", d, K_TITLE)
    vcall("SetBelowItem", d, K_TITLE, K_FILE_LABEL, 0, 6)
    vcall("SetBelowItem", d, K_FILE_LABEL, K_TAG_CHECK, 0, 10)
    vcall("SetRightItem", d, K_TAG_CHECK, K_STYLE_EDIT, 8, 0)
    vcall("SetBelowItem", d, K_TAG_CHECK, K_COLOR_LABEL, 0, 4)
    vcall("SetRightItem", d, K_COLOR_LABEL, K_COLOR_MENU, 8, 0)
    vcall("SetBelowItem", d, K_COLOR_LABEL, K_LIFT_CHECK, 0, 4)
    vcall("SetBelowItem", d, K_LIFT_CHECK, K_REPLACE_CHECK, 0, 4)
    vcall("SetBelowItem", d, K_REPLACE_CHECK, K_HELP, 0, 10)

    prev = K_HELP
    cid = K_CHECK_START
    for src in sources:
        label = src
        if meta[src]["system"]:
            label = f"{src}  ({meta[src]['system']})"
        if not meta[src]["single_available"]:
            label += "  - no single pick in CSV"
        vcall("CreateCheckBox", d, cid, label)
        vcall("SetBelowItem", d, prev, cid, 0, 2)
        STATE.checks[src] = cid
        prev = cid
        cid += 1
    return d


def write_param_dump(csv_path, sizer):
    try:
        path = os.path.join(os.path.dirname(csv_path), "V3_data_tag_parameters.txt")
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(f"record: {sizer.pio}\nlayer scale: {sizer.layer_scale:g}\n")
            fh.write(f"world-based before: {sizer.wb_before}\nafter: {sizer.wb_after}\n")
            fh.write(f"style: {sizer.style_wb}\nmethod: {sizer.method}\n\n")
            fh.write(f"reference tag: {sizer.ref_info}\n")
            fh.write("differences script vs tool tag:\n  " + "\n  ".join(sizer.ref_diff) + "\n\n")
            fh.write("\n".join(sizer.param_dump) + "\n")
        return path
    except Exception as e:
        log_error(f"could not write parameter list: {e}")
        return ""


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def run():
    del ERRORS[:]
    csv_path = choose_csv_path()
    if not csv_path or not os.path.isfile(csv_path):
        vcall("AlrtDialog", "No hoist CSV found. Run the extractor first, or pick a CSV.")
        return
    try:
        rows = read_csv(csv_path)
    except Exception as e:
        vcall("AlrtDialog", f"Could not read CSV:\n{csv_path}\n\n{e}")
        return

    global RUN_LOG, CRUMB_VERBOSE
    RUN_LOG = os.path.join(os.path.dirname(csv_path), "V3_run_log.txt")
    try:
        with open(RUN_LOG, "w", encoding="utf-8") as fh:
            fh.write(f"{SCRIPT_TITLE} run log (breadcrumbs; last line = last step reached)\n")
    except Exception:
        RUN_LOG = None
    crumb(f"CSV {csv_path}: {len(rows)} rows")
    sources, meta = unique_sources(rows)
    dialog = build_dialog(sources, meta, csv_path)
    if dialog is None:
        vcall("AlrtDialog", "Could not build the dialog:\n" + "\n".join(ERRORS[:5]))
        return
    vcall("RunLayoutDialog", dialog, dialog_handler)
    if not STATE.ok:
        crumb("dialog cancelled")
        return
    crumb(f"dialog OK: style={STATE.style!r} colour={STATE.color} fix_size={STATE.fix_scale} "
          f"extra={STATE.scale_factor} replace={STATE.replace_prev} singles={sorted(STATE.single_sources)}")

    missing = [s for s in STATE.single_sources if not meta[s]["single_available"]]
    if missing:
        vcall("AlrtDialog", "These sources have no single pick in the CSV:\n" + ", ".join(missing))
        return
    selected = filter_rows(rows, STATE.single_sources)
    if not selected:
        vcall("AlrtDialog", "Nothing to place with the current checkbox selection.")
        return

    crumb("step: record format")
    record_ok = ensure_arraycalc_record()
    if not record_ok:
        log_error(f"Could not create record format '{RECORD_NAME}' - tags cannot show loads")

    # Style first (record already exists, so the import doesn't bring a duplicate)
    style = STATE.style
    style_ok, style_status = False, "tagging switched off"
    if STATE.tag_hoists:
        style_ok, style_status = ensure_tag_style(style)

    crumb(f"step: style -> {style_ok} {style_status}")
    crumb("step: cleanup of earlier runs")
    removed_marks, removed_tags, removed_hoists = cleanup_previous(STATE.replace_prev)
    crumb(f"step: cleanup done {removed_marks}/{removed_tags}/{removed_hoists}; colour")
    color_status = set_quarters_color(STATE.color)

    unit_mark, upi = document_unit_info()
    placed = failed = tagged = 0
    ref_tag = None
    if STATE.tag_hoists and style_ok and STATE.fix_scale:
        crumb("step: reference tag scan")
        ref_tag = find_reference_tag(style)
        crumb(f"step: reference tag {'found' if ref_tag is not None else 'none'}")
    sizer = TagScaleFixer(STATE.scale_factor, STATE.fix_scale, ref_tag, style)
    lift_ok, lift_bad = 0, []
    CRUMB_VERBOSE = True   # every vs call of the first hoist + tag goes to the log
    z_set = z_unverified = z_missing = 0
    z_bad = []
    no_load = []

    for r in selected:
        try:
            x = m_to_doc(r["x_m"])
            y = m_to_doc(r["y_m"])
        except Exception as e:
            log_error(f"Bad X/Y in CSV row {r.get('source')} {r.get('pick_kind')}: {e}")
            failed += 1
            continue
        letter = pick_letter(r["pick_kind"])
        load_text = format_load_kg(r.get("weight_kg"))
        hoist_id = f"{r['source']} {letter} {side_label(r['y_m'])}"
        hoist_name = f"{hoist_id}  {load_text}" if load_text else hoist_id
        z_raw = (r.get("z_m") or "").strip()
        notes = (f"ArrayCalc {r.get('system', '')} | {r['source']} {r['pick_kind']} | "
                 f"XY=({r['x_m']},{r['y_m']}) m | Z={z_raw or '?'} m | hole={r.get('hole', '')}")
        if load_text:
            notes += f" | pick load {load_text}"

        crumb(f"hoist {r['source']} {r['pick_kind']}: create")
        h, pio_name = create_hoist(x, y)
        if not h:
            failed += 1
            continue
        placed += 1
        set_hoist_fields(h, pio_name, hoist_id, hoist_name, load_text, notes, STATE.show_id_label)
        attach_arraycalc_record(h, r, load_text)
        vcall("SetName", h, hoist_id, quiet=True)
        vcall("ResetObject", h)

        # Height last: a PIO reset can rebuild the object
        # Height is always applied
        try:
            z_m = float(z_raw)
        except Exception:
            z_m = None
        if z_m is None:
            z_missing += 1
        else:
            res = set_hoist_z(h, z_m)
            if res is True:
                z_set += 1
            elif res is None:
                z_unverified += 1
            else:
                z_bad.append(hoist_id)

        if STATE.tag_hoists and style_ok:
            if not record_load_text(h):
                no_load.append(hoist_id)
            crumb(f"hoist {hoist_id}: tag")
            tag = place_tag(h, x, y, style, hoist_id)
            if tag is not None:
                crumb(f"hoist {hoist_id}: size")
                sizer.handle(tag)
                recenter_tag(tag, x, y)
                tagged += 1
                if STATE.lift_tags:
                    if z_m is None:
                        lift_bad.append(f"{hoist_id} (no z_m)")
                    else:
                        okl, why = lift_tag(tag, m_to_doc(z_m), x, y, hoist_id)
                        if okl and why == "ok":
                            lift_ok += 1
                        elif okl:
                            lift_ok += 1
                            lift_bad.append(f"{hoist_id}: {why}")
                        else:
                            lift_bad.append(f"{hoist_id}: {why}")
        CRUMB_VERBOSE = False

    # Redraw every data tag (new tags, and existing ones after a class colour change)
    crumb(f"loop done: {placed} hoists, {tagged} tags; reset all data tags")
    if (STATE.tag_hoists and style_ok) or STATE.color != KEEP_COLOR:
        vcall("DT_ResetAllDataTags", quiet=True)
    vcall("ReDrawAll", quiet=True)

    # ---- summary (user-readable only; technical details go to V3_run_log.txt)
    lines = []
    if STATE.tag_hoists:
        if style_ok:
            lines.append(f"Data tag style '{style}': found")
        else:
            lines.append(f"Data tag style '{style}': NOT FOUND")
    lines.append(f"Hoists placed: {placed}" + (f"   (failed: {failed})" if failed else ""))
    if STATE.tag_hoists:
        lines.append(f"Data tags placed: {tagged}")
        if not style_ok:
            lines.append("")
            lines.append(f"Hoists were placed without tags. Import '{style}' with the Resource "
                         "Manager, then run the script again, or tag the hoists with the "
                         "Data Tag tool.")
    if ERRORS:
        crumb("problems: " + " | ".join(ERRORS))
    crumb("summary shown - run finished")
    vcall("AlrtDialog", "\n".join(lines))


if __name__ != "vwtest":
    run()
