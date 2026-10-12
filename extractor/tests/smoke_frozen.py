#!/usr/bin/env python3
"""Smoke-test a frozen Pick-up point extractor (no client files).

  python tests/smoke_frozen.py --exe "Pick-up_point_extractor_v1.0.exe"
  python tests/smoke_frozen.py --exe "Pick-up point extractor.app/Contents/MacOS/Pick-up point extractor"

Builds a tiny ArrayCalc-shaped SQLite file and a tiny text PDF in a temp
folder, then checks --version-json and --cli. --script runs the same checks
against a source tree (python --script src/app.py) instead of a frozen binary.
"""

from __future__ import annotations

import argparse
import json
import os
import sqlite3
import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))
import version  # noqa: E402


# ASCII-only so a simple Helvetica PDF content stream round-trips through pypdf.
REPORT = """\
Soundvision
Version: 2026.3.1
File name: synthetic.xmlp
Distance unit:
m
Scale factor:
1.000000
Weight unit:
kg
1. Source: A
1. 1. Physical configuration
Configuration: vertical, flown array
Bumper: K2-BUMP
# motors: 2
Front pickup position (X; Y; Z, m): 1 (1.5; -2; 10)
Rear pickup position (X; Y; Z, m): 2 (1; -2; 10.1)
Position (X; Y; Z, m): 1; -2; 10
Azimuth: 30
Total weight (Enclosures + Frames): 1000 kg
Front motor load: 400 kg
Rear motor load: 600 kg
Enclosure #1 - K2
"""


def _pdf_escape(text: str) -> str:
    return text.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")


def pdf_with_text(text: str) -> bytes:
    """Minimal PDF 1.4 whose extract_text() keeps one line per input line."""
    lines = text.splitlines()
    parts = ["BT", "/F1 10 Tf", "36 800 Td"]
    for i, line in enumerate(lines):
        if i:
            parts.append("0 -12 Td")
        parts.append(f"({_pdf_escape(line)}) Tj")
    parts.append("ET")
    stream = ("\n".join(parts) + "\n").encode("ascii")
    objects = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Count 1 /Kids [3 0 R] >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 900] "
        b"/Contents 4 0 R /Resources << /Font << /F1 5 0 R >> >> >>",
        b"<< /Length %d >>\nstream\n" % len(stream) + stream + b"endstream",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
    ]
    out = bytearray(b"%PDF-1.4\n")
    offsets = [0]
    for i, obj in enumerate(objects, start=1):
        offsets.append(len(out))
        out += f"{i} 0 obj\n".encode("ascii") + obj + b"\nendobj\n"
    xref = len(out)
    out += f"xref\n0 {len(objects) + 1}\n".encode("ascii")
    out += b"0000000000 65535 f \n"
    for off in offsets[1:]:
        out += f"{off:010d} 00000 n \n".encode("ascii")
    out += (
        f"trailer << /Size {len(objects) + 1} /Root 1 0 R >>\n"
        f"startxref\n{xref}\n%%EOF\n"
    ).encode("ascii")
    return bytes(out)


def write_synthetic_dbpr(path: Path) -> None:
    con = sqlite3.connect(path)
    con.executescript(
        """
        CREATE TABLE SourceGroups (
            SourceGroupId INTEGER, Name TEXT, OrderIndex INTEGER, Mounting INTEGER
        );
        CREATE TABLE SourceGroupsAdditionalData (
            SourceGroupId INTEGER, System TEXT, HorizontalAiming REAL, OriginZ REAL
        );
        CREATE TABLE FlyingFrames (
            FlyingFrameId INTEGER, SourceGroupId INTEGER,
            FrontPickPointHole REAL, RearPickPointHole REAL, SinglePickPointHole REAL,
            FrontPickX REAL, FrontPickY REAL, RearPickX REAL, RearPickY REAL,
            SinglePickX REAL, SinglePickY REAL,
            FrontPickPointWeight REAL, RearPickPointWeight REAL, TotalWeight REAL,
            PositionIndex INTEGER
        );
        """
    )
    con.execute("INSERT INTO SourceGroups VALUES (1, 'Main', 0, 0)")
    con.execute("INSERT INTO SourceGroupsAdditionalData VALUES (1, 'K2', 12.0, 8.5)")
    con.execute(
        """
        INSERT INTO FlyingFrames VALUES (
            1, 1,
            1, 2, -1,
            1.25, 2.5,
            1.25, 0.5,
            NULL, NULL,
            100.0, 150.0, 250.0,
            0
        )
        """
    )
    con.commit()
    con.close()


def _run(cmd: list[str], timeout: int) -> subprocess.CompletedProcess[str]:
    return subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)


def _load_report(path: Path, proc: subprocess.CompletedProcess[str]) -> dict:
    if not path.is_file():
        raise SystemExit(
            f"no report written at {path}\nexit={proc.returncode}\n"
            f"stdout:\n{proc.stdout}\nstderr:\n{proc.stderr}"
        )
    return json.loads(path.read_text(encoding="utf-8"))


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--exe", required=True, help="Frozen binary, or python when --script is set")
    ap.add_argument("--script", help="Source entry point inserted before the flags")
    ap.add_argument("--timeout", type=int, default=90)
    args = ap.parse_args(argv)

    # abspath, not resolve(): a venv python is a symlink to the system interpreter,
    # and following it drops the venv (and its installed pypdf).
    exe = os.path.abspath(args.exe)
    base = [exe] if not args.script else [exe, os.path.abspath(args.script)]

    with tempfile.TemporaryDirectory(prefix="ppe_smoke_") as tmp:
        folder = Path(tmp)
        version_path = folder / "version.json"
        proc = _run(base + ["--version-json", str(version_path)], args.timeout)
        if proc.returncode != 0:
            raise SystemExit(f"--version-json exit {proc.returncode}\n{proc.stdout}\n{proc.stderr}")
        info = json.loads(version_path.read_text(encoding="utf-8"))
        if info.get("app") != version.APP_NAME or info.get("version") != version.VERSION:
            raise SystemExit(f"version mismatch: {info!r}")
        print(f"PASS --version-json {info['app']} {info['version']}")

        dbpr = folder / "synthetic.dbpr"
        write_synthetic_dbpr(dbpr)
        report = folder / "dbpr.json"
        proc = _run(base + ["--cli", str(dbpr), "--report", str(report)], args.timeout)
        data = _load_report(report, proc)
        if proc.returncode != 0 or not data.get("ok") or data.get("points") != 2 or data.get("sources") != 1:
            raise SystemExit(f"synthetic dbpr failed: exit={proc.returncode} {data}")
        csv_path = Path(data["out_path"])
        csv_text = csv_path.read_text(encoding="utf-8")
        if "front" not in csv_text or "rear" not in csv_text:
            raise SystemExit(f"csv missing front/rear rows:\n{csv_text}")
        print(f"PASS --cli synthetic.dbpr points={data['points']}")

        pdf = folder / "synthetic.pdf"
        pdf.write_bytes(pdf_with_text(REPORT))
        report = folder / "pdf.json"
        proc = _run(base + ["--cli", str(pdf), "--report", str(report)], args.timeout)
        data = _load_report(report, proc)
        if proc.returncode != 0 or not data.get("ok") or data.get("points") != 2:
            raise SystemExit(f"synthetic pdf failed: exit={proc.returncode} {data}")
        print(f"PASS --cli synthetic.pdf points={data['points']}")

        bad = folder / "notes.txt"
        bad.write_text("x", encoding="utf-8")
        report = folder / "bad.json"
        proc = _run(base + ["--cli", str(bad), "--report", str(report)], args.timeout)
        data = _load_report(report, proc)
        if proc.returncode == 0 or data.get("ok") or data.get("log_path"):
            raise SystemExit(f"bad input should fail cleanly: exit={proc.returncode} {data}")
        if not str(data.get("message", "")).startswith("Failed: "):
            raise SystemExit(f"unexpected failure message: {data}")
        print(f"PASS --cli notes.txt {data['message']}")

    print("ALL PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
