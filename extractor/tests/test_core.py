"""Quick checks for the shared core (no samples needed).

  python -m pytest tests        (or)   python tests/test_core.py
Set PPE_SAMPLES=<folder with .dbpr/.pdf + reference CSVs> to also run the
byte-for-byte regression against reference *_hoist_picks.csv files.
"""
import os, shutil, sqlite3, sys, tempfile
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))
import core  # noqa: E402


def _tmp():
    return Path(tempfile.mkdtemp(prefix="ppe_"))


def test_bad_inputs():
    d = _tmp()
    (d / "empty.pdf").write_bytes(b"")
    (d / "fake.pdf").write_bytes(b"hello")
    (d / "junk.dbpr").write_bytes(os.urandom(2000))
    (d / "notes.txt").write_text("x")
    con = sqlite3.connect(d / "other.dbpr"); con.execute("create table t(a)"); con.commit(); con.close()
    for name in ("empty.pdf", "fake.pdf", "junk.dbpr", "notes.txt", "other.dbpr", "missing.pdf"):
        r = core.run_extraction(d / name)
        assert not r.ok and r.message.startswith("Failed: ") and "Traceback" not in r.message, (name, r.message)
        assert not r.log_path, (name, r.log_path)
    shutil.rmtree(d)


def test_count_points():
    rows = [{"source": "A", "pick_kind": "front"}, {"source": "A", "pick_kind": "rear"},
            {"source": "A", "pick_kind": "single"}, {"source": "B", "pick_kind": "front"},
            {"source": "B", "pick_kind": "single"}]
    assert core.count_points(rows) == (3, 2)


def test_samples():
    folder = os.environ.get("PPE_SAMPLES")
    if not folder:
        return
    d = _tmp()
    for src in Path(folder).iterdir():
        if src.suffix.lower() not in (".dbpr", ".pdf"):
            continue
        ref = src.with_name(src.stem + core.OUT_SUFFIX)
        if not ref.exists():
            continue
        shutil.copy2(src, d / src.name)
        r = core.run_extraction(d / src.name)
        assert r.ok, r.message
        assert Path(r.out_path).read_bytes() == ref.read_bytes(), src.name
    shutil.rmtree(d)


if __name__ == "__main__":
    for t in (test_bad_inputs, test_count_points, test_samples):
        t(); print("PASS", t.__name__)
