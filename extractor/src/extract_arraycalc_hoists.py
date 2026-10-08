#!/usr/bin/env python3
"""Extract flown-array pick points from a d&b ArrayCalc .dbpr (SQLite) project.

Defaults:
  - Skip ground-stacked sources (Mounting != 0)
  - Emit front + rear picks for every flown frame
  - Also emit single picks when ArrayCalc has a valid single-pick hole
    (the Vectorworks placer decides whether to use them via checkboxes)

Usage:
  python extract_arraycalc_hoists.py
  python extract_arraycalc_hoists.py "path/to/project.dbpr" [-o out.csv]

Double-click / no arguments: opens a file picker so you can choose among
several .dbpr files in any folder. CSV is written next to the chosen project.
"""

from __future__ import annotations

import argparse
import csv
import sqlite3
import sys
import traceback
from pathlib import Path


MOUNTING_FLOWN = 0


def open_db(path: Path) -> sqlite3.Connection:
    # Read-only so it works even while ArrayCalc has the project open
    uri = path.resolve().as_uri() + "?mode=ro"
    con = sqlite3.connect(uri, uri=True)
    con.row_factory = sqlite3.Row
    return con


def extract(con: sqlite3.Connection) -> list[dict]:
    rows = con.execute(
        """
        SELECT f.FlyingFrameId, f.SourceGroupId,
               s.Name AS SourceName, s.OrderIndex, s.Mounting,
               a.System, a.HorizontalAiming, a.OriginZ AS ArrOriginZ,
               f.FrontPickPointHole, f.RearPickPointHole, f.SinglePickPointHole,
               f.FrontPickX, f.FrontPickY, f.RearPickX, f.RearPickY,
               f.SinglePickX, f.SinglePickY,
               f.FrontPickPointWeight, f.RearPickPointWeight, f.TotalWeight,
               f.PositionIndex
        FROM FlyingFrames f
        JOIN SourceGroups s ON s.SourceGroupId = f.SourceGroupId
        LEFT JOIN SourceGroupsAdditionalData a ON a.SourceGroupId = f.SourceGroupId
        WHERE s.Mounting = ?
        ORDER BY s.OrderIndex, f.PositionIndex, f.FlyingFrameId
        """,
        (MOUNTING_FLOWN,),
    ).fetchall()

    out: list[dict] = []
    for r in rows:
        src = r["SourceName"] or f"Frame{r['FlyingFrameId']}"
        single_ok = (
            r["SinglePickPointHole"] is not None
            and float(r["SinglePickPointHole"]) >= 0
        )
        candidates = [
            ("front", r["FrontPickX"], r["FrontPickY"], r["FrontPickPointHole"], r["FrontPickPointWeight"]),
            ("rear", r["RearPickX"], r["RearPickY"], r["RearPickPointHole"], r["RearPickPointWeight"]),
            ("single", r["SinglePickX"], r["SinglePickY"], r["SinglePickPointHole"], r["TotalWeight"]),
        ]
        for kind, x, y, hole, w in candidates:
            if x is None or y is None:
                continue
            if kind == "single" and not single_ok:
                continue
            out.append(
                {
                    "source": src,
                    "pick_kind": kind,
                    "x_m": round(float(x), 4),
                    "y_m": round(float(y), 4),
                    "z_m": round(float(r["ArrOriginZ"] or 0), 4),
                    "hole": hole,
                    "weight_kg": None if w is None else round(float(w), 2),
                    "total_weight_kg": (
                        None
                        if r["TotalWeight"] is None
                        else round(float(r["TotalWeight"]), 2)
                    ),
                    "system": r["System"],
                    "horizontal_aiming_deg": r["HorizontalAiming"],
                    "flying_frame_id": r["FlyingFrameId"],
                    "source_group_id": r["SourceGroupId"],
                    "single_available": "1" if single_ok else "0",
                }
            )
    return out


def pick_dbpr_dialog(initial_dir: Path | None = None) -> Path | None:
    """Windows-friendly file picker — choose any .dbpr, even when several share a folder."""
    try:
        import tkinter as tk
        from tkinter import filedialog
    except Exception as e:
        print(f"No file-dialog support ({e}). Pass the .dbpr path as an argument.")
        return None

    root = tk.Tk()
    root.withdraw()
    root.attributes("-topmost", True)
    start = str(initial_dir) if initial_dir and initial_dir.is_dir() else str(Path.home())
    path = filedialog.askopenfilename(
        parent=root,
        title="Select ArrayCalc project (.dbpr)",
        initialdir=start,
        filetypes=[
            ("ArrayCalc project", "*.dbpr"),
            ("All files", "*.*"),
        ],
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


def run(dbpr: Path, output: Path | None) -> int:
    if not dbpr.exists():
        print(f"File not found: {dbpr}")
        return 1

    out = output or dbpr.with_name(dbpr.stem + "_hoist_picks.csv")
    print(f"Reading: {dbpr}")
    rows = extract(open_db(dbpr))
    if not rows:
        print("No flown pick points found (Mounting=0).")
        return 2

    with out.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)

    sources = sorted({r["source"] for r in rows})
    fr = sum(1 for r in rows if r["pick_kind"] != "single")
    sg = sum(1 for r in rows if r["pick_kind"] == "single")
    print(f"Wrote:   {out}")
    print(f"  sources: {len(sources)}  front/rear: {fr}  single options: {sg}")
    print("  " + ", ".join(sources))
    return 0


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    interactive = len(argv) == 0

    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument(
        "dbpr",
        nargs="?",
        type=Path,
        help="ArrayCalc .dbpr (optional — file picker opens if omitted)",
    )
    ap.add_argument(
        "-o",
        "--output",
        type=Path,
        help="Output CSV (default: <dbpr>_hoist_picks.csv beside the project)",
    )
    args = ap.parse_args(argv)

    dbpr = args.dbpr
    if dbpr is None:
        # Prefer starting the picker in the parent of vw-scripts (project folder)
        script_dir = Path(__file__).resolve().parent
        guess = script_dir.parent if script_dir.name.lower() == "vw-scripts" else script_dir
        dbpr = pick_dbpr_dialog(guess)
        if dbpr is None:
            print("Cancelled — no project selected.")
            pause_if_needed(interactive)
            return 0

    try:
        code = run(dbpr, args.output)
    except Exception:
        traceback.print_exc()
        code = 1

    pause_if_needed(interactive)
    return code


if __name__ == "__main__":
    raise SystemExit(main())
