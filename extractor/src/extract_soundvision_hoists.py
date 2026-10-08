#!/usr/bin/env python3
"""Extract flown-array hoist pick points + motor loads from an L-Acoustics
Soundvision report PDF and write them in the SAME CSV format as
extract_arraycalc_hoists.py (so ACHOISTS / the Vectorworks placers read it
unchanged).

CSV columns (identical to the ArrayCalc extractor):
  source, pick_kind, x_m, y_m, z_m, hole, weight_kg, total_weight_kg, system,
  horizontal_aiming_deg, flying_frame_id, source_group_id, single_available

Conventions:
  - Only flown sources ("Configuration: ..., flown array") that have motors and
    pickup positions. Stacked / motor-less sources are skipped and listed.
  - 2-motor source -> "front" + "rear" rows, weight_kg = Front/Rear motor load,
    single_available = 0 (Soundvision gives no single-pick option).
  - 1-motor source (Soundvision prints "# motors: 1", a single "Front pickup
    position" line and a single "Front motor load" line) -> one "front" row
    (placed by default) + an identical "single" row with single_available = 1.
    The placers use front/rear rows OR the single row, never both, so the
    hoist is placed exactly once; ticking "Single-point" only relabels it.
  - x/y/z = the pickup point itself (metres). Soundvision reports each pickup's
    own Z, so z_m is per pick (ArrayCalc only has the frame origin Z).
  - hole = the pickup index Soundvision prints before the coordinates.
  - flying_frame_id = running source number (the placers pair front/rear by
    it), source_group_id = running Soundvision group number.
  - Metres and kilograms only. If the report header (Distance unit / Weight
    unit) or a pickup/load line shows any other unit, the run stops with an
    error - set Soundvision to m / kg and export the report again.
  - Sources outside any group get source_group_id = 0.

Usage:
  python extract_soundvision_hoists.py
  python extract_soundvision_hoists.py "report.pdf" [-o out.csv]

Double-click / no arguments: opens a file picker. The CSV is written next to
the chosen PDF as <pdf name>_hoist_picks.csv.

Library: pypdf (pure Python, no poppler / system binaries; freezes cleanly
with PyInstaller / py2app).

Module use:
  from extract_soundvision_hoists import extract_soundvision
  rows = extract_soundvision("report.pdf")            # list of CSV-row dicts
  res  = extract_soundvision_report("report.pdf")     # rows + warnings + info
"""

from __future__ import annotations

import argparse
import csv
import logging
import re
import sys
import traceback
from dataclasses import dataclass, field
from pathlib import Path

FIELDNAMES = [
    "source", "pick_kind", "x_m", "y_m", "z_m", "hole", "weight_kg",
    "total_weight_kg", "system", "horizontal_aiming_deg", "flying_frame_id",
    "source_group_id", "single_available",
]

# Only metric reports are supported (no ft / lb conversion by design).
LENGTH_UNITS = {"m": 1.0}
WEIGHT_UNITS = {"kg": 1.0}


class SoundvisionParseError(ValueError):
    """The report cannot be read without guessing (units, structure...)."""


@dataclass
class SVSource:
    name: str
    group: str
    group_index: int
    index: int                      # running source number (1-based)
    configuration: str = ""
    bumper: str = ""
    motors: int | None = None
    picks: list = field(default_factory=list)   # (kind, hole, x, y, z) in metres
    loads: dict = field(default_factory=dict)   # kind -> kg
    total_weight_kg: float | None = None
    azimuth_deg: float | None = None
    system: str = ""
    flown: bool = False


@dataclass
class SVResult:
    rows: list
    sources: list
    skipped: list                    # (source name, reason)
    warnings: list
    info: dict


# ----------------------------------------------------------------- text ----

_NUM = r"[-+]?\d+(?:[.,]\d+)?(?:[eE][-+]?\d+)?"
_PAGE_FOOTER = re.compile(r"^\s*Page\s+\d+\s+of\s+\d+\s*$", re.I | re.M)


def _num(s: str) -> float:
    return float(s.replace(",", "."))


def pdf_to_text(pdf_path) -> str:
    """All pages as one string, page footers removed (so blocks that cross a
    page break read as one block)."""
    try:
        from pypdf import PdfReader
    except ImportError as e:  # pragma: no cover
        raise SystemExit("pypdf is required:  pip install pypdf") from e
    # Haru-generated reports trigger harmless ToUnicode CMap warnings
    logging.getLogger("pypdf").setLevel(logging.ERROR)
    reader = PdfReader(str(pdf_path))
    pages = [(p.extract_text() or "") for p in reader.pages]
    text = "\n".join(pages)
    return _PAGE_FOOTER.sub("", text)


def _unit(token: str, table: dict, what: str, where: str) -> float:
    key = (token or "").strip().lower().rstrip(".")
    if key not in table:
        want = "/".join(table)
        raise SoundvisionParseError(
            f"{where} uses {what} unit '{token}'. Only {want} is supported - set "
            f"Soundvision's {what} unit to {want} and export the report again.")
    return table[key]


# Header / block patterns. \s* spans newlines because pypdf sometimes breaks
# "Distance unit:" and its value onto separate lines.
_RE_HDR_DIST = re.compile(r"Distance\s+unit\s*:\s*(\S+)", re.I)
_RE_HDR_WEIGHT = re.compile(r"Weight\s+unit\s*:\s*(\S+)", re.I)
_RE_HDR_SCALE = re.compile(r"Scale\s+factor\s*:\s*(" + _NUM + ")", re.I)
_RE_HDR_FILE = re.compile(r"File\s+name\s*:\s*(.+)", re.I)
_RE_HDR_VERSION = re.compile(r"Version\s*:\s*(\S+)", re.I)

_RE_HEADING = re.compile(r"^\s*\d+\s*\.\s*(Group|Source)\s*:\s*(.*?)\s*$", re.I | re.M)
_RE_CONFIG = re.compile(r"^\s*Configuration\s*:\s*(.+?)\s*$", re.I | re.M)
_RE_BUMPER = re.compile(r"^\s*Bumper\s*:\s*(.+?)\s*$", re.I | re.M)
_RE_MOTORS = re.compile(r"#\s*motors\s*:\s*(\d+)", re.I)
_RE_PICK = re.compile(
    r"(Front|Rear)\s+pickup\s+position\s*"
    r"\(\s*X\s*;\s*Y\s*;\s*Z\s*,\s*([^)\s]+)\s*\)\s*:\s*"
    r"(?:([A-Za-z0-9#\-]+)\s*)?"
    r"\(\s*(" + _NUM + r")\s*;\s*(" + _NUM + r")\s*;\s*(" + _NUM + r")\s*\)",
    re.I,
)
_RE_LOAD = re.compile(
    r"(Front|Rear)\s+motor\s+load\s*:\s*(" + _NUM + r")\s*([A-Za-z]+)", re.I)
_RE_TOTAL = re.compile(
    r"Total\s+weight\s*\(\s*Enclosures\s*\+\s*Frames\s*\)\s*:\s*(" + _NUM + r")\s*([A-Za-z]+)",
    re.I)
_RE_AZIMUTH = re.compile(r"^\s*Azimuth\s*:\s*(" + _NUM + ")", re.I | re.M)
_RE_ENCLOSURE = re.compile(r"^\s*Enclosure\s*#\s*\d+\s*-\s*(.+?)\s*$", re.I | re.M)
# Enclosure table "#1  KARA II  5 ...": pypdf gives "#1\nKARA II\n5...",
# a layout text extractor gives one row with 2+ spaces between columns.
_RE_TABLE_TYPE = re.compile(
    r"^[ \t]*#\d+[ \t]*(?:\n[ \t]*|[ \t]+)([A-Za-z][A-Za-z0-9\-]*(?: [A-Za-z0-9\-]+)*)[ \t]*(?=\n|  |\t)",
    re.M)


def parse_report_text(text: str) -> SVResult:
    warnings: list[str] = []
    info: dict = {}

    m = _RE_HDR_FILE.search(text)
    info["file_name"] = m.group(1).strip() if m else ""
    m = _RE_HDR_VERSION.search(text)
    info["version"] = m.group(1) if m else ""

    m = _RE_HDR_DIST.search(text)
    hdr_len = m.group(1) if m else None
    m = _RE_HDR_WEIGHT.search(text)
    hdr_wt = m.group(1) if m else None
    if hdr_len is None:
        warnings.append("No 'Distance unit' in report header; using the unit printed on each pickup line.")
    else:
        _unit(hdr_len, LENGTH_UNITS, "distance", "report header")
    if hdr_wt is None:
        warnings.append("No 'Weight unit' in report header; using the unit printed on each load line.")
    else:
        _unit(hdr_wt, WEIGHT_UNITS, "weight", "report header")
    info["distance_unit"] = hdr_len or ""
    info["weight_unit"] = hdr_wt or ""
    m = _RE_HDR_SCALE.search(text)
    if m:
        info["scale_factor"] = _num(m.group(1))
        if abs(info["scale_factor"] - 1.0) > 1e-9:
            warnings.append(
                f"Report 'Scale factor' is {m.group(1)} (not 1). Coordinates are written "
                "exactly as printed - check whether they need rescaling.")

    # ---- split into Group / Source blocks
    heads = list(_RE_HEADING.finditer(text))
    sources: list[SVSource] = []
    groups: list[str] = []
    group_sources: dict[int, int] = {}
    cur_group, cur_gi = "", 0
    for i, h in enumerate(heads):
        kind, name = h.group(1).lower(), h.group(2).strip()
        body = text[h.end(): heads[i + 1].start() if i + 1 < len(heads) else len(text)]
        if kind == "group":
            groups.append(name)
            cur_group, cur_gi = name, len(groups)
            group_sources.setdefault(cur_gi, 0)
            continue
        group_sources[cur_gi] = group_sources.get(cur_gi, 0) + 1
        sources.append(_parse_source(name, body, cur_group, cur_gi, len(sources) + 1,
                                     hdr_len, hdr_wt, warnings))
    info["groups"] = groups
    info["empty_groups"] = [g for gi, g in enumerate(groups, 1) if not group_sources.get(gi)]
    if not sources:
        raise SoundvisionParseError("No 'N. Source: <name>' blocks found - is this a Soundvision report?")

    # ---- duplicate names would merge in the placers (they key on source)
    seen: dict[str, int] = {}
    for s in sources:
        if s.name in seen:
            seen[s.name] += 1
            new = f"{s.name} ({seen[s.name]})"
            warnings.append(f"Duplicate source name '{s.name}' renamed to '{new}'.")
            s.name = new
        else:
            seen[s.name] = 1

    rows, skipped = _rows_from_sources(sources, warnings)
    return SVResult(rows=rows, sources=sources, skipped=skipped, warnings=warnings, info=info)


def _parse_source(name, body, group, gi, idx, hdr_len, hdr_wt, warnings) -> SVSource:
    s = SVSource(name=name, group=group, group_index=gi, index=idx)
    where = f"source '{name}'"

    m = _RE_CONFIG.search(body)
    s.configuration = m.group(1) if m else ""
    s.flown = "flown" in s.configuration.lower()
    m = _RE_BUMPER.search(body)
    s.bumper = m.group(1) if m else ""
    m = _RE_MOTORS.search(body)
    s.motors = int(m.group(1)) if m else None

    for pm in _RE_PICK.finditer(body):
        side, ustr, hole, x, y, z = pm.groups()
        if hdr_len and ustr.lower() != hdr_len.lower():
            raise SoundvisionParseError(
                f"{where}: pickup unit '{ustr}' differs from header distance unit '{hdr_len}'.")
        k = _unit(ustr, LENGTH_UNITS, "distance", where)
        kind = side.lower()
        if "," in x + y + z:
            warnings.append(f"{where}: comma in pickup coordinates read as a decimal point - check.")
        s.picks.append((kind, hole or "", _num(x) * k, _num(y) * k, _num(z) * k))

    for lm in _RE_LOAD.finditer(body):
        side, val, ustr = lm.groups()
        if hdr_wt and ustr.lower().rstrip("s") != hdr_wt.lower().rstrip("s"):
            raise SoundvisionParseError(
                f"{where}: load unit '{ustr}' differs from header weight unit '{hdr_wt}'.")
        kind = side.lower()
        if "," in val:
            warnings.append(f"{where}: load '{val}' has a comma - read as a decimal point, check "
                            "it is not a thousands separator.")
        if kind in s.loads:
            warnings.append(f"{where}: '{kind}' motor load listed twice; keeping the first.")
            continue
        s.loads[kind] = _num(val) * _unit(ustr, WEIGHT_UNITS, "weight", where)

    m = _RE_TOTAL.search(body)
    if m:
        s.total_weight_kg = _num(m.group(1)) * _unit(m.group(2), WEIGHT_UNITS, "weight", where)
    m = _RE_AZIMUTH.search(body)
    s.azimuth_deg = _num(m.group(1)) if m else None

    types = []
    for em in list(_RE_TABLE_TYPE.finditer(body)) + list(_RE_ENCLOSURE.finditer(body)):
        t = em.group(1).strip()
        if t not in types:
            types.append(t)
    s.system = "+".join(types) if types else s.bumper
    return s


def _r(v, nd):
    return None if v is None else round(float(v), nd)


def _hole(h):
    return int(h) if h and h.isdigit() else h


def _rows_from_sources(sources, warnings):
    rows, skipped = [], []
    for s in sources:
        where = f"source '{s.name}'"
        if not s.flown:
            skipped.append((s.name, f"not flown ({s.configuration or 'no configuration line'})"))
            continue
        if not s.motors:
            skipped.append((s.name, "flown but no motors"))
            continue
        if not s.picks:
            skipped.append((s.name, f"{s.motors} motor(s) but no pickup positions found"))
            warnings.append(f"{where}: '# motors: {s.motors}' but no pickup position lines - skipped.")
            continue
        if len(s.picks) != s.motors:
            warnings.append(f"{where}: '# motors: {s.motors}' but {len(s.picks)} pickup position(s) found.")

        def base(kind, hole, x, y, z, w, single_ok):
            return {
                "source": s.name,
                "pick_kind": kind,
                "x_m": _r(x, 4), "y_m": _r(y, 4), "z_m": _r(z, 4),
                "hole": _hole(hole),
                "weight_kg": _r(w, 2),
                "total_weight_kg": _r(s.total_weight_kg, 2),
                "system": s.system,
                "horizontal_aiming_deg": s.azimuth_deg,
                "flying_frame_id": s.index,
                "source_group_id": s.group_index,
                "single_available": "1" if single_ok else "0",
            }

        if s.motors == 1 or len(s.picks) == 1:
            # Soundvision labels the only pickup/load "Front"
            kind0, hole, x, y, z = s.picks[0]
            w = s.loads.get(kind0)
            if w is None and len(s.loads) == 1:
                w = next(iter(s.loads.values()))
            if w is None:
                w = s.total_weight_kg
                if w is not None:
                    warnings.append(f"{where}: 1 motor, no motor load line - using total weight {w:g} kg.")
            if w is None:
                warnings.append(f"{where}: no load found - weight_kg left blank.")
            elif s.total_weight_kg and abs(w - s.total_weight_kg) > max(2.0, 0.01 * s.total_weight_kg):
                warnings.append(f"{where}: 1-motor load {w:g} kg != total weight {s.total_weight_kg:g} kg.")
            rows.append(base("front", hole, x, y, z, w, True))
            rows.append(base("single", hole, x, y, z, w, True))
            continue

        by_kind = {}
        for p in s.picks:
            if p[0] in by_kind:
                warnings.append(f"{where}: duplicate '{p[0]}' pickup line ignored.")
                continue
            by_kind[p[0]] = p
        for kind in ("front", "rear"):
            if kind not in by_kind:
                warnings.append(f"{where}: no {kind} pickup position.")
                continue
            _, hole, x, y, z = by_kind[kind]
            w = s.loads.get(kind)
            if w is None:
                warnings.append(f"{where}: no {kind} motor load - weight_kg left blank.")
            rows.append(base(kind, hole, x, y, z, w, False))
        extra = set(by_kind) - {"front", "rear"}
        if extra:
            warnings.append(f"{where}: unlabelled pickup line(s) next to front/rear ignored.")
        if s.total_weight_kg is not None and "front" in s.loads and "rear" in s.loads:
            diff = s.loads["front"] + s.loads["rear"] - s.total_weight_kg
            if abs(diff) > max(2.0, 0.01 * s.total_weight_kg):
                warnings.append(
                    f"{where}: front+rear load {s.loads['front'] + s.loads['rear']:g} kg "
                    f"!= total weight {s.total_weight_kg:g} kg.")
    return rows, skipped


# ------------------------------------------------------------------ API ----

def extract_soundvision_report(pdf_path) -> SVResult:
    return parse_report_text(pdf_to_text(pdf_path))


def extract_soundvision(pdf_path) -> list[dict]:
    """Rows ready for csv.DictWriter(fieldnames=FIELDNAMES)."""
    return extract_soundvision_report(pdf_path).rows


def write_csv(rows, out_path) -> None:
    with Path(out_path).open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=FIELDNAMES)
        w.writeheader()
        w.writerows(rows)


# ------------------------------------------------------------------ CLI ----

def pick_pdf_dialog(initial_dir: Path | None = None) -> Path | None:
    """File picker - choose any Soundvision report PDF."""
    try:
        import tkinter as tk
        from tkinter import filedialog
    except Exception as e:
        print(f"No file-dialog support ({e}). Pass the PDF path as an argument.")
        return None

    root = tk.Tk()
    root.withdraw()
    root.attributes("-topmost", True)
    start = str(initial_dir) if initial_dir and initial_dir.is_dir() else str(Path.home())
    path = filedialog.askopenfilename(
        parent=root,
        title="Select Soundvision report (.pdf)",
        initialdir=start,
        filetypes=[("Soundvision report", "*.pdf"), ("All files", "*.*")],
    )
    root.destroy()
    return Path(path) if path else None


def pause_if_needed(interactive: bool) -> None:
    if not interactive:
        return
    try:
        input("\nPress Enter to close…")
    except EOFError:
        pass


def run(pdf: Path, output: Path | None) -> int:
    if not pdf.exists():
        print(f"File not found: {pdf}")
        return 1
    out = output or pdf.with_name(pdf.stem + "_hoist_picks.csv")
    print(f"Reading: {pdf}")
    try:
        res = extract_soundvision_report(pdf)
    except SoundvisionParseError as e:
        print(f"STOPPED - {e}")
        return 3
    for w in res.warnings:
        print(f"  WARNING: {w}")
    for name, why in res.skipped:
        print(f"  skipped: {name} - {why}")
    if not res.rows:
        print("No flown sources with motors found.")
        return 2
    write_csv(res.rows, out)
    srcs = list(dict.fromkeys(r["source"] for r in res.rows))
    fr = sum(1 for r in res.rows if r["pick_kind"] in ("front", "rear") and r["single_available"] != "1")
    sg = sum(1 for r in res.rows if r["pick_kind"] == "single")
    print(f"Wrote:   {out}")
    print(f"  units in report: {res.info.get('distance_unit') or '?'} / "
          f"{res.info.get('weight_unit') or '?'}")
    print(f"  sources: {len(srcs)}  2-motor picks: {fr}  1-motor (single) sources: {sg}")
    print("  " + ", ".join(srcs))
    return 0


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    interactive = len(argv) == 0

    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("pdf", nargs="?", type=Path,
                    help="Soundvision report .pdf (optional - file picker opens if omitted)")
    ap.add_argument("-o", "--output", type=Path,
                    help="Output CSV (default: <pdf>_hoist_picks.csv beside the report)")
    args = ap.parse_args(argv)

    pdf = args.pdf
    if pdf is None:
        pdf = pick_pdf_dialog(Path(__file__).resolve().parent)
        if pdf is None:
            print("Cancelled - no report selected.")
            pause_if_needed(interactive)
            return 0
    try:
        code = run(pdf, args.output)
    except Exception:
        traceback.print_exc()
        code = 1
    pause_if_needed(interactive)
    return code


if __name__ == "__main__":
    raise SystemExit(main())
