"""GUI-free extraction logic shared by the Windows and macOS builds.

Input type is detected from the file header (SQLite -> ArrayCalc .dbpr,
%PDF -> Soundvision report) with the extension as a hint. Both extractors
produce the same 13-column CSV, written next to the input as
<input name>_hoist_picks.csv.

Heavy modules (sqlite3, pypdf) are imported only when an extraction runs.
"""

from __future__ import annotations

import csv
import errno
import os
import tempfile
import traceback
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

SQLITE_MAGIC = b"SQLite format 3\x00"
PDF_MAGIC = b"%PDF"
OUT_SUFFIX = "_hoist_picks.csv"
KIND_LABEL = {"arraycalc": "ArrayCalc project", "soundvision": "Soundvision report"}


class ExtractError(Exception):
    """Expected failure with a short, user-readable reason."""


@dataclass
class Result:
    ok: bool
    message: str                      # one-line status for the UI
    kind: str = ""
    points: int = 0                   # rows placed by default (front + rear)
    sources: int = 0
    out_path: str = ""
    renamed: bool = False             # target was locked -> wrote a suffixed name
    warnings: list = field(default_factory=list)
    log_path: str = ""


# ------------------------------------------------------------ detection ----

def detect_kind(path: Path) -> str:
    """'arraycalc' or 'soundvision'; raises ExtractError otherwise."""
    if not path.is_file():
        raise ExtractError("File not found.")
    try:
        with path.open("rb") as f:
            head = f.read(1024)
    except OSError as e:
        raise ExtractError(f"Cannot open the file ({e.strerror or e}).")
    ext = path.suffix.lower()
    if head.startswith(SQLITE_MAGIC):
        return "arraycalc"
    if PDF_MAGIC in head:             # PDF header may follow a few junk bytes
        return "soundvision"
    if not head:
        raise ExtractError("The file is empty.")
    if ext == ".dbpr":
        raise ExtractError("Not a valid ArrayCalc project (the file is damaged or not a .dbpr).")
    if ext == ".pdf":
        raise ExtractError("Not a valid PDF (the file is damaged or not a PDF).")
    raise ExtractError("Unsupported file. Choose an ArrayCalc project (.dbpr) or a Soundvision report (.pdf).")


# ----------------------------------------------------------- extraction ----

def _extract_arraycalc(path: Path):
    import sqlite3
    import extract_arraycalc_hoists as ac
    try:
        con = ac.open_db(path)
    except sqlite3.Error as e:
        raise ExtractError(f"Cannot open the ArrayCalc project ({e}).")
    try:
        return ac.extract(con), []
    except sqlite3.DatabaseError as e:
        msg = str(e)
        if "no such table" in msg or "no such column" in msg:
            raise ExtractError("This database is not an ArrayCalc project (or a version this tool doesn't know).")
        if "locked" in msg:
            raise ExtractError("The project is locked by another program - close it in ArrayCalc and try again.")
        raise ExtractError(f"The ArrayCalc project is damaged or unreadable ({msg}).")
    finally:
        con.close()                   # never keep the .dbpr locked


def _extract_soundvision(path: Path):
    import extract_soundvision_hoists as sv
    try:
        from pypdf.errors import PdfReadError, FileNotDecryptedError
    except Exception:                 # pragma: no cover
        PdfReadError = FileNotDecryptedError = ()
    try:
        res = sv.extract_soundvision_report(path)
    except sv.SoundvisionParseError as e:
        raise ExtractError(str(e))
    except FileNotDecryptedError:
        raise ExtractError("The PDF is password-protected.")
    except PdfReadError as e:
        raise ExtractError(f"The PDF is damaged or unreadable ({e}).")
    return res.rows, list(res.warnings)


def extract_rows(path: Path, kind: str):
    if kind == "arraycalc":
        rows, warnings = _extract_arraycalc(path)
        if not rows:
            raise ExtractError("No flown pick-up points in this ArrayCalc project.")
    else:
        rows, warnings = _extract_soundvision(path)
        if not rows:
            raise ExtractError("No flown sources with motors in this Soundvision report.")
    return rows, warnings


def count_points(rows) -> tuple[int, int]:
    """(pick-up points placed by default, sources). Optional 'single' rows are
    alternatives to front/rear, so they are not counted."""
    pts = sum(1 for r in rows if str(r.get("pick_kind", "")).lower() in ("front", "rear"))
    return pts, len({r.get("source") for r in rows})


# --------------------------------------------------------------- output ----

def output_path(path: Path) -> Path:
    return path.with_name(path.stem + OUT_SUFFIX)


def _locked(e: OSError) -> bool:
    return isinstance(e, PermissionError) or e.errno in (errno.EACCES, errno.EBUSY, errno.EPERM)


def write_csv(rows, target: Path) -> tuple[Path, bool]:
    """Write the CSV (same bytes as the stand-alone scripts). If the target is
    open/locked (e.g. in Excel), use '<name> (2).csv', '(3)'... instead."""
    fieldnames = list(rows[0].keys())
    candidates = [target] + [target.with_name(f"{target.stem} ({i}){target.suffix}") for i in range(2, 100)]
    last = None
    for i, p in enumerate(candidates):
        try:
            with p.open("w", newline="", encoding="utf-8") as f:
                w = csv.DictWriter(f, fieldnames=fieldnames)
                w.writeheader()
                w.writerows(rows)
            return p, i > 0
        except OSError as e:
            if not _locked(e):
                raise ExtractError(f"Cannot write the CSV ({e.strerror or e}).")
            last = e
    raise ExtractError(f"Cannot write the CSV - the folder is read-only or the file is locked ({last}).")


def _write_crash_log(path: Path | None) -> str:
    text = f"{datetime.now():%Y-%m-%d %H:%M:%S}\n{traceback.format_exc()}"
    name = (path.stem if path else "extractor") + "_extractor_error.log"
    for folder in ([path.parent] if path else []) + [Path(tempfile.gettempdir())]:
        try:
            p = folder / name
            p.write_text(text, encoding="utf-8")
            return str(p)
        except OSError:
            continue
    return ""


# ------------------------------------------------------------------ API ----

def run_extraction(file_path) -> Result:
    path = Path(str(file_path).strip().strip('"')) if file_path else None
    if not path or not str(path):
        return Result(False, "Choose a file first.")
    try:
        kind = detect_kind(path)
        rows, warnings = extract_rows(path, kind)
        pts, srcs = count_points(rows)
        out, renamed = write_csv(rows, output_path(path))
        msg = f"Done: {pts} pick-up point{'s' * (pts != 1)} ({srcs} source{'s' * (srcs != 1)}) -> {out.name}"
        if renamed:
            msg += f"   ({output_path(path).name} is open in another program, so a new name was used)"
        if warnings:
            msg += f"   Warning{'s' * (len(warnings) > 1)}: " + "; ".join(warnings[:2])
            if len(warnings) > 2:
                msg += f" (+{len(warnings) - 2} more)"
        return Result(True, msg, kind, pts, srcs, str(out), renamed, warnings)
    except ExtractError as e:
        return Result(False, f"Failed: {e}")
    except Exception:
        log = _write_crash_log(path)
        where = f" Details: {Path(log).name}" if log else ""
        return Result(False, f"Failed: unexpected error.{where}", log_path=log)
