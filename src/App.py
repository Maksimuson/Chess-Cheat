"""
Chess board reader - setup window.
Put it next to board_reader.py (the "src" folder).

Requirements:  pip install pillow opencv-python numpy
Run:           python app.py

Workflow: 1) screenshot  2) calibrate  3) build templates  ->  Launch overlay (C++ button) and play.
"""
import os
import sys
import json
import ctypes
import threading
import subprocess
import tkinter as tk
from tkinter import ttk, messagebox, filedialog

from PIL import Image, ImageGrab, ImageTk

# real screen resolution on scaled Windows displays (same as SetProcessDPIAware in the C++ code)
try:
    ctypes.windll.user32.SetProcessDPIAware()
except Exception:
    pass

HERE = os.path.dirname(os.path.abspath(__file__))
SCRIPT = os.path.join(HERE, "board_reader.py")
CONFIG_FILE = os.path.join(HERE, "board_config.json")
TEMPLATE_FILE = os.path.join(HERE, "templates.npz")
SHOT_DIR = os.path.normpath(os.path.join(HERE, "..", "screenshots"))
SHOT = os.path.join(SHOT_DIR, "shot.bmp")
NO_WINDOW = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0

# ---- chess theme ----
BG = "#312e2b"        # window background
PANEL = "#262421"     # darker panels / log
FG = "#e8e6e3"
MUTED = "#9a9894"
LIGHT_SQ = "#eeeed2"
DARK_SQ = "#769656"
GREEN_HOVER = "#8bb06a"
GREY_BTN = "#4b4845"
GREY_BTN_HOVER = "#5d5a56"
SQ = 60               # header square size


def load_cfg():
    if os.path.exists(CONFIG_FILE):
        with open(CONFIG_FILE, encoding="utf-8") as f:
            return json.load(f)
    return {}


def save_cfg(cfg):
    with open(CONFIG_FILE, "w", encoding="utf-8") as f:
        json.dump(cfg, f, indent=2)


class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Chess board reader")
        self.configure(bg=BG)
        self.resizable(False, False)
        self.attributes("-topmost", True)
        self.busy = False
        self.overlay = None

        cfg = load_cfg()
        self.turn = tk.StringVar(value=cfg.get("turn", "me"))
        self.white_bottom = tk.BooleanVar(value=cfg.get("start_white_at_bottom", True))
        self.turn.trace_add("write", lambda *_: self.persist_turn())
        self.persist_turn()

        self.setup_style()
        self.build_header()
        self.build_steps()
        self.build_play()
        self.build_log()
        self.refresh()
        self.protocol("WM_DELETE_WINDOW", self.on_close)
        self.log("Ready. Start with step 1." if "box" not in cfg
                 else "Calibration found. You can launch the overlay.")

    # ---------------- styling / layout ----------------
    def setup_style(self):
        st = ttk.Style(self)
        st.theme_use("clam")
        st.configure(".", background=BG, foreground=FG, font=("Segoe UI", 10))
        st.configure("TFrame", background=BG)
        st.configure("TLabel", background=BG, foreground=FG)
        st.configure("Muted.TLabel", foreground=MUTED)
        st.configure("TLabelframe", background=BG, bordercolor=GREY_BTN)
        st.configure("TLabelframe.Label", background=BG, foreground=LIGHT_SQ,
                     font=("Segoe UI", 10, "bold"))
        st.configure("Step.TButton", background=DARK_SQ, foreground="white", borderwidth=0,
                     padding=7, font=("Segoe UI", 10, "bold"))
        st.map("Step.TButton", background=[("disabled", GREY_BTN), ("active", GREEN_HOVER)],
               foreground=[("disabled", MUTED)])
        st.configure("Alt.TButton", background=GREY_BTN, foreground=FG, borderwidth=0,
                     padding=7, font=("Segoe UI", 10))
        st.map("Alt.TButton", background=[("disabled", PANEL), ("active", GREY_BTN_HOVER)],
               foreground=[("disabled", MUTED)])
        for name in ("TRadiobutton", "TCheckbutton"):
            st.configure(name, background=BG, foreground=FG, indicatorcolor=PANEL)
            st.map(name, background=[("active", BG)], indicatorcolor=[("selected", DARK_SQ)])

    def build_header(self):
        c = tk.Canvas(self, width=SQ * 8, height=SQ, bg=BG, highlightthickness=0)
        c.pack()
        pieces = "\u265c\u265e\u265d\u265b\u265a\u265d\u265e\u265c"   # rook knight bishop queen king ...
        for i, p in enumerate(pieces):
            light = i % 2 == 0
            c.create_rectangle(i * SQ, 0, (i + 1) * SQ, SQ, fill=LIGHT_SQ if light else DARK_SQ,
                               outline="")
            c.create_text(i * SQ + SQ // 2, SQ // 2 + 2, text=p, fill="#1b1b1b",
                          font=("Segoe UI Symbol", 30))
        tk.Label(self, text="CHESS BOARD READER", bg=BG, fg=LIGHT_SQ,
                 font=("Segoe UI", 14, "bold")).pack(pady=(8, 0))
        tk.Label(self, text="screenshot  \u2192  calibrate  \u2192  templates  \u2192  play",
                 bg=BG, fg=MUTED, font=("Segoe UI", 9)).pack(pady=(0, 6))

    def step_row(self, parent, text, command, style="Step.TButton"):
        row = tk.Frame(parent, bg=BG)
        row.pack(fill="x", padx=8, pady=3)
        mark = tk.Label(row, text="\u25cb", bg=BG, fg=MUTED, font=("Segoe UI Symbol", 14), width=2)
        mark.pack(side="left")
        btn = ttk.Button(row, text=text, command=command, style=style)
        btn.pack(side="left", fill="x", expand=True)
        return btn, mark

    def build_steps(self):
        box = ttk.LabelFrame(self, text="  One-time setup  ")
        box.pack(fill="x", padx=12, pady=(4, 6))
        self.btn_shot, self.mk_shot = self.step_row(box, "1.  Take screenshot", self.step_screenshot)
        self.btn_cal, self.mk_cal = self.step_row(box, "2.  Calibrate board", self.step_calibrate)
        self.btn_tpl, self.mk_tpl = self.step_row(box, "3.  Build piece templates", self.step_templates)
        ttk.Label(box, text="Open a game at the STARTING position first, then press 1.\n"
                            "This window hides itself while the screenshot is taken.",
                  style="Muted.TLabel", justify="left").pack(anchor="w", padx=10, pady=(2, 8))

    def build_play(self):
        box = ttk.LabelFrame(self, text="  Play  ")
        box.pack(fill="x", padx=12, pady=6)
        row = tk.Frame(box, bg=BG)
        row.pack(fill="x", padx=10, pady=(6, 2))
        ttk.Label(row, text="Move for:").pack(side="left")
        ttk.Radiobutton(row, text="my side (auto)", variable=self.turn, value="me").pack(side="left", padx=8)
        ttk.Radiobutton(row, text="White", variable=self.turn, value="w").pack(side="left")
        ttk.Radiobutton(row, text="Black", variable=self.turn, value="b").pack(side="left", padx=8)
        self.btn_overlay = ttk.Button(box, text="\u265e  Launch overlay button", style="Step.TButton",
                                      command=self.launch_overlay)
        self.btn_overlay.pack(fill="x", padx=10, pady=(6, 3))
        self.btn_move = ttk.Button(box, text="Test: screenshot + best move", style="Alt.TButton",
                                   command=self.step_move)
        self.btn_move.pack(fill="x", padx=10, pady=(0, 8))

    def build_log(self):
        self.log_box = tk.Text(self, height=8, width=58, bg=PANEL, fg="#d9d9d9", relief="flat",
                               font=("Consolas", 10), state="disabled", padx=8, pady=6,
                               insertbackground=FG)
        self.log_box.pack(fill="both", expand=True, padx=12, pady=(6, 12))

    # ---------------- helpers ----------------
    def log(self, text):
        self.log_box.configure(state="normal")
        self.log_box.insert("end", text + "\n")
        self.log_box.see("end")
        self.log_box.configure(state="disabled")

    def refresh(self):
        def mark(lbl, ok):
            lbl.configure(text="\u2713" if ok else "\u25cb", fg=DARK_SQ if ok else MUTED)
        mark(self.mk_shot, os.path.exists(SHOT))
        mark(self.mk_cal, "box" in load_cfg())
        mark(self.mk_tpl, os.path.exists(TEMPLATE_FILE))

    def set_busy(self, value):
        self.busy = value
        state = "disabled" if value else "normal"
        for b in (self.btn_shot, self.btn_cal, self.btn_tpl, self.btn_move, self.btn_overlay):
            b.configure(state=state)
        if not value:
            self.refresh()

    def persist_turn(self):
        cfg = load_cfg()
        cfg["turn"] = self.turn.get()
        save_cfg(cfg)

    def ready(self):
        return os.path.exists(TEMPLATE_FILE) and "box" in load_cfg()

    def run_script(self, args, done):
        """Runs board_reader.py in a separate process (it re-reads the config every time)."""
        self.set_busy(True)

        def work():
            r = subprocess.run(
                [sys.executable, SCRIPT] + args, cwd=HERE, capture_output=True,
                text=True, encoding="utf-8", errors="replace", creationflags=NO_WINDOW)
            out = (r.stdout + r.stderr).strip()
            self.after(0, lambda: (self.set_busy(False), done(r.returncode, out)))

        threading.Thread(target=work, daemon=True).start()

    # ---------------- step 1: screenshot ----------------
    def grab_screen(self, then):
        """Hides the window, saves the screen to shot.bmp, then calls then()."""
        self.set_busy(True)
        self.withdraw()

        def do():
            err = None
            try:
                os.makedirs(SHOT_DIR, exist_ok=True)
                ImageGrab.grab().save(SHOT, "BMP")
            except Exception as e:
                err = str(e)
            self.deiconify()
            self.set_busy(False)
            if err:
                self.log(f"ERROR taking screenshot: {err}")
            else:
                then()

        self.after(400, do)   # give the window time to disappear

    def step_screenshot(self):
        self.grab_screen(lambda: self.log(f"Screenshot saved: {SHOT}\nNow step 2."))

    # ---------------- step 2: calibration ----------------
    def step_calibrate(self):
        if not os.path.exists(SHOT):
            messagebox.showinfo("No screenshot", "Take a screenshot first (step 1).")
            return

        img = Image.open(SHOT).convert("RGB")
        W, H = img.size
        sw, sh = self.winfo_screenwidth(), self.winfo_screenheight()
        scale = min(1.0, (sw - 80) / W, (sh - 180) / H)
        view = img.resize((int(W * scale), int(H * scale)), Image.LANCZOS) if scale < 1 else img

        win = tk.Toplevel(self, bg=BG)
        win.title("Select the board along the outer edges of the squares")
        win.transient(self)
        photo = ImageTk.PhotoImage(view)
        canvas = tk.Canvas(win, width=view.width, height=view.height, cursor="cross",
                           highlightthickness=0, bg=PANEL)
        canvas.pack()
        canvas.create_image(0, 0, anchor="nw", image=photo)
        canvas.photo = photo

        sel = {"start": None, "rect": None}   # rect = (left, top, side) in canvas coordinates

        def draw():
            canvas.delete("sel")
            if not sel["rect"]:
                return
            l, t, s = sel["rect"]
            canvas.create_rectangle(l, t, l + s, t + s, outline="#ff4040", width=2, tags="sel")
            for i in range(1, 8):
                p = i * s / 8
                canvas.create_line(l + p, t, l + p, t + s, fill="#ff4040", tags="sel")
                canvas.create_line(l, t + p, l + s, t + p, fill="#ff4040", tags="sel")

        def on_press(e):
            sel["start"] = (e.x, e.y)

        def on_drag(e):
            x0, y0 = sel["start"]
            dx, dy = e.x - x0, e.y - y0
            s = min(abs(dx), abs(dy))                  # the board is square
            sel["rect"] = (x0 if dx >= 0 else x0 - s, y0 if dy >= 0 else y0 - s, s)
            draw()

        def nudge(dl, dt, ds):
            if sel["rect"]:
                l, t, s = sel["rect"]
                sel["rect"] = (l + dl, t + dt, max(8, s + ds))
                draw()

        canvas.bind("<ButtonPress-1>", on_press)
        canvas.bind("<B1-Motion>", on_drag)
        for key, args in (("<Left>", (-1, 0, 0)), ("<Right>", (1, 0, 0)), ("<Up>", (0, -1, 0)),
                          ("<Down>", (0, 1, 0)), ("<plus>", (0, 0, 1)), ("<equal>", (0, 0, 1)),
                          ("<minus>", (0, 0, -1))):
            win.bind(key, lambda e, a=args: nudge(*a))

        def accept():
            if not sel["rect"] or sel["rect"][2] < 16:
                messagebox.showinfo("No selection", "Drag a square over the board first.", parent=win)
                return
            l, t, s = sel["rect"]
            left, top = int(round(l / scale)), int(round(t / scale))
            side = int(round(s / scale))
            cfg = load_cfg()
            cfg["box"] = [max(0, left), max(0, top), min(W, left + side), min(H, top + side)]
            cfg["start_white_at_bottom"] = self.white_bottom.get()
            cfg.setdefault("my_color", "auto")
            save_cfg(cfg)
            self.log(f"Calibration saved: box={cfg['box']}\nNow step 3.")
            self.refresh()
            win.destroy()

        bar = tk.Frame(win, bg=BG)
        bar.pack(fill="x", padx=10, pady=8)
        ttk.Checkbutton(bar, text="White is at the bottom on this screenshot",
                        variable=self.white_bottom).pack(side="left")
        ttk.Button(bar, text="Accept", style="Step.TButton", command=accept).pack(side="right")
        tk.Label(win, text="Drag with the mouse.  Arrow keys: move 1 px.   + / - : resize.",
                 bg=BG, fg=MUTED).pack(pady=(0, 8))

    # ---------------- step 3: templates ----------------
    def step_templates(self):
        if not os.path.exists(SHOT) or "box" not in load_cfg():
            messagebox.showinfo("Not ready", "You need a screenshot (1) and a calibration (2).")
            return
        self.log("Building templates...")
        self.run_script(["templates", SHOT], lambda code, out: self.log(out or "Done."))

    # ---------------- test move ----------------
    def step_move(self):
        if not self.ready():
            messagebox.showinfo("Not ready", "Complete steps 1-3 first.")
            return

        def after_shot():
            self.log("Calculating move...")
            # no turn argument: board_reader uses the "turn" value from board_config.json
            self.run_script(["move", SHOT], lambda code, out: self.log(out))

        self.grab_screen(after_shot)

    # ---------------- C++ overlay ----------------
    def launch_overlay(self):
        if not self.ready():
            messagebox.showinfo("Not ready", "Complete steps 1-3 first.")
            return
        cfg = load_cfg()
        exe = cfg.get("overlay_exe")
        if not exe or not os.path.exists(exe):
            exe = filedialog.askopenfilename(
                title="Select the overlay .exe built from main.cpp",
                filetypes=[("Executable", "*.exe")])
            if not exe:
                return
            cfg["overlay_exe"] = exe
            save_cfg(cfg)
        try:
            self.overlay = subprocess.Popen([exe], cwd=os.path.dirname(exe))
        except OSError as e:
            self.log(f"ERROR starting overlay: {e}")
            return
        self.log("Overlay started. Right-click its button to close it.")
        self.iconify()          # keep this window out of the overlay's screenshots
        self.after(500, self.watch_overlay)

    def on_close(self):
        if self.overlay and self.overlay.poll() is None:
            self.overlay.terminate()
        self.destroy()

    def watch_overlay(self):
        if self.overlay and self.overlay.poll() is None:
            self.after(500, self.watch_overlay)
            return
        self.overlay = None
        self.deiconify()
        self.log("Overlay closed.")


if __name__ == "__main__":
    App().mainloop()