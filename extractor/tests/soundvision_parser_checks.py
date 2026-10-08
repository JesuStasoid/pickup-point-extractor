"""Edge-case tests for extract_soundvision_hoists (synthetic report text)."""
import sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent / "src"))
import extract_soundvision_hoists as sv

HDR = "Soundvision\nVersion: 2026.3.1\nFile name: t.xmlp\nDistance unit:\n{du}\nScale factor:\n1.000000\nWeight unit:\n{wu}\n"

def rep(du="m", wu="kg", body=""):
    return HDR.format(du=du, wu=wu) + body

TWO = """1. Group: G
1. Source: A
1. 1. Physical configuration
Configuration: vertical, flown array
Bumper: K2-BUMP
# motors: 2
Front pickup position (X; Y; Z, {du}): 1 (1.5; -2; 10)
Rear pickup position (X; Y; Z, {du}): 2 (1; -2; 10.1)
Position (X; Y; Z, {du}): 1; -2; 10
Azimuth: 30 °
Page 3 of 9
Spatial dimensions (X; Y; Z, m): 1; 1; 5
Total weight (Enclosures + Frames): 1000 {wu}
Front motor
load: 400 {wu}
Rear motor load: 600 {wu}
Enclosure #1 - K2
Enclosure #2 - KS28
"""
# 1-motor wording as in the real report (KARA II on M-BUMP, Soundvision 2026.3.1)
ONE = """2. Source: B
1. 1. Physical configuration
Configuration: vertical, flown array
Bumper: M-BUMP+MBAR hole B
# motors: 1
Front pickup position (X; Y; Z, {du}): 7 (3; 4; 12)
Position (X; Y; Z, {du}): 3; 4; 12
Azimuth: 0 °
Page 1 of 2
Total weight (Enclosures + Frames): 300 {wu}
Total enclosure weight: 280 {wu}
Front motor load: 300 {wu}
#
Type
Angles (°)
Panflex
#1
KARA II
5
55/55
#2
KARA II
0
55/55
1. 2. Acoustic configuration
None
3. Source: C stack
Configuration: vertical, stacked array
# motors: 0
4. Source: D flown no load
Configuration: vertical, flown array
# motors: 1
Front pickup position (X; Y; Z, {du}): 0 (0; 0; 9)
Total weight (Enclosures + Frames): 250 {wu}
"""

def ok(c, msg):
    print(("PASS " if c else "FAIL ") + msg)
    if not c: ok.fail = True
ok.fail = False

# metric, page footer + wrapped load line inside block
r = sv.parse_report_text(rep(body=(TWO + ONE).format(du="m", wu="kg")))
rows = r.rows
ok([x["pick_kind"] for x in rows if x["source"] == "A"] == ["front", "rear"], "2-motor -> front+rear")
ok(rows[0]["weight_kg"] == 400 and rows[1]["weight_kg"] == 600, "loads across page footer / line wrap")
ok(rows[0]["system"] == "K2+KS28", "system from enclosure types")
b = [x for x in rows if x["source"] == "B"]
ok([x["pick_kind"] for x in b] == ["front", "single"] and all(x["single_available"] == "1" for x in b), "1-motor -> front + single, single_available=1")
ok(b[0]["weight_kg"] == 300 and b[0]["hole"] == 7, "1-motor 'Front motor load' + hole")
ok(b[0]["system"] == "KARA II", "system from enclosure table (no 'Enclosure #' lines)")
ok(not any("source 'B'" in w for w in r.warnings), "1-motor real wording -> no warnings")
ok(any(n == "C stack" for n, _ in r.skipped), "stacked source skipped")
d = [x for x in rows if x["source"] == "D flown no load"]
ok(d and d[0]["weight_kg"] == 250 and any("using total weight" in w for w in r.warnings), "1-motor w/o load -> total weight + warning")
ok(len({x["flying_frame_id"] for x in rows if x["pick_kind"] != "single"}) == 3, "unique frame ids")

# placers: default (front/rear) and ticked (single) each place the 1-motor hoist once
def placed(rows, singles):
    return [x for x in rows if (x["pick_kind"] == "single") == (x["source"] in singles)
            and x["pick_kind"] in (("single",) if x["source"] in singles else ("front", "rear"))]
r = sv.parse_report_text(rep(body=(TWO + ONE).format(du="m", wu="kg")))
ok(sum(x["source"] == "B" for x in placed(r.rows, set())) == 1, "1-motor placed once by default")
ok(sum(x["source"] == "B" for x in placed(r.rows, {"B"})) == 1, "1-motor placed once when ticked single")

# imperial reports are refused (no conversion)
for du, wu, what in (("ft", "kg", "ft header"), ("m", "lb", "lb header")):
    try:
        sv.parse_report_text(rep(du, wu, (TWO + ONE).format(du=du, wu=wu))); ok(False, f"{what} refused")
    except sv.SoundvisionParseError as e:
        ok("Only" in str(e), f"{what} refused: {e}")

# contradictory units must stop
try:
    sv.parse_report_text(rep("m", "kg", TWO.format(du="ft", wu="kg"))); ok(False, "unit mismatch raises")
except sv.SoundvisionParseError:
    ok(True, "unit mismatch raises")
try:
    sv.parse_report_text(rep("m", "kg", TWO.format(du="m", wu="lb"))); ok(False, "lb on a load line raises")
except sv.SoundvisionParseError:
    ok(True, "lb on a load line raises")
try:
    sv.parse_report_text(rep("furlong", "kg", "")); ok(False, "unknown header unit raises")
except sv.SoundvisionParseError:
    ok(True, "unknown header unit raises")

# comma decimals + duplicate names + load mismatch warning
body = TWO.format(du="m", wu="kg").replace("1.5; -2; 10", "1,5; -2; 10") + TWO.format(du="m", wu="kg").replace("1. Source: A", "2. Source: A").replace("Rear motor load: 600", "Rear motor load: 900")
r = sv.parse_report_text(rep(body=body))
ok(r.rows[0]["x_m"] == 1.5, "comma decimal")
ok(any(x["source"] == "A (2)" for x in r.rows), "duplicate source renamed")
ok(any("!= total weight" in w for w in r.warnings), "front+rear vs total check")
print("ALL PASS" if not ok.fail else "SOME FAILED")
sys.exit(1 if ok.fail else 0)
