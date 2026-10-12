"""Pick-up point extractor - tiny Tk front end.

Event-driven only: no timers, no polling, no threads. Extraction runs
synchronously (well under a second for real projects/reports).

Hidden flags (used for automated tests of the frozen build):
  --cli INPUT [--report out.json]   extract without UI, JSON result
  --version-json out.json           write version + exit (startup timing)
  --demo INPUT                      open the UI and extract INPUT once
"""

from __future__ import annotations

import os
import sys

from version import APP_NAME, VERSION, WINDOW_TITLE

# --noconsole builds have no stdout/stderr; keep stray prints/logging harmless
for _name in ("stdout", "stderr"):
    if getattr(sys, _name) is None:
        setattr(sys, _name, open(os.devnull, "w", encoding="utf-8"))

FILETYPES = [
    ("Supported files", "*.dbpr *.pdf"),
    ("ArrayCalc", "*.dbpr"),
    ("Soundvision report", "*.pdf"),
    ("All files", "*.*"),
]
GREEN, RED, GREY = "#1a7f37", "#c62828", "#555555"


def _write_json(path, data):
    import json
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=1)


def cli(argv) -> int:
    import time
    from dataclasses import asdict
    t0 = time.perf_counter()
    inp = argv[argv.index("--cli") + 1]
    report = argv[argv.index("--report") + 1] if "--report" in argv else None
    import core
    res = core.run_extraction(inp)
    data = asdict(res)
    data["elapsed_s"] = round(time.perf_counter() - t0, 4)
    try:
        import _diag
        data["peak_rss_bytes"] = _diag.peak_rss_bytes()
    except Exception:
        pass
    if report:
        _write_json(report, data)
    else:
        print(res.message)
    return 0 if res.ok else 1


class App:
    def __init__(self, root, initial=""):
        import tkinter as tk
        from tkinter import ttk
        self.tk = tk
        self.root = root
        self.last_dir = os.path.dirname(initial) if initial else ""
        root.title(WINDOW_TITLE)
        root.resizable(False, False)

        frm = ttk.Frame(root, padding=10)
        frm.grid(sticky="nsew")
        ttk.Label(frm, text="ArrayCalc project (.dbpr) or Soundvision report (.pdf):").grid(
            row=0, column=0, columnspan=2, sticky="w")
        self.path = tk.StringVar(value=initial)
        # Classic Entry with a steady (non-blinking) caret: a blinking caret
        # (ttk.Entry) wakes the process ~3x per second while focused.
        self.ent = ent = tk.Entry(frm, textvariable=self.path, width=62, insertofftime=0,
                                  relief="solid", borderwidth=1)
        ent.grid(row=1, column=0, sticky="ew", pady=(4, 8), ipady=3)
        ttk.Button(frm, text="Browse…", command=self.browse).grid(row=1, column=1, padx=(6, 0), pady=(4, 8))
        self.btn = ttk.Button(frm, text="Extract", command=self.extract)
        self.btn.grid(row=2, column=0, columnspan=2, sticky="ew")
        self.status = tk.Label(frm, text="Choose a file, then press Extract. "
                               "The CSV is saved next to it.",
                               fg=GREY, anchor="w", justify="left", wraplength=470)
        self.status.grid(row=3, column=0, columnspan=2, sticky="ew", pady=(8, 0))
        root.bind("<Return>", lambda e: self.extract())
        ent.focus_set()
        self.show_end()

    def show_end(self):
        """Keep the file name (end of the path) visible in the entry."""
        self.ent.icursor("end")
        self.ent.xview_moveto(1.0)

    def browse(self):
        from tkinter import filedialog
        p = filedialog.askopenfilename(parent=self.root, title="Choose a file",
                                       initialdir=self.last_dir or None, filetypes=FILETYPES)
        if p:
            self.path.set(os.path.normpath(p))
            self.last_dir = os.path.dirname(p)
            self.show_end()
            self.set_status("Ready - press Extract.", GREY)

    def set_status(self, text, color):
        self.status.config(text=text, fg=color)

    def extract(self):
        import core
        self.btn.state(["disabled"])
        self.root.config(cursor="watch")
        self.set_status("Extracting…", GREY)
        self.root.update_idletasks()
        try:
            res = core.run_extraction(self.path.get())
        finally:
            self.root.config(cursor="")
            self.btn.state(["!disabled"])
            import gc
            gc.collect()              # drop the parsed PDF/DB objects right away
        self.set_status(res.message, GREEN if res.ok else RED)
        return res


def _mac_paint(root) -> None:
    """Ask Aqua Tk to paint once. One idle callback, then no timer is left."""
    if sys.platform != "darwin":
        return
    root.lift()
    try:
        root.attributes("-topmost", True)
    except Exception:
        return

    def drop_topmost() -> None:
        try:
            root.attributes("-topmost", False)
        except Exception:
            pass

    root.after_idle(drop_topmost)


def gui(argv) -> int:
    if sys.platform == "darwin":
        # Must be set before Tk loads. Harmless on python.org Tk 8.6; silences
        # the blank-window warning from Apple's deprecated system Tk.
        os.environ.setdefault("TK_SILENCE_DEPRECATION", "1")
    import tkinter as tk
    demo = argv[argv.index("--demo") + 1] if "--demo" in argv else None
    initial = demo or next((a for a in argv[1:] if not a.startswith("--")), "")
    root = tk.Tk()
    app = App(root, os.path.normpath(initial) if initial else "")
    _mac_paint(root)
    if demo:
        root.after_idle(app.extract)  # one-shot, demo/screenshot only
    if sys.platform == "darwin":
        root.update_idletasks()
    root.mainloop()
    return 0


def main(argv=None) -> int:
    argv = list(sys.argv if argv is None else argv)
    if "--version-json" in argv:
        _write_json(argv[argv.index("--version-json") + 1], {"app": APP_NAME, "version": VERSION})
        return 0
    if "--cli" in argv:
        return cli(argv)
    return gui(argv)


if __name__ == "__main__":
    sys.exit(main())
