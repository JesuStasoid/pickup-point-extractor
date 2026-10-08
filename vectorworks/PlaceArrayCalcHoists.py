# Place ArrayCalc Hoists
# Vectorworks Python — Tools > Plug-ins > Run Script… / workspace menu
#
# Reads CSV from extract_arraycalc_hoists.py (metres).
# Dialog: single-point hang checkboxes + per-source LEFT/RIGHT load-tag side.
# Sets each hoist's insertion Z from ArrayCalc frame height.
# Load marks are sized from the active layer scale so they stay a sensible
# real-world size (no giant text at 1:200 / 1:500).

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

# --- Load mark sizing -------------------------------------------------------
# Target height of the load text in the model (metres, real size). Editable in
# the dialog. Point size = target / (scale * 1 pt), clamped to MIN/MAX_PT.
DEFAULT_TEXT_HEIGHT_M = 0.25
MIN_PT = 3.0
MAX_PT = 10.0
PT_TO_M = 0.0254 / 72.0  # 1 pt on paper in metres
# Leader geometry was tuned for 10 pt at 1:100 (≈0.35 m text); it scales with
# the actual text height, with floors so it never collapses onto the hang.
REF_TEXT_M = 10 * PT_TO_M * 100
REF_SIDE_M, MIN_SIDE_M = 4.0, 1.2
REF_FAN_M, MIN_FAN_M = 0.9, 0.3
REF_NUDGE_M, MIN_NUDGE_M = 0.25, 0.08
# Hangs whose front/rear picks line up along plan X (within ~15°) get their
# marks split vertically: front above, rear below, with a clear gap of
# ALIGNED_GAP_TEXT_HEIGHTS × text height between them. Leaders get an elbow
# so they run parallel instead of on top of each other.
ALIGNED_AXIS_TOL = 0.26  # |sin| of hang-axis angle to X
ALIGNED_GAP_TEXT_HEIGHTS = 1.0

# Filled in run() once the scale is known
MARK = {"pt": MAX_PT, "text_m": REF_TEXT_M, "k": 1.0, "scale": 100.0}
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
    try:
        vs.Record(h, RECORD_NAME)
    except Exception:
        return False
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


def set_object_z(h, z_m):
    """Set an object's global / insertion Z (ArrayCalc frame height → doc units)."""
    if not h:
        return False
    z_doc = float(m_to_doc(z_m))
    # Screen-plane objects ignore height in 3D — force layer plane first
    for ov in (1160, 1161):
        try:
            vs.SetObjectVariableBoolean(h, ov, False)
        except Exception:
            pass
    try:
        vs.SetPlanarRef(h, -1)
    except Exception:
        pass

    cur_z = 0.0
    try:
        mat = vs.GetEntityMatrix(h)
        if isinstance(mat, (list, tuple)) and len(mat) >= 13 and mat[0] in (True, 1):
            cur_z = float(mat[3])
        elif isinstance(mat, (list, tuple)) and len(mat) >= 3:
            cur_z = float(mat[2])
    except Exception:
        cur_z = 0.0

    dz = z_doc - cur_z
    try:
        vs.Move3DObj(h, 0.0, 0.0, dz)
        return True
    except Exception:
        pass
    try:
        mat = vs.GetEntityMatrix(h)
        if isinstance(mat, (list, tuple)) and len(mat) >= 13 and mat[0] in (True, 1):
            _ok, ox, oy, _oz, ux, uy, uz, vx, vy, vz, wx, wy, wz = mat[:13]
            return bool(vs.SetEntityMatrix(h, ox, oy, z_doc, ux, uy, uz, vx, vy, vz, wx, wy, wz))
        if isinstance(mat, (list, tuple)) and len(mat) >= 12:
            ox, oy = mat[0], mat[1]
            rest = mat[3:12]
            return bool(vs.SetEntityMatrix(h, ox, oy, z_doc, *rest))
    except Exception:
        pass
    return False


def set_hoist_z(h, z_m):
    return set_object_z(h, z_m)


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
    # After Reset — PIO rebuild can drop Z; set insertion Z last
    set_hoist_z(h, z_m)
    return h, pio_name


def _style_load_text(text_h, load_text, hoist_id, tip_dx, tip_dy):
    try:
        vs.SetTextJust(text_h, 1 if tip_dx >= 0 else 3)
    except Exception:
        pass
    try:
        vs.SetTextVerticalJust(text_h, 3 if tip_dy >= 0 else 1)
    except Exception:
        pass
    try:
        vs.SetName(text_h, f"AC Load {hoist_id}")
    except Exception:
        pass
    try:
        vs.SetTextSize(text_h, 0, len(load_text), round(MARK["pt"], 1))
    except Exception:
        pass


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


def _is_x_aligned(pick_kind, along_xy):
    kind = (pick_kind or "").lower()
    return kind in ("front", "rear") and abs(along_xy[1]) < ALIGNED_AXIS_TOL


def _tag_offset_m(pick_kind, tag_side, along_xy=(1.0, 0.0)):
    """Front/rear fan along the hang axis; LEFT/RIGHT stay on world ±X only.

    For hangs aligned with X the fan is purely horizontal, so front/rear are
    split vertically by half the gap each (front up, rear down)."""
    ax, ay = along_xy
    if _is_x_aligned(pick_kind, along_xy):
        ay = 0.0
    # World horizontal only — do not rotate LEFT/RIGHT with array aiming
    x_sign = -1.0 if (tag_side or "right").lower() == "left" else 1.0
    side_m = max(MIN_SIDE_M, REF_SIDE_M * MARK["k"])
    fan_m = max(MIN_FAN_M, REF_FAN_M * MARK["k"])
    kind = (pick_kind or "").lower()
    if kind == "front":
        fx, fy = ax * fan_m, ay * fan_m
    elif kind == "rear":
        fx, fy = -ax * fan_m, -ay * fan_m
    else:
        fx, fy = 0.0, 0.0
    if _is_x_aligned(pick_kind, along_xy):
        half_gap = 0.5 * ALIGNED_GAP_TEXT_HEIGHTS * MARK["text_m"]
        fy = half_gap if kind == "front" else -half_gap
    return x_sign * side_m + fx, fy


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


def create_leader_line(x0, y0, tip_x, tip_y, z_m, name, elbow=None):
    """Callout leader from motor to tag tip, at motor height.

    elbow=(x, y) adds a bend point (motor → elbow → tip).
    Exactly one object is created: each fallback runs only if the previous
    attempt produced nothing, and a half-built attempt is deleted."""
    z = float(m_to_doc(z_m))
    pts = [(float(x0), float(y0))]
    if elbow:
        pts.append((float(elbow[0]), float(elbow[1])))
    pts.append((float(tip_x), float(tip_y)))

    def poly3d():
        vs.BeginPoly3D()
        for px, py in pts:
            vs.Add3DPt(px, py, z)
        vs.EndPoly3D()

    def poly2d():
        vs.OpenPoly()
        vs.BeginPoly()
        for px, py in pts:
            vs.AddPoint(px, py)
        vs.EndPoly()

    def line2d():
        # Straight fallback only when there is no bend to draw
        vs.MoveTo(pts[0][0], pts[0][1])
        vs.LineTo(pts[-1][0], pts[-1][1])

    attempts = [(poly3d, False), (poly2d, True)]
    if not elbow:
        attempts.append((line2d, True))

    h = None
    for build, needs_z in attempts:
        try:
            before = vs.LNewObj()
        except Exception:
            before = None
        ok = True
        try:
            build()
        except Exception:
            ok = False
        new = _created_since(before)
        if new is not None and not ok:
            try:
                vs.DelObject(new)
            except Exception:
                pass
            new = None
        if new is not None:
            h = new
            if needs_z:
                set_object_z(h, z_m)
            break
    if h is not None and name:
        try:
            vs.SetName(h, name)
        except Exception:
            pass
    return h


def delete_previous_load_marks():
    """Remove load texts/leaders from earlier runs (named 'AC Load …')."""
    found = []

    def collect(h):
        try:
            nm = vs.GetName(h) or ""
        except Exception:
            nm = ""
        if nm.startswith("AC Load"):
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


def snap_text_corner_to(text_h, tip_x, tip_y, x_dir, y_dir):
    """Move text so the box corner facing the leader sits exactly on the tip."""
    try:
        bb = vs.GetBBox(text_h)
        if len(bb) == 2:
            (x1, y1), (x2, y2) = bb
        else:
            x1, y1, x2, y2 = bb[:4]
    except Exception:
        return False
    left, right = min(x1, x2), max(x1, x2)
    bottom, top = min(y1, y2), max(y1, y2)
    cx = left if x_dir >= 0 else right
    cy = bottom if y_dir >= 0 else top
    dx, dy = float(tip_x) - cx, float(tip_y) - cy
    if abs(dx) < 1e-9 and abs(dy) < 1e-9:
        return True
    try:
        vs.HMove(text_h, dx, dy)
        return True
    except Exception:
        return False


def place_load_mark(
    x_doc, y_doc, z_m, load_text, hoist_id, pick_kind="", tag_side="right", along_xy=(1.0, 0.0)
):
    """Leader + load text at motor Z; side from dialog, front/rear along hang axis."""
    if not load_text:
        return None

    x0 = float(x_doc)
    y0 = float(y_doc)
    tip_dx_m, tip_dy_m = _tag_offset_m(pick_kind, tag_side, along_xy)
    tip_x = x0 + m_to_doc(tip_dx_m)
    tip_y = y0 + m_to_doc(tip_dy_m)
    aligned = _is_x_aligned(pick_kind, along_xy)
    elbow = None
    if aligned:
        # Leader: short 45° kink up/down at the motor, then horizontal to the
        # tag, so front and rear leaders run parallel one gap apart.
        x_dir = 1.0 if tip_dx_m >= 0 else -1.0
        kink_m = min(abs(tip_dy_m), 0.5 * abs(tip_dx_m))
        elbow = (x0 + m_to_doc(x_dir * kink_m), tip_y)
        ux, uy = x_dir, 0.0
    else:
        # Nudge text a bit further along the same direction as the leader
        length = (tip_dx_m * tip_dx_m + tip_dy_m * tip_dy_m) ** 0.5
        if length < 1e-6:
            ux, uy = 1.0, 0.0
        else:
            ux, uy = tip_dx_m / length, tip_dy_m / length
    # Text corner sits exactly on the leader end (snapped after sizing below)
    text_x, text_y = tip_x, tip_y

    create_leader_line(x0, y0, tip_x, tip_y, z_m, f"AC Load ldr {hoist_id}", elbow)

    try:
        vs.MoveTo(text_x, text_y)
        try:
            vs.TextSize(round(MARK["pt"], 1))
        except Exception:
            pass
        text_h = vs.CreateText(load_text)
    except Exception:
        return None
    if not text_h:
        return None

    _style_load_text(text_h, load_text, hoist_id, tip_dx_m, tip_dy_m)
    try:
        vs.ResetObject(text_h)
    except Exception:
        pass
    snap_text_corner_to(text_h, tip_x, tip_y, tip_dx_m, tip_dy_m)
    set_object_z(text_h, z_m)
    return text_h


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
    d = vs.CreateLayout("Place ArrayCalc Hoists", True, "Place", "Cancel")
    STATE.dialog = d
    vs.CreateStaticText(d, K_TITLE, "Flown sources only. Default = front + rear picks.", -1)
    vs.CreateStaticText(d, K_HELP, "Tick a source only if it is actually a single-point hang:", -1)
    vs.CreateStaticText(d, K_FILE_LABEL, csv_path or "", -1)
    vs.CreateStaticText(
        d,
        K_TAG_HELP,
        "Load tag side per source (LEFT/RIGHT = plan −X / +X; use opposite sides if hangs sit close):",
        -1,
    )
    preview = compute_mark_size(scale, DEFAULT_TEXT_HEIGHT_M)
    vs.CreateStaticText(
        d,
        K_TEXT_H_LABEL,
        f"Layer scale 1:{scale:g}. Load text height in model (m):",
        -1,
    )
    vs.CreateEditReal(d, K_TEXT_H_EDIT, 1, DEFAULT_TEXT_HEIGHT_M, 8)
    vs.SetFirstLayoutItem(d, K_TITLE)
    vs.SetBelowItem(d, K_TITLE, K_HELP, 0, 6)
    vs.SetBelowItem(d, K_HELP, K_FILE_LABEL, 0, 6)
    vs.SetBelowItem(d, K_FILE_LABEL, K_TEXT_H_LABEL, 0, 8)
    vs.SetRightItem(d, K_TEXT_H_LABEL, K_TEXT_H_EDIT, 8, 0)

    prev = K_TEXT_H_LABEL
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
        vs.CreateCheckBox(d, left_id, f"{src}  — tags LEFT")
        vs.CreateCheckBox(d, right_id, f"{src}  — tags RIGHT")
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

    placed = 0
    failed = 0
    texts = 0
    removed_marks = delete_previous_load_marks()
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
        if place_load_mark(
            x, y, z, load_text, hoist_id, r.get("pick_kind"), tag_side, along_xy
        ):
            texts += 1

    left_src = [s for s, side in STATE.tag_side.items() if side == "left"]
    right_src = [s for s, side in STATE.tag_side.items() if side == "right"]
    msg = (
        f"Placed {placed} hoist(s) from:\n{csv_path}\n\n"
        f"Insertion Z = ArrayCalc frame height (m → doc units).\n"
        f"Old load marks/leaders removed: {removed_marks}\n"
        f"Load marks: {texts}  (layer 1:{MARK['scale']:g} → {MARK['pt']:.1f} pt, "
        f"≈{MARK['text_m']:.2f} m tall in model)\n"
        f"Tags LEFT: {', '.join(left_src) if left_src else '(none)'}\n"
        f"Tags RIGHT: {', '.join(right_src) if right_src else '(none)'}\n"
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
