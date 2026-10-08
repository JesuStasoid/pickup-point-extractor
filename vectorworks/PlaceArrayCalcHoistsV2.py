# Place ArrayCalc Hoists V2
# Vectorworks Python — Tools > Plug-ins > Run Script… / workspace menu
#
# Reads CSV from extract_arraycalc_hoists.py (metres).
# V2: load marks are AutoCAD-attribute style — a small symbol at each hoist
# whose text is LINKED to the 'ArrayCalc Pick' record field 'Load Text'
# (e.g. "664 kg"). Edit the field on the symbol (OIP → Data) and the text
# updates. No leaders.
#
# Mark position:
#   front/rear hangs lying mostly along plan X → higher pick's mark ABOVE,
#   lower pick's mark BELOW (centred over / under the hoist);
#   other hangs and single picks → LEFT / RIGHT of the hoist (dialog).
# Text size follows the active layer scale (target height editable in dialog);
# gap from hoist centre is editable too.
# No Z handling: hoists and marks are placed flat at layer height (Z 0).
# ArrayCalc height is kept in the hoist notes only.
# Re-running deletes earlier load marks (objects named "AC Load …").

import csv
import os

import vs

HOIST_PIO_CANDIDATES = ("Hoist", "BrxHoist")
RECORD_NAME = "ArrayCalc Pick"

K_TITLE = 10
K_HELP = 11
K_FILE_LABEL = 13
K_TAG_HELP = 14
K_TEXT_H_LABEL = 15
K_TEXT_H_EDIT = 16
K_GAP_LABEL = 17
K_GAP_EDIT = 18

# --- Load mark sizing -------------------------------------------------------
# Target height of the load text in the model (metres, real size). Editable in
# the dialog. Point size = target / (scale * 1 pt), clamped to MIN/MAX_PT.
DEFAULT_TEXT_HEIGHT_M = 0.25
MIN_PT = 3.0
MAX_PT = 10.0
PT_TO_M = 0.0254 / 72.0  # 1 pt on paper in metres
# Hangs whose hang axis is within ~45° of plan X get stacked marks
# (above / below); steeper hangs get side marks (left / right).
STACK_AXIS_TOL = 0.71  # |sin| of hang-axis angle to X
# Distance from hoist centre to the near edge of the text (metres, real size)
DEFAULT_GAP_M = 0.35
REF_TEXT_M = 10 * PT_TO_M * 100

SYMBOL_PREFIX = "AC Load Mark"
LINK_FIELD = "Load Text"
PLACEHOLDER = "000 kg"
# variant → (horizontal just 1=L 2=C 3=R, vertical just 1=top 2=centre 3=bottom)
VARIANTS = {
    "right": (1, 2),
    "left": (3, 2),
    "above": (2, 3),
    "below": (2, 1),
}

# Filled in run() once the scale is known
MARK = {"pt": MAX_PT, "text_m": REF_TEXT_M, "k": 1.0, "scale": 100.0, "gap_m": DEFAULT_GAP_M}
K_CHECK_START = 100
K_TAG_LEFT_START = 300
K_TAG_RIGHT_START = 500


def m_to_doc(meters):
    """ArrayCalc metres → current document length units via GetUnits() upi."""
    _frac, _disp, _fmt, upi, _mark, _area = vs.GetUnits()
    inches = float(meters) / 0.0254
    return inches * float(upi)


def document_unit_info():
    _frac, _disp, _fmt, upi, mark, _area = vs.GetUnits()
    return mark or "?", float(upi)


def active_layer_scale():
    """Scale factor of the active design layer (200.0 for 1:200)."""
    try:
        s = float(vs.GetLScale(vs.ActLayer()))
        if s > 0:
            return s
    except Exception:
        pass
    return 100.0


def compute_mark_size(scale, target_text_m):
    """Point size + leader scale factor for load marks at this layer scale."""
    target = target_text_m if target_text_m and target_text_m > 0 else DEFAULT_TEXT_HEIGHT_M
    pt = target / (scale * PT_TO_M)
    pt = max(MIN_PT, min(MAX_PT, pt))
    text_m = pt * PT_TO_M * scale  # actual model height after clamping
    return {"pt": pt, "text_m": text_m, "k": text_m / REF_TEXT_M, "scale": scale}


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
    return rows


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


def choose_csv_path():
    doc = vs.GetFName() or ""
    folder = ""
    try:
        full = vs.GetFPathName()
        if full:
            folder = os.path.dirname(full)
    except Exception:
        folder = ""

    candidates = []
    if folder:
        for name in (
            "hoist_pick_points_flown.csv",
            "hoist_pick_points.csv",
            os.path.splitext(os.path.basename(doc))[0] + "_hoist_picks.csv",
        ):
            candidates.append(os.path.join(folder, name))
        try:
            for fn in os.listdir(folder):
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

    ok = vs.GetFileN("ArrayCalc hoist CSV", "", "csv")
    if isinstance(ok, tuple):
        if len(ok) >= 2 and ok[0] in (True, 1):
            return ok[1]
        if len(ok) == 1 and isinstance(ok[0], str) and ok[0]:
            return ok[0]
        return None
    if isinstance(ok, str) and ok:
        return ok
    return None


def ensure_arraycalc_record():
    """Create ArrayCalc Pick record format if missing."""
    if vs.GetObject(RECORD_NAME):
        return True
    ok = vs.NewField(RECORD_NAME, "Source", "", 4, 0)  # 4 = text
    if not ok and not vs.GetObject(RECORD_NAME):
        return False
    vs.NewField(RECORD_NAME, "Pick", "", 4, 0)
    vs.NewField(RECORD_NAME, "Load kg", "0", 1, 0)  # 1 = integer / number-ish
    vs.NewField(RECORD_NAME, "Load Text", "", 4, 0)
    vs.NewField(RECORD_NAME, "Hole", "", 4, 0)
    vs.NewField(RECORD_NAME, "System", "", 4, 0)
    return bool(vs.GetObject(RECORD_NAME))


def attach_arraycalc_record(h, source, pick_kind, weight_kg, load_text, hole, system):
    # Attach the record (SetRecord); SetRField below also attaches if needed
    try:
        vs.SetRecord(h, RECORD_NAME)
    except Exception:
        pass
    def sf(field, value):
        try:
            vs.SetRField(h, RECORD_NAME, field, str(value))
        except Exception:
            pass
    sf("Source", source or "")
    sf("Pick", pick_kind or "")
    if weight_kg not in (None, ""):
        try:
            sf("Load kg", f"{float(weight_kg):.2f}")
        except Exception:
            sf("Load kg", str(weight_kg))
    sf("Load Text", load_text or "")
    sf("Hole", hole if hole is not None else "")
    sf("System", system or "")
    return True


def set_hoist_fields(h, pio_name, hoist_id, hoist_name, load_text, notes):
    def setf(field, value):
        try:
            vs.SetRField(h, pio_name, field, str(value))
        except Exception:
            pass

    setf("Param_HoistID", hoist_id)
    setf("Param_HoistName", hoist_name)
    setf("HoistID", hoist_id)
    setf("Hoist Name", hoist_name)
    setf("Param_Notes", notes)
    setf("Notes", notes)
    if load_text:
        # Function is the usual paperwork field; many tags / reports show it
        setf("ParamFunction", load_text)
        setf("Function", load_text)
        setf("Param_ShowLabel", "True")
        setf("Show ID label", "True")
        setf("Param_ShowLabel", "1")


def insert_hoist(x_doc, y_doc, hoist_id, hoist_name, z_m, weight_kg, load_text, notes, row):
    h = None
    pio_name = None
    for name in HOIST_PIO_CANDIDATES:
        try:
            h = vs.CreateCustomObject(name, float(x_doc), float(y_doc), 0.0)
        except Exception:
            h = None
        if h:
            pio_name = name
            break
    if not h:
        return None, None

    set_hoist_fields(h, pio_name, hoist_id, hoist_name, load_text, notes)
    attach_arraycalc_record(
        h,
        row.get("source"),
        row.get("pick_kind"),
        weight_kg,
        load_text,
        row.get("hole"),
        row.get("system"),
    )

    try:
        vs.SetName(h, hoist_id)
    except Exception:
        pass
    try:
        vs.ResetObject(h)
    except Exception:
        pass
    return h, pio_name


def unit_front_direction_m(front_row, rear_row):
    """Unit vector rear → front in plan (metres)."""
    dx = float(front_row["x_m"]) - float(rear_row["x_m"])
    dy = float(front_row["y_m"]) - float(rear_row["y_m"])
    length = (dx * dx + dy * dy) ** 0.5
    if length < 1e-4:
        return 1.0, 0.0
    return dx / length, dy / length


def build_frame_axes(selected):
    """Map flying_frame_id → unit rear→front direction for that hang."""
    frames = {}
    for r in selected:
        fid = r.get("flying_frame_id")
        if fid is None or fid == "":
            continue
        kind = (r.get("pick_kind") or "").lower()
        frames.setdefault(str(fid), {})[kind] = r
    axes = {}
    for fid, kinds in frames.items():
        if "front" in kinds and "rear" in kinds:
            axes[fid] = unit_front_direction_m(kinds["front"], kinds["rear"])
        else:
            axes[fid] = (1.0, 0.0)
    return axes


def _valid(h):
    if h is None:
        return False
    try:
        return vs.GetTypeN(h) > 0
    except Exception:
        return bool(h)


def _created_since(before):
    """Handle of the newest object if one was created after `before`."""
    try:
        n = vs.LNewObj()
    except Exception:
        return None
    if not _valid(n):
        return None
    try:
        if before is not None and _valid(before) and n == before:
            return None
    except Exception:
        pass
    return n


def delete_previous_load_marks():
    """Remove load marks / texts / leaders from earlier runs ('AC Load …')."""
    found = []

    def collect(h):
        try:
            nm = vs.GetName(h) or ""
        except Exception:
            nm = ""
        if nm.startswith("AC Load") and not nm.startswith(SYMBOL_PREFIX):
            found.append(h)

    try:
        vs.ForEachObject(collect, "ALL")
    except Exception:
        return 0
    removed = 0
    for h in found:
        try:
            vs.DelObject(h)
            removed += 1
        except Exception:
            pass
    return removed


def choose_variant(pick_kind, tag_side, along_xy):
    """Where the mark sits relative to its hoist."""
    kind = (pick_kind or "").lower()
    ay = along_xy[1] if along_xy else 0.0
    if kind in ("front", "rear") and abs(ay) < STACK_AXIS_TOL:
        if abs(ay) < 0.05:
            up = kind == "front"
        else:
            # rear→front unit vector: ay > 0 means front is the higher pick
            up = (ay > 0) == (kind == "front")
        return "above" if up else "below"
    return "left" if (tag_side or "right").lower() == "left" else "right"


def _bbox(h):
    bb = vs.GetBBox(h)
    if len(bb) == 2:
        (x1, y1), (x2, y2) = bb
    else:
        x1, y1, x2, y2 = bb[:4]
    return min(x1, x2), min(y1, y2), max(x1, x2), max(y1, y2)


def _snap_text_in_def(text_h, variant, gap_doc):
    """Place the text box so its near edge is gap_doc from the symbol origin."""
    try:
        left, bottom, right, top = _bbox(text_h)
    except Exception:
        return False
    cx, cy = (left + right) / 2.0, (bottom + top) / 2.0
    if variant == "right":
        dx, dy = gap_doc - left, -cy
    elif variant == "left":
        dx, dy = -gap_doc - right, -cy
    elif variant == "above":
        dx, dy = -cx, gap_doc - bottom
    else:  # below
        dx, dy = -cx, -gap_doc - top
    try:
        vs.HMove(text_h, dx, dy)
        return True
    except Exception:
        return False


def _texts_in_def(sym):
    out = []
    try:
        h = vs.FInSymDef(sym)
    except Exception:
        h = None
    while _valid(h):
        try:
            if vs.GetTypeN(h) == 10:  # text
                out.append(h)
        except Exception:
            pass
        try:
            h = vs.NextObj(h)
        except Exception:
            break
    return out


def symbol_name(variant):
    return f"{SYMBOL_PREFIX} {variant.capitalize()}"


def _style_def_text(th, variant, pt):
    hj, vj = VARIANTS[variant]
    try:
        vs.SetTextSize(th, 0, 255, round(pt, 1))
    except Exception:
        try:
            vs.SetTextSize(th, 0, len(PLACEHOLDER), round(pt, 1))
        except Exception:
            pass
    try:
        vs.SetTextJust(th, hj)
    except Exception:
        pass
    try:
        vs.SetTextVerticalJust(th, vj)
    except Exception:
        pass


def ensure_mark_symbol(variant, pt, gap_doc):
    """Create (or refresh size/position of) the linked-text mark symbol."""
    name = symbol_name(variant)
    sym = vs.GetObject(name)
    if not _valid(sym):
        hj, vj = VARIANTS[variant]
        th = None
        try:
            vs.BeginSym(name)
            try:
                vs.TextJust(hj)
                vs.TextVerticalJust(vj)
                vs.TextSize(round(pt, 1))
            except Exception:
                pass
            vs.MoveTo(0.0, 0.0)
            vs.CreateText(PLACEHOLDER)
            th = vs.LNewObj()
            try:
                vs.LinkText(th, RECORD_NAME, LINK_FIELD)
            except Exception:
                pass
        finally:
            try:
                vs.EndSym()
            except Exception:
                pass
        sym = vs.GetObject(name)
        if not _valid(sym):
            return None
        try:
            vs.SetRecord(sym, RECORD_NAME)
        except Exception:
            pass
    texts = _texts_in_def(sym)
    for th in texts:
        if not texts or th == texts[0]:
            try:
                vs.LinkText(th, RECORD_NAME, LINK_FIELD)
            except Exception:
                pass
        _style_def_text(th, variant, pt)
        _snap_text_in_def(th, variant, gap_doc)
    return sym


def _insert_symbol(name, x_doc, y_doc):
    for args in (((float(x_doc), float(y_doc)), 0.0), (float(x_doc), float(y_doc), 0.0)):
        try:
            before = vs.LNewObj()
        except Exception:
            before = None
        try:
            vs.Symbol(name, *args)
        except Exception:
            continue
        h = _created_since(before)
        if h is not None:
            return h
    return None


def place_linked_mark(x_doc, y_doc, z_m, load_text, hoist_id, variant, row):
    """Insert the mark symbol at the hoist and fill its record (text follows)."""
    if not load_text:
        return None
    h = _insert_symbol(symbol_name(variant), x_doc, y_doc)
    if h is None:
        return None
    try:
        vs.SetRecord(h, RECORD_NAME)
    except Exception:
        pass
    attach_arraycalc_record(
        h,
        row.get("source"),
        row.get("pick_kind"),
        row.get("weight_kg"),
        load_text,
        row.get("hole"),
        row.get("system"),
    )
    try:
        vs.SetName(h, f"AC Load {hoist_id}")
    except Exception:
        pass
    try:
        vs.ResetObject(h)
    except Exception:
        pass
    return h


class DialogState(object):
    def __init__(self, sources, meta, csv_path):
        self.sources = sources
        self.meta = meta
        self.csv_path = csv_path
        self.checks = {}
        self.tag_left = {}
        self.tag_right = {}
        self.single_sources = set()
        self.tag_side = {}  # source -> "left" | "right"
        self.scale = 100.0
        self.text_height_m = DEFAULT_TEXT_HEIGHT_M
        self.gap_m = DEFAULT_GAP_M
        self.ok = False


STATE = None


def dialog_handler(item, data):
    global STATE
    if item == 12255:  # SetupDialogC
        vs.SetItemText(STATE.dialog, K_FILE_LABEL, STATE.csv_path or "(no file)")
        for src, cid in STATE.checks.items():
            vs.SetBooleanItem(STATE.dialog, cid, False)
            if not STATE.meta[src]["single_available"]:
                vs.EnableItem(STATE.dialog, cid, False)
        for src in STATE.sources:
            vs.SetBooleanItem(STATE.dialog, STATE.tag_left[src], False)
            vs.SetBooleanItem(STATE.dialog, STATE.tag_right[src], True)
        try:
            vs.SetEditReal(STATE.dialog, K_TEXT_H_EDIT, 1, STATE.text_height_m)
        except Exception:
            pass
        try:
            vs.SetEditReal(STATE.dialog, K_GAP_EDIT, 1, STATE.gap_m)
        except Exception:
            pass
        return None

    # Keep Left / Right mutually exclusive per source
    for src in STATE.sources:
        if item == STATE.tag_left[src]:
            if vs.GetBooleanItem(STATE.dialog, STATE.tag_left[src]):
                vs.SetBooleanItem(STATE.dialog, STATE.tag_right[src], False)
            elif not vs.GetBooleanItem(STATE.dialog, STATE.tag_right[src]):
                vs.SetBooleanItem(STATE.dialog, STATE.tag_right[src], True)
            return None
        if item == STATE.tag_right[src]:
            if vs.GetBooleanItem(STATE.dialog, STATE.tag_right[src]):
                vs.SetBooleanItem(STATE.dialog, STATE.tag_left[src], False)
            elif not vs.GetBooleanItem(STATE.dialog, STATE.tag_left[src]):
                vs.SetBooleanItem(STATE.dialog, STATE.tag_left[src], True)
            return None

    if item == 1:
        STATE.single_sources = set()
        STATE.tag_side = {}
        for src, cid in STATE.checks.items():
            if vs.GetBooleanItem(STATE.dialog, cid):
                STATE.single_sources.add(src)
        for src in STATE.sources:
            if vs.GetBooleanItem(STATE.dialog, STATE.tag_left[src]):
                STATE.tag_side[src] = "left"
            else:
                STATE.tag_side[src] = "right"
        try:
            res = vs.GetEditReal(STATE.dialog, K_TEXT_H_EDIT, 1)
            val = res[1] if isinstance(res, (list, tuple)) else res
            if res and float(val) > 0:
                STATE.text_height_m = float(val)
        except Exception:
            pass
        try:
            res = vs.GetEditReal(STATE.dialog, K_GAP_EDIT, 1)
            val = res[1] if isinstance(res, (list, tuple)) else res
            if res and float(val) >= 0:
                STATE.gap_m = float(val)
        except Exception:
            pass
        STATE.ok = True
        return 1
    if item == 2:
        STATE.ok = False
        return 2
    return None


def build_dialog(sources, meta, csv_path, scale):
    global STATE
    STATE = DialogState(sources, meta, csv_path)
    STATE.scale = scale
    d = vs.CreateLayout("Place ArrayCalc Hoists V2", True, "Place", "Cancel")
    STATE.dialog = d
    vs.CreateStaticText(d, K_TITLE, "Flown sources only. Default = front + rear picks.", -1)
    vs.CreateStaticText(d, K_HELP, "Tick a source only if it is actually a single-point hang:", -1)
    vs.CreateStaticText(d, K_FILE_LABEL, csv_path or "", -1)
    vs.CreateStaticText(
        d,
        K_TAG_HELP,
        "Load mark side per source (LEFT/RIGHT = plan −X / +X). Used for single picks and steep hangs; "
        "hangs along X get marks above / below:",
        -1,
    )
    vs.CreateStaticText(
        d,
        K_TEXT_H_LABEL,
        f"Layer scale 1:{scale:g}. Load text height in model (m):",
        -1,
    )
    vs.CreateEditReal(d, K_TEXT_H_EDIT, 1, DEFAULT_TEXT_HEIGHT_M, 8)
    vs.CreateStaticText(d, K_GAP_LABEL, "Gap from hoist centre to load text (m):", -1)
    vs.CreateEditReal(d, K_GAP_EDIT, 1, DEFAULT_GAP_M, 8)
    vs.SetFirstLayoutItem(d, K_TITLE)
    vs.SetBelowItem(d, K_TITLE, K_HELP, 0, 6)
    vs.SetBelowItem(d, K_HELP, K_FILE_LABEL, 0, 6)
    vs.SetBelowItem(d, K_FILE_LABEL, K_TEXT_H_LABEL, 0, 8)
    vs.SetRightItem(d, K_TEXT_H_LABEL, K_TEXT_H_EDIT, 8, 0)
    vs.SetBelowItem(d, K_TEXT_H_LABEL, K_GAP_LABEL, 0, 4)
    vs.SetRightItem(d, K_GAP_LABEL, K_GAP_EDIT, 8, 0)

    prev = K_GAP_LABEL
    cid = K_CHECK_START
    for src in sources:
        label = src
        if meta[src]["system"]:
            label = f"{src}  ({meta[src]['system']})"
        if not meta[src]["single_available"]:
            label += "  — no single pick in ArrayCalc"
        vs.CreateCheckBox(d, cid, label)
        vs.SetBelowItem(d, prev, cid, 0, 2)
        STATE.checks[src] = cid
        prev = cid
        cid += 1

    vs.SetBelowItem(d, prev, K_TAG_HELP, 0, 10)
    prev = K_TAG_HELP
    left_id = K_TAG_LEFT_START
    right_id = K_TAG_RIGHT_START
    for src in sources:
        vs.CreateCheckBox(d, left_id, f"{src}  — marks LEFT")
        vs.CreateCheckBox(d, right_id, f"{src}  — marks RIGHT")
        vs.SetBelowItem(d, prev, left_id, 0, 4)
        vs.SetRightItem(d, left_id, right_id, 16, 0)
        STATE.tag_left[src] = left_id
        STATE.tag_right[src] = right_id
        prev = left_id
        left_id += 1
        right_id += 1
    return d


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


def run():
    csv_path = choose_csv_path()
    if not csv_path or not os.path.isfile(csv_path):
        vs.AlrtDialog("No hoist CSV found. Run extract_arraycalc_hoists.py first, or pick a CSV.")
        return

    try:
        rows = read_csv(csv_path)
    except Exception as e:
        vs.AlrtDialog(f"Could not read CSV:\n{e}")
        return

    sources, meta = unique_sources(rows)
    scale = active_layer_scale()
    dialog = build_dialog(sources, meta, csv_path, scale)
    vs.RunLayoutDialog(dialog, dialog_handler)
    if not STATE.ok:
        return

    missing = [s for s in STATE.single_sources if not meta[s]["single_available"]]
    if missing:
        vs.AlrtDialog("These sources have no single-pick hole in ArrayCalc:\n" + ", ".join(missing))
        return

    selected = filter_rows(rows, STATE.single_sources)
    if not selected:
        vs.AlrtDialog("Nothing to place with the current checkbox selection.")
        return

    if not ensure_arraycalc_record():
        vs.AlrtDialog("Could not create record format 'ArrayCalc Pick'. Loads may not attach.")

    unit_mark, upi = document_unit_info()
    one_m = m_to_doc(1.0)
    MARK.update(compute_mark_size(STATE.scale, STATE.text_height_m))
    MARK["gap_m"] = STATE.gap_m

    placed = 0
    failed = 0
    texts = 0
    removed_marks = delete_previous_load_marks()
    gap_doc = m_to_doc(MARK["gap_m"])
    symbols_ok = {}
    for variant in VARIANTS:
        symbols_ok[variant] = ensure_mark_symbol(variant, MARK["pt"], gap_doc) is not None
    frame_axes = build_frame_axes(selected)
    for r in selected:
        x = m_to_doc(r["x_m"])
        y = m_to_doc(r["y_m"])
        z = float(r.get("z_m") or 0)
        side = side_label(r["y_m"])
        letter = pick_letter(r["pick_kind"])
        load_text = format_load_kg(r.get("weight_kg"))
        hoist_id = f"{r['source']} {letter} {side}"
        hoist_name = f"{hoist_id}  {load_text}" if load_text else hoist_id
        notes = (
            f"ArrayCalc {r.get('system', '')} | {r['source']} {r['pick_kind']} | "
            f"XY=({r['x_m']},{r['y_m']}) m | Z={z} m | hole={r.get('hole', '')}"
        )
        if load_text:
            notes = f"{notes} | pick load {load_text}"

        h, _pio = insert_hoist(x, y, hoist_id, hoist_name, z, r.get("weight_kg"), load_text, notes, r)
        if not h:
            failed += 1
            continue
        placed += 1

        tag_side = STATE.tag_side.get(r["source"], "right")
        fid = str(r.get("flying_frame_id") or "")
        along_xy = frame_axes.get(fid, (1.0, 0.0))
        variant = choose_variant(r.get("pick_kind"), tag_side, along_xy)
        if symbols_ok.get(variant) and place_linked_mark(
            x, y, z, load_text, hoist_id, variant, r
        ):
            texts += 1

    left_src = [s for s, side in STATE.tag_side.items() if side == "left"]
    right_src = [s for s, side in STATE.tag_side.items() if side == "right"]
    msg = (
        f"Placed {placed} hoist(s) from:\n{csv_path}\n\n"
        f"Old load marks removed: {removed_marks}\n"
        f"Linked load marks: {texts}  (symbols '{SYMBOL_PREFIX} Right/Left/Above/Below', "
        f"gap {MARK['gap_m']:.2f} m; layer 1:{MARK['scale']:g} → {MARK['pt']:.1f} pt, "
        f"≈{MARK['text_m']:.2f} m tall in model)\n"
        f"Marks LEFT: {', '.join(left_src) if left_src else '(none)'}\n"
        f"Marks RIGHT: {', '.join(right_src) if right_src else '(none)'}\n"
        f"Record: '{RECORD_NAME}' (Load kg / Load Text)\n\n"
        f"Document units: {unit_mark} (upi={upi:g})\n"
        f"1 m ArrayCalc → {one_m:g} doc units"
    )
    if STATE.single_sources:
        msg += "\n\nSingle-point: " + ", ".join(sorted(STATE.single_sources))
    else:
        msg += "\n\nAll front + rear."
    if failed:
        msg += (
            f"\n\n{failed} failed — is the Hoist tool / Braceworks available "
            "in this workspace?"
        )
    vs.AlrtDialog(msg)


run()
