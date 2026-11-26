"""Hand Mouse - Version 7.0.0

Control the mouse pointer with hand gestures using a webcam and MediaPipe.

Requirements:
    pip install -r requirements.txt

Run from source:
    python hand_mouse.py

Exit:
    Press Q or Esc in the camera window, or close the window.

Author: Matin Sobhani
GitHub: https://github.com/matinsobhanidev
Instagram: https://www.instagram.com/matinsobahnidev/
Telegram: https://t.me/sobhani_matin

Gesture controls:
    Open palm movement                 -> Move the cursor
    Thumb + index pinch and release    -> Left click
    Two quick thumb + index pinches    -> Double-click
    Thumb + middle-finger pinch        -> Right click
    V gesture (index and middle open)  -> Scroll
    All fingertips pinched to thumb, or a fist -> Drag

Camera frames are processed locally. The hand-landmarker model is downloaded
from the official MediaPipe model hosting endpoint on first launch.
"""

import ctypes
import os
import sys
import tempfile


os.environ.setdefault("OPENCV_LOG_LEVEL", "SILENT")
os.environ.setdefault("GLOG_minloglevel", "3")
os.environ.setdefault("TF_CPP_MIN_LOG_LEVEL", "3")
if sys.stdout is None:
    sys.stdout = open(os.devnull, "w")
if sys.stderr is None:
    sys.stderr = open(os.devnull, "w")

from collections import deque
import json
import math
import time
import urllib.request

import cv2
import mediapipe as mp
import numpy as np
import pyautogui
from mediapipe.tasks import python as mp_python
from mediapipe.tasks.python import vision
from screeninfo import get_monitors


CAM_INDEX = 0
AREA_SIZE = 0.8
SENSITIVITY = 1.25
SMOOTH = 0.45



AREA_SHIFT_X = 0
AREA_SHIFT_UP = 0


DISPLAY_WIDTH = 640
TOOLBAR_H = 56


REAL_MOUSE_INPUT = True





TREMOR_DEADZONE = 0.0075

STEADY_MIN_CUTOFF = 1.0
STEADY_BETA = 8.0


CAM_WIDTH = 320
CAM_HEIGHT = 240
CAM_FPS = 20
CAM_SEARCH_COUNT = 4
CAM_OPEN_TIMEOUT = 3.0
CAM_LOST_FRAMES = 40
MON_CHECK_EVERY = 2.0


IDLE_AFTER = 2.0
IDLE_DETECT_EVERY = 4


PINCH_ON = 0.35
PINCH_OFF = 0.48
CONFIRM_FRAMES = 2
CLICK_MAX_TIME = 0.8
DOUBLE_CLICK_WINDOW = 0.25

DOUBLE_CLICK_RELEASE_MOVE = 70
PINCH_BACKTRACK = 5
DIST_SMOOTH = 0.6
LOST_GRACE_FRAMES = 10
DRAG_SCALE = 1.0

RELEASE_HOLD = 0.25
RELEASE_BLEND = 0.94


RIGHT_ON = 0.35
RIGHT_OFF = 0.50
RIGHT_CONFIRM_FRAMES = 2
MID_WINS_MARGIN = 0.03
MIN_CLICK_TIME = 0.05
MAX_CLICK_TIME = 1.2






GRAB_ON = 0.60
CURL_ON = 1.35
GRAB_RELEASE = 1.3
GRAB_CONFIRM_FRAMES = 3


SCROLL_DEADZONE = 0.04
SCROLL_RANGE = 0.18
SCROLL_MAX_SPEED = 45
SCROLL_ENTER_FRAMES = 3
SCROLL_EXIT_FRAMES = 3
SCROLL_INVERT = False

LABEL_CONFIRM_FRAMES = 6
USE_DSHOW = True
SWAP_HANDS = True
# -----------------------------------------------------------

APP_TITLE = 'Hand Mouse'
APP_AUTHOR = 'Matin Sobhani'
MODEL_URL = ("https://storage.googleapis.com/mediapipe-models/hand_landmarker/"
             "hand_landmarker/float16/1/hand_landmarker.task")
MODEL_NAME = "hand_landmarker.task"
CONFIG_NAME = "hand_mouse_config.json"


class AppError(Exception):
    'An error that can be displayed directly in a message dialog.'


def app_dir():
    'The directory containing the Python script or executable.'
    if getattr(sys, "frozen", False):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.abspath(__file__))


def find_model():
    cands = [os.path.join(app_dir(), MODEL_NAME)]
    if hasattr(sys, "_MEIPASS"):
        cands.insert(0, os.path.join(sys._MEIPASS, MODEL_NAME))
    for c in cands:
        if os.path.exists(c) and os.path.getsize(c) > 1_000_000:
            return c
    return cands[-1]


MODEL_PATH = find_model()
CONFIG_PATH = os.path.join(app_dir(), CONFIG_NAME)

WIN = "Hand Mouse (q = exit)"

HAND_CONNECTIONS = [
    (0, 1), (1, 2), (2, 3), (3, 4),
    (0, 5), (5, 6), (6, 7), (7, 8),
    (5, 9), (9, 10), (10, 11), (11, 12),
    (9, 13), (13, 14), (14, 15), (15, 16),
    (13, 17), (17, 18), (18, 19), (19, 20), (0, 17),
]

pyautogui.FAILSAFE = True
pyautogui.PAUSE = 0

try:
    ctypes.windll.shcore.SetProcessDpiAwareness(2)
except Exception:
    pass

if os.name == "nt":
    from ctypes import wintypes

    class _MOUSEINPUT(ctypes.Structure):
        _fields_ = [("dx", wintypes.LONG), ("dy", wintypes.LONG), ("mouseData", wintypes.DWORD),
                    ("dwFlags", wintypes.DWORD), ("time", wintypes.DWORD), ("dwExtraInfo", ctypes.c_size_t)]

    class _INPUT_UNION(ctypes.Union):
        _fields_ = [("mi", _MOUSEINPUT)]

    class _INPUT(ctypes.Structure):
        _anonymous_ = ("u",)
        _fields_ = [("type", wintypes.DWORD), ("u", _INPUT_UNION)]


def move_cursor(x, y):
    'Moves the cursor. When REAL_MOUSE_INPUT is enabled on Windows, SendInput is used to emulate physical mouse movement.'
    x, y = int(round(x)), int(round(y))
    if REAL_MOUSE_INPUT and os.name == "nt":
        try:
            u = ctypes.windll.user32
            vx, vy = u.GetSystemMetrics(76), u.GetSystemMetrics(77)
            vw, vh = u.GetSystemMetrics(78), u.GetSystemMetrics(79)
            if vw > 1 and vh > 1:
                inp = _INPUT(type=0)                                      # INPUT_MOUSE
                inp.mi = _MOUSEINPUT(int(round((x - vx) * 65535 / (vw - 1))),
                                     int(round((y - vy) * 65535 / (vh - 1))),
                                     0, 0x0001 | 0x8000 | 0x4000, 0, 0)   # MOVE | ABSOLUTE | VIRTUALDESK
                if u.SendInput(1, ctypes.byref(inp), ctypes.sizeof(inp)) == 1:
                    return
        except Exception:
            pass
    pyautogui.moveTo(x, y)


def click_at(x, y, button="left"):
    x, y = int(x), int(y)
    if REAL_MOUSE_INPUT and os.name == "nt":
        move_cursor(x, y)
        time.sleep(0.01)
        pyautogui.click(button=button)
    else:
        pyautogui.click(x, y, button=button)


WRIST, THUMB_TIP = 0, 4
IDX_PIP, IDX_TIP = 6, 8
MID_MCP, MID_PIP, MID_TIP = 9, 10, 12
RING_PIP, RING_TIP = 14, 16
PINKY_PIP, PINKY_TIP = 18, 20




def show_message(text, kind="error", title=APP_TITLE):
    'Displays a message dialog instead of printing to the console. kind: error / warning / info.'
    if os.name == "nt":
        try:
            icon = {"error": 0x10, "warning": 0x30, "info": 0x40}.get(kind, 0x10)

            ctypes.windll.user32.MessageBoxW(0, text, title,
                                             icon | 0x00080000 | 0x00100000 | 0x00040000)
            return
        except Exception:
            pass
    try:
        import tkinter as tk
        from tkinter import messagebox
        root = tk.Tk()
        root.withdraw()
        root.attributes("-topmost", True)
        fn = {"error": messagebox.showerror, "warning": messagebox.showwarning,
              "info": messagebox.showinfo}.get(kind, messagebox.showerror)
        fn(title, text, parent=root)
        root.destroy()
    except Exception:
        pass




from collections import namedtuple

Setting = namedtuple("Setting", "name group label help lo hi step kind")
_S = Setting
G_MOVE, G_STEADY, G_CLICK, G_GRAB, G_HANDS = ('Movement', 'Stabilization', 'Clicks', 'Grab & Scroll', 'Hands & Camera')

SCHEMA = [
    _S("AREA_SIZE", G_MOVE, "Green area size", "Larger = move your hand farther to reach the screen edges. Smaller = cover the screen with less hand movement.", 0.3, 1.0, 0.01, "float"),
    _S("AREA_SHIFT_X", G_MOVE, "Green area position: left / right", "0 = centered. Positive values move the area right; negative values move it left.", -100, 100, 1, "int"),
    _S("AREA_SHIFT_UP", G_MOVE, "Green area position: up / down", "Higher values move the area up; lower (negative) values move it down.", -100, 100, 1, "int"),
    _S("SENSITIVITY", G_MOVE, "Cursor sensitivity", "Higher values move the cursor farther with less hand movement.", 0.5, 3.0, 0.05, "float"),
    _S("SMOOTH", G_MOVE, "Movement smoothing", "Lower = smoother but slower. Higher = faster with less delay.", 0.1, 1.0, 0.05, "float"),
    _S("DRAG_SCALE", G_MOVE, "Drag cursor speed", "1 = moving your hand across the green area covers the monitor. Higher values make cross-screen movement easier.", 0.5, 3.0, 0.1, "float"),

    _S("TREMOR_DEADZONE", G_STEADY, "Deadzone radius", "Larger values ignore more hand movement. 0 disables the deadzone.", 0.0, 0.03, 0.0005, "float"),
    _S("STEADY_MIN_CUTOFF", G_STEADY, "Stability while hand is still", "Lower values provide more stability, but may slow very small movements.", 0.2, 3.0, 0.05, "float"),
    _S("STEADY_BETA", G_STEADY, "Fast-movement response", "Higher values reduce smoothing delay during fast movements.", 0.0, 20.0, 0.5, "float"),

    _S("PINCH_ON", G_CLICK, "Left-click sensitivity", "Higher values make a pinch easier to trigger.", 0.15, 0.7, 0.01, "float"),
    _S("PINCH_OFF", G_CLICK, "Left-click release threshold", "Must be greater than the activation threshold; this is enforced automatically.", 0.2, 0.9, 0.01, "float"),
    _S("CONFIRM_FRAMES", G_CLICK, "Left-click confirmation (frames)", "Higher values reduce accidental clicks but add a small delay.", 1, 6, 1, "int"),
    _S("CLICK_MAX_TIME", G_CLICK, "Maximum left-click duration (seconds)", "A longer pinch is not treated as a left click.", 0.2, 2.0, 0.05, "float"),
    _S("DOUBLE_CLICK_WINDOW", G_CLICK, "Double-click interval (seconds)", "The second pinch must happen within this interval. Keep this at or below 0.5 seconds.", 0.03, 0.6, 0.01, "float"),
    _S("RIGHT_ON", G_CLICK, "Right-click sensitivity", "Higher values make a right-click pinch easier to trigger.", 0.15, 0.8, 0.01, "float"),
    _S("RIGHT_OFF", G_CLICK, "Right-click release threshold", "Must be greater than the activation threshold; this is enforced automatically.", 0.2, 0.95, 0.01, "float"),
    _S("MAX_CLICK_TIME", G_CLICK, "Maximum right-click duration (seconds)", "A longer pinch is not treated as a right click.", 0.3, 3.0, 0.05, "float"),

    _S("GRAB_ON", G_GRAB, "Grab: fingertip-to-thumb distance", "Higher values make grabbing easier when pinching all four fingertips to the thumb.", 0.2, 1.0, 0.01, "float"),
    _S("CURL_ON", G_GRAB, "Grab with a fist: finger curl", "Higher values make fist detection easier. Lower values require a tighter fist.", 0.8, 1.8, 0.05, "float"),
    _S("GRAB_RELEASE", G_GRAB, "Grab release threshold", "Higher values make the grab gesture release later.", 1.02, 1.8, 0.01, "float"),
    _S("GRAB_CONFIRM_FRAMES", G_GRAB, "Grab confirmation (frames)", "Higher values reduce accidental grabs but add a small delay.", 1, 8, 1, "int"),
    _S("SCROLL_DEADZONE", G_GRAB, "Scroll deadzone", "Move your hand farther from the starting point to begin scrolling.", 0.01, 0.15, 0.005, "float"),
    _S("SCROLL_RANGE", G_GRAB, "Scroll range", "Higher values increase scrolling speed more gradually.", 0.05, 0.4, 0.01, "float"),
    _S("SCROLL_MAX_SPEED", G_GRAB, "Maximum scroll speed", "Higher values allow faster scrolling.", 5, 150, 1, "int"),
    _S("SCROLL_INVERT", G_GRAB, "Invert scrolling", "When enabled, moving your hand up scrolls down.", 0, 1, 1, "bool"),

    _S("REAL_MOUSE_INPUT", G_GRAB, "Real mouse input", "Enable this if dragging does not work in some applications. Disable it if cursor movement behaves unexpectedly.", 0, 1, 1, "bool"),

    _S("SWAP_HANDS", G_HANDS, "Swap left and right hands", "Enable this if the detected hands are assigned to the opposite monitors.", 0, 1, 1, "bool"),
    _S("LOST_GRACE_FRAMES", G_HANDS, "Hand tracking grace period (frames)", "Higher values keep a drag active longer when the hand is briefly lost.", 1, 30, 1, "int"),
    _S("CAM_INDEX", G_HANDS, "Camera index", "Applied after saving and restarting the application. 0 is usually the first camera.", 0, 9, 1, "int"),
]
SPEC = {st.name: st for st in SCHEMA}
DEFAULTS = {st.name: globals()[st.name] for st in SCHEMA}
PAIRS = [("PINCH_ON", "PINCH_OFF"), ("RIGHT_ON", "RIGHT_OFF")]
PAIR_GAP = 0.05
SETTINGS_FILE = "hand_mouse_settings.json"
SETTINGS_VERSION = 0


def area_box():
    'Returns the green area as (left, top, size), relative to the camera frame. Offsets use the available margin, so the area stays inside the frame.'
    size = min(max(float(AREA_SIZE), 0.2), 1.0)
    free = (1.0 - size) / 2.0
    sx = min(max(float(AREA_SHIFT_X), -100.0), 100.0) / 100.0
    sy = min(max(float(AREA_SHIFT_UP), -100.0), 100.0) / 100.0
    return free + sx * free, free - sy * free, size


SOCIAL_LINKS = [
    ("Telegram", "https://t.me/sobhani_matin"),
    ("Instagram", "https://www.instagram.com/matinsobahnidev/"),
    ("GitHub", "https://github.com/matinsobhanidev"),
    ("Bale", "https://ble.ir/sobhani_matin"),
]


HELP_TEXT = [
    ("h", "What is this app?"),
    ("p", "Use your webcam to track your hand and control the mouse pointer."),
    ("h", "Getting started"),
    ("p", "1. Sit in front of your camera and bring one hand into view."),
    ("p", "2. Move your palm to move the cursor."),
    ("p", "3. Moving your palm inside the green area maps it to the full monitor."),
    ("p", "4. Each hand controls a monitor. With one monitor, either hand controls it."),
    ("h", "Hand gestures"),
    ("p", "• Pinch thumb and index finger, then release: left click"),
    ("p", "• Pinch thumb and index finger twice quickly: double-click"),
    ("p", "• Pinch thumb and middle finger: right click"),
    ("p", "• Hold a V gesture (index and middle fingers open): scroll"),
    ("p", "  Move your hand above the starting point to scroll up, or below it to scroll down."),
    ("p", "• Pinch all four fingertips to the thumb, or make a fist: drag"),
    ("p", "  To move an item to another monitor, keep holding the gesture, move your hand, then release."),
    ("h", "Camera window buttons"),
    ("p", "• Settings: open settings (the S key does the same)"),
    ("p", "• Stop / Start: pause or resume mouse control"),
    ("p", "• Help: open this page"),
    ("p", "• Exit: close the app (Q or Esc also exits)"),
    ("h", "Settings"),
    ("p", "Changes take effect immediately. Use Save to keep them for the next launch."),
    ("p", "Adjust the green area size and position on the Movement page. A preview is shown there."),
    ("p", "If dragging does not work in an application, enable Real mouse input on the Grab and scroll page."),
    ("h", "About"),
    ("p", APP_AUTHOR),
]


def settings_paths():
    base = os.environ.get("APPDATA") or os.path.expanduser("~")
    return [os.path.join(app_dir(), SETTINGS_FILE),
            os.path.join(base, "HandMouse", SETTINGS_FILE)]


def current_values():
    g = globals()
    return {n: g[n] for n in SPEC}


def apply_values(vals):
    'Applies values to the application settings. The main loop detects the update.'
    global SETTINGS_VERSION
    g = globals()
    for k, v in vals.items():
        if k in SPEC:
            g[k] = v
    SETTINGS_VERSION += 1


def decimals_of(step):
    r = repr(float(step))
    return len(r.split(".")[1]) if "." in r and not r.endswith(".0") else 0


def coerce_value(st, v):
    if st.kind == "bool":
        if not isinstance(v, bool):
            raise ValueError
        return v
    if isinstance(v, bool):
        raise ValueError
    x = float(v)
    x = min(max(x, st.lo), st.hi)
    if st.kind == "int":
        return int(round(x))
    return round(x, 4)


def enforce_pairs(vals, moved=None):
    'Ensures that each release threshold is greater than its activation threshold. Returns the names of adjusted settings.'
    changed = []
    for on, off in PAIRS:
        if vals[off] < vals[on] + PAIR_GAP - 1e-9:
            if moved == off:
                vals[on] = round(max(SPEC[on].lo, vals[off] - PAIR_GAP), 4)
                changed.append(on)
            else:
                vals[off] = round(min(SPEC[off].hi, vals[on] + PAIR_GAP), 4)
                changed.append(off)
            if vals[off] < vals[on] + PAIR_GAP - 1e-9:
                vals[on] = round(vals[off] - PAIR_GAP, 4)
                changed.append(on)
    return changed


def load_user_settings():
    for path in settings_paths():
        if not os.path.exists(path):
            continue
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            if not isinstance(data, dict):
                raise ValueError
        except Exception:
            show_message('The settings file is invalid and will be ignored. Default settings will be used:\n' + path,
                         "warning")
            return
        vals = current_values()
        if "AREA_SIZE" not in data and "MARGIN" in data:
            try:
                data["AREA_SIZE"] = round(1 - 2 * float(data["MARGIN"]), 4)
            except Exception:
                pass
        for k, v in data.items():
            st = SPEC.get(k)
            if st is None:
                continue
            try:
                vals[k] = coerce_value(st, v)
            except Exception:
                pass
        enforce_pairs(vals)
        apply_values(vals)
        return


def save_settings(vals):
    'Saves settings to disk and returns the saved path, or None on failure.'
    data = {n: vals[n] for n in SPEC}
    for path in settings_paths():
        try:
            os.makedirs(os.path.dirname(path), exist_ok=True)
            with open(path, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            return path
        except Exception:
            continue
    return None


UI = {
    "bg": "#eef1f6", "card": "#ffffff", "line": "#e2e8f0", "text": "#0f172a", "muted": "#64748b",
    "accent": "#2563eb", "accent_dk": "#1d4ed8", "accent_lt": "#dbeafe",
    "side": "#0f172a", "side_hi": "#1e293b", "ok": "#16a34a", "bad": "#dc2626",
}
HELP_NAME = 'Help & About'
GROUP_INFO = {
    G_MOVE: 'Cursor movement and green-area size and position',
    G_STEADY: 'Reduce hand tremor in cursor movement',
    G_CLICK: 'Left click, double-click, and right click',
    G_GRAB: 'Drag, scrolling, and mouse input',
    G_HANDS: 'Hand identification and camera settings',
}
APP_VERSION = '7.0.0'


class SettingsWindow:
    'Settings window with a sidebar and slider cards. Changes apply immediately.'

    def __init__(self):
        self.root = None
        self.tk = None
        self.busy = False
        self.saved = {}
        self.note = ("", UI["ok"])
        self.k = 1.0
        self.pages, self.rows = {}, {}
        self.current = None
        self.cur_canvas = None
        self.preview = None
        self.vars, self.val_labels = {}, {}
        self.status_lbl = None

    @property
    def is_open(self):
        return self.root is not None

    def open(self, tab=None):
        'Set tab="help" to open the Help & About page directly.'
        if self.root is not None:
            try:
                self.root.deiconify()
                self.root.lift()
                self._select_tab(tab)
                return
            except Exception:
                self.root = None
        try:
            self._build()
            self._select_tab(tab)
        except Exception:
            self.root = None
            show_message('The settings window could not be opened.', "warning")

    def _open_url(self, url):
        try:
            import webbrowser
            webbrowser.open(url)
        except Exception:
            pass

    def _select_tab(self, tab):
        if tab == "help":
            self.show(HELP_NAME)

    def close(self):
        if self.root is not None:
            try:
                self.root.destroy()
            except Exception:
                pass
            self.root = None
            self.pages, self.rows = {}, {}
            self.current = self.cur_canvas = self.preview = None

    def pump(self):
        if self.root is None:
            return
        try:
            self.root.update()
        except Exception:
            self.root = None


    def _btn(self, parent, text, cmd, primary=False):
        tk = self.tk
        bg = UI["accent"] if primary else "#e2e8f0"
        fg = "#ffffff" if primary else UI["text"]
        hov = UI["accent_dk"] if primary else "#cbd5e1"
        b = tk.Button(parent, text=text, command=cmd, font=self.FB, bg=bg, fg=fg, activebackground=hov,
                      activeforeground=fg, relief="flat", bd=0, padx=18, pady=7, cursor="hand2",
                      highlightthickness=0)
        b.bind("<Enter>", lambda e: b.config(bg=hov))
        b.bind("<Leave>", lambda e: b.config(bg=bg))
        return b

    def _card(self, parent, bg=None):
        tk = self.tk
        bg = bg or UI["card"]
        c = tk.Frame(parent, bg=bg, highlightbackground=UI["line"], highlightthickness=1, bd=0)
        c.pack(fill="x", padx=22, pady=5)
        body = tk.Frame(c, bg=bg)
        body.pack(fill="x", padx=16, pady=12)
        return c, body

    def _toggle(self, parent, var, command):
        'Toggle switch.'
        tk, k = self.tk, self.k
        W, H = int(46 * k), int(26 * k)
        c = tk.Canvas(parent, width=W, height=H, bg=UI["card"], highlightthickness=0, cursor="hand2")

        def draw(*_):
            try:
                c.delete("all")
                on = bool(var.get())
                col = UI["accent"] if on else "#cbd5e1"
                r = H / 2
                c.create_oval(0, 0, H, H, fill=col, outline=col)
                c.create_oval(W - H, 0, W, H, fill=col, outline=col)
                c.create_rectangle(r, 0, W - r, H, fill=col, outline=col)
                pad = 3 * k
                x0 = (W - H + pad) if on else pad
                c.create_oval(x0, pad, x0 + H - 2 * pad, H - pad, fill="#ffffff", outline="#ffffff")
            except Exception:
                pass

        def click(_e):
            var.set(not bool(var.get()))
            command()

        c.bind("<Button-1>", click)
        var.trace_add("write", draw)
        draw()
        return c

    def _make_page(self, parent):
        'Creates a scrollable page and returns the outer frame, canvas, and inner frame.'
        tk = self.tk
        from tkinter import ttk
        outer = tk.Frame(parent, bg=UI["bg"])
        canvas = tk.Canvas(outer, bg=UI["bg"], highlightthickness=0, bd=0)
        sb = ttk.Scrollbar(outer, orient="vertical", command=canvas.yview)
        canvas.configure(yscrollcommand=sb.set)
        sb.pack(side="left", fill="y")
        canvas.pack(side="left", fill="both", expand=True)
        inner = tk.Frame(canvas, bg=UI["bg"])
        win = canvas.create_window((0, 0), window=inner, anchor="nw")
        inner.bind("<Configure>", lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
        canvas.bind("<Configure>", lambda e: canvas.itemconfigure(win, width=e.width))
        return outer, canvas, inner

    def _page_header(self, inner, title, sub):
        tk = self.tk
        box = tk.Frame(inner, bg=UI["bg"])
        box.pack(fill="x", padx=22, pady=(20, 8))
        tk.Label(box, text=title, font=("Segoe UI", 16, "bold"), fg=UI["text"], bg=UI["bg"],
                 anchor="w").pack(fill="x")
        tk.Label(box, text=sub, font=self.FS, fg=UI["muted"], bg=UI["bg"], anchor="w").pack(fill="x")

    def _build_preview(self, inner):
        tk, k = self.tk, self.k
        card, body = self._card(inner)
        tk.Label(body, text='Green area preview', font=self.FB, fg=UI["text"], bg=UI["card"],
                 anchor="w").pack(fill="x")
        tk.Label(body, text='Moving your palm inside this area maps it to the full monitor. Use the sliders below to resize or reposition the area.',
                 font=self.FS, fg=UI["muted"], bg=UI["card"], anchor="w", justify="left",
                 wraplength=int(450 * k)).pack(fill="x", pady=(4, 10))
        self.preview = tk.Canvas(body, width=int(200 * k), height=int(150 * k), bg="#0f172a",
                                 highlightthickness=0)
        self.preview.pack(pady=(0, 2))
        self._draw_preview()

    def _draw_preview(self):
        c = self.preview
        if c is None:
            return
        try:
            c.delete("all")
            W, H = int(c["width"]), int(c["height"])
            for i in range(1, 4):
                c.create_line(W * i / 4, 0, W * i / 4, H, fill="#1e293b")
                c.create_line(0, H * i / 4, W, H * i / 4, fill="#1e293b")
            left, top, size = area_box()
            x0, y0, x1, y1 = left * W, top * H, (left + size) * W, (top + size) * H
            c.create_rectangle(x0 + 1, y0 + 1, x1 - 1, y1 - 1, outline="#22c55e", width=2)
            c.create_text(x0 + 8, y1 - 10, text="cursor area", fill="#22c55e", anchor="w",
                          font=("Segoe UI", 8))
            c.create_text(W - 6, 8, text="camera", fill="#64748b", anchor="w", font=("Segoe UI", 8))
        except Exception:
            pass

    def _setting_card(self, inner, st):
        tk, k = self.tk, self.k
        card, body = self._card(inner)
        top = tk.Frame(body, bg=UI["card"])
        top.pack(fill="x")
        cur = globals()[st.name]
        tk.Label(top, text=st.label, font=self.FB, fg=UI["text"], bg=UI["card"], anchor="w",
                 justify="left").pack(side="right")
        if st.kind == "bool":
            var = tk.BooleanVar(master=self.root, value=bool(cur))
            self._toggle(top, var, lambda n=st.name: self._changed(n)).pack(side="left")
        else:
            var = (tk.IntVar if st.kind == "int" else tk.DoubleVar)(master=self.root, value=cur)
            badge = tk.Label(top, text=self._fmt(st.name, cur), font=self.FB, fg=UI["accent"],
                             bg=UI["accent_lt"], padx=10, pady=2, width=6)
            badge.pack(side="left")
            self.val_labels[st.name] = badge
        tk.Label(body, text=st.help, font=self.FS, fg=UI["muted"], bg=UI["card"], anchor="w",
                 justify="left", wraplength=int(450 * k)).pack(fill="x", pady=(4, 0))
        if st.kind != "bool":
            tk.Scale(body, from_=st.lo, to=st.hi, resolution=st.step, orient="horizontal", variable=var,
                     showvalue=False, width=int(12 * k), sliderlength=int(24 * k), bg=UI["card"],
                     troughcolor="#dbe3ef", activebackground=UI["accent"], highlightthickness=0, bd=0,
                     relief="flat", sliderrelief="flat",
                     command=lambda _v, n=st.name: self._changed(n)).pack(fill="x", pady=(8, 0))
        self.vars[st.name] = var

    def _build_help(self, inner):
        tk, k = self.tk, self.k
        self._page_header(inner, HELP_NAME, 'How the application works and author information')
        sections, cur = [], None
        for tag, line in HELP_TEXT:
            if tag == "h":
                cur = [line, []]
                sections.append(cur)
            elif cur is not None:
                cur[1].append(line)
        for title, lines in sections:
            if title == 'About':
                card, body = self._card(inner, bg=UI["accent"])
                tk.Label(body, text='Created by', font=self.FS, fg="#bfdbfe", bg=UI["accent"],
                         anchor="w").pack(fill="x")
                for ln in lines:
                    tk.Label(body, text=ln, font=("Segoe UI", 18, "bold"), fg="#ffffff", bg=UI["accent"],
                             anchor="w").pack(fill="x", pady=(2, 0))
                tk.Label(body, text='Version ' + APP_VERSION, font=self.FS, fg="#bfdbfe", bg=UI["accent"],
                         anchor="w").pack(fill="x", pady=(4, 0))
                tk.Label(body, text='Social links (click to open)', font=self.FS, fg="#bfdbfe",
                         bg=UI["accent"], anchor="w").pack(fill="x", pady=(14, 4))
                for sname, url in SOCIAL_LINKS:
                    row = tk.Frame(body, bg=UI["accent"])
                    row.pack(fill="x", pady=2)
                    tk.Label(row, text=sname, font=self.FB, fg="#ffffff", bg=UI["accent"], width=10,
                             anchor="w").pack(side="right")
                    lk = tk.Label(row, text=url, font=("Segoe UI", 9, "underline"), fg="#dbeafe",
                                  bg=UI["accent"], cursor="hand2", anchor="w")
                    lk.pack(side="right", padx=(0, 8))
                    lk.bind("<Button-1>", lambda e, u=url: self._open_url(u))
                continue
            card, body = self._card(inner)
            tk.Label(body, text=title, font=self.FH, fg=UI["accent"], bg=UI["card"],
                     anchor="w").pack(fill="x", pady=(0, 4))
            for ln in lines:
                sub = ln.startswith("  ")
                tk.Label(body, text=ln.strip(), font=self.FS if sub else self.F,
                         fg=UI["muted"] if sub else UI["text"], bg=UI["card"], anchor="w", justify="left",
                         wraplength=int(440 * k)).pack(fill="x", padx=(0, 18 if sub else 0), pady=1)


    def _build(self):
        import tkinter as tk
        from tkinter import ttk

        root = tk.Tk()
        self.root, self.tk = root, tk
        root.title('Settings - ' + APP_TITLE)
        root.attributes("-topmost", True)
        root.configure(bg=UI["bg"])
        root.protocol("WM_DELETE_WINDOW", self._on_close)
        try:
            self.k = max(1.0, float(root.winfo_fpixels("1i")) / 96.0)
        except Exception:
            self.k = 1.0
        k = self.k
        sw_, sh_ = root.winfo_screenwidth(), root.winfo_screenheight()
        ww_, wh_ = min(int(780 * k), sw_ - 60), min(int(580 * k), sh_ - 100)
        root.minsize(min(int(680 * k), ww_), min(int(460 * k), wh_))
        root.geometry(f"{ww_}x{wh_}+60+40")
        self.F, self.FB = ("Segoe UI", 10), ("Segoe UI", 10, "bold")
        self.FS, self.FH = ("Segoe UI", 9), ("Segoe UI", 11, "bold")

        try:
            style = ttk.Style(root)
            style.theme_use("clam")
            style.configure("Vertical.TScrollbar", background="#cbd5e1", troughcolor=UI["bg"],
                            bordercolor=UI["bg"], lightcolor="#cbd5e1", darkcolor="#cbd5e1",
                            arrowcolor="#64748b")
        except Exception:
            pass

        self.busy = True
        self.vars, self.val_labels = {}, {}
        self.pages, self.rows = {}, {}
        self.current = self.cur_canvas = self.preview = None
        self.saved = current_values()
        self.note = ("", UI["ok"])


        bar = tk.Frame(root, bg="#ffffff", highlightbackground=UI["line"], highlightthickness=1)
        bar.pack(side="bottom", fill="x")
        binner = tk.Frame(bar, bg="#ffffff")
        binner.pack(fill="x", padx=18, pady=10)
        for text, cmd, primary in (('Save', self._save, True), ('Reset to defaults', self._reset, False),
                                   ('Close', self._on_close, False)):
            self._btn(binner, text, cmd, primary).pack(side="right", padx=(8, 0))
        self.status_lbl = tk.Label(binner, text="", font=self.FB, bg="#ffffff", anchor="w")
        self.status_lbl.pack(side="left")


        side = tk.Frame(root, bg=UI["side"], width=int(180 * k))
        side.pack(side="left", fill="y")
        side.pack_propagate(False)
        brand = tk.Frame(side, bg=UI["side"])
        brand.pack(fill="x", padx=18, pady=(22, 18))
        tk.Label(brand, text='Settings', font=("Segoe UI", 17, "bold"), fg="#ffffff", bg=UI["side"],
                 anchor="w").pack(fill="x")
        tk.Label(brand, text=APP_TITLE, font=self.FS, fg="#94a3b8", bg=UI["side"], anchor="w").pack(fill="x")
        tk.Label(side, text='Author: ' + APP_AUTHOR + '\nVersion ' + APP_VERSION, font=self.FS, fg="#64748b",
                 bg=UI["side"], justify="left", anchor="w").pack(side="bottom", fill="x", padx=18, pady=14)

        groups = []
        for st in SCHEMA:
            if st.group not in groups:
                groups.append(st.group)
        for name in groups + [HELP_NAME]:
            row = tk.Frame(side, bg=UI["side"], cursor="hand2")
            row.pack(fill="x")
            strip = tk.Frame(row, width=4, bg=UI["side"])
            strip.pack(side="right", fill="y")
            lbl = tk.Label(row, text=name, font=self.F, fg="#94a3b8", bg=UI["side"], anchor="w",
                           padx=16, pady=11, cursor="hand2")
            lbl.pack(side="right", fill="x", expand=True)
            for wdg in (row, strip, lbl):
                wdg.bind("<Button-1>", lambda e, n=name: self.show(n))
            self.rows[name] = (row, strip, lbl)


        content = tk.Frame(root, bg=UI["bg"])
        content.pack(side="left", fill="both", expand=True)
        for g in groups:
            outer, canvas, inner = self._make_page(content)
            self.pages[g] = (outer, canvas)
            self._page_header(inner, g, GROUP_INFO.get(g, ""))
            if g == G_MOVE:
                self._build_preview(inner)
            for st in SCHEMA:
                if st.group == g:
                    self._setting_card(inner, st)
            if g == G_HANDS:
                card, body = self._card(inner)
                tk.Label(body, text='Settings file location', font=self.FB, fg=UI["text"], bg=UI["card"],
                         anchor="w").pack(fill="x")
                tk.Label(body, text=settings_paths()[0], font=self.FS, fg=UI["muted"], bg=UI["card"],
                         anchor="w", justify="left", wraplength=int(450 * k)).pack(fill="x", pady=(4, 0))
            tk.Frame(inner, bg=UI["bg"], height=12).pack()
        outer, canvas, inner = self._make_page(content)
        self.pages[HELP_NAME] = (outer, canvas)
        self._build_help(inner)
        tk.Frame(inner, bg=UI["bg"], height=12).pack()

        root.bind_all("<MouseWheel>", self._wheel)
        root.bind_all("<Button-4>", self._wheel)
        root.bind_all("<Button-5>", self._wheel)
        self.busy = False
        self.show(groups[0])
        self._refresh_status()
        root.update_idletasks()

    def show(self, name):
        if self.root is None or name not in self.pages:
            return
        if self.current in self.pages:
            self.pages[self.current][0].pack_forget()
        outer, canvas = self.pages[name]
        outer.pack(fill="both", expand=True)
        self.current, self.cur_canvas = name, canvas
        for n, (row, strip, lbl) in self.rows.items():
            on = n == name
            bg = UI["side_hi"] if on else UI["side"]
            row.config(bg=bg)
            lbl.config(bg=bg, fg="#ffffff" if on else "#94a3b8", font=self.FB if on else self.F)
            strip.config(bg=UI["accent"] if on else bg)

    def _wheel(self, e):
        c = self.cur_canvas
        if c is None:
            return
        try:
            if c.yview() == (0.0, 1.0):
                return
            up = getattr(e, "num", 0) == 4 or getattr(e, "delta", 0) > 0
            c.yview_scroll(-2 if up else 2, "units")
        except Exception:
            pass


    def _fmt(self, name, v):
        st = SPEC[name]
        return str(int(v)) if st.kind == "int" else f"{v:.{decimals_of(st.step)}f}"

    def _set_var(self, name, v):
        self.busy = True
        try:
            self.vars[name].set(v)
        finally:
            self.busy = False

    def _sync_labels(self):
        cur = current_values()
        for n, vl in self.val_labels.items():
            vl.config(text=self._fmt(n, cur[n]))
        self._draw_preview()

    def _dirty(self):
        cur = current_values()
        return any(cur[n] != self.saved[n] and not (SPEC[n].kind == "float" and abs(cur[n] - self.saved[n]) < 1e-9)
                   for n in SPEC)

    def _refresh_status(self):
        if self.status_lbl is None:
            return
        if self._dirty():
            self.status_lbl.config(text='●  Unsaved changes', fg=UI["bad"])
        else:
            self.status_lbl.config(text=self.note[0], fg=self.note[1])


    def _changed(self, name):
        if self.busy or self.root is None:
            return
        st = SPEC[name]
        try:
            raw = self.vars[name].get()
            new = bool(raw) if st.kind == "bool" else coerce_value(st, raw)
        except Exception:
            return
        cur = globals()[name]
        if new == cur or (st.kind == "float" and abs(new - cur) < st.step / 2):
            return
        vals = current_values()
        vals[name] = new
        for n in enforce_pairs(vals, name):
            self._set_var(n, vals[n])
        apply_values(vals)
        self.note = ("", UI["ok"])
        self._sync_labels()
        self._refresh_status()

    def _save(self):
        vals = current_values()
        path = save_settings(vals)
        if path:
            self.saved = vals
            self.note = ('✓  Saved', UI["ok"])
        else:
            self.note = ('Could not save: write access is unavailable in the application folder and %APPDATA%.', UI["bad"])
        self._refresh_status()

    def _reset(self):
        for n, v in DEFAULTS.items():
            self._set_var(n, v)
        apply_values(dict(DEFAULTS))
        self.note = ("", UI["ok"])
        self._sync_labels()
        self._refresh_status()

    def _on_close(self):
        if self.root is not None and self._dirty():
            try:
                from tkinter import messagebox
                ans = messagebox.askyesnocancel(
                    'Settings', 'You have unsaved changes. Save them?\n(Choose No to restore the previous settings.)',
                    parent=self.root)
            except Exception:
                ans = True
            if ans is None:
                return
            if ans:
                self._save()
            else:
                apply_values(dict(self.saved))
        self.close()


load_user_settings()




def mon_key(m):
    return [int(m.x), int(m.y), int(m.width), int(m.height)]


def detect_monitors():
    try:
        mons = sorted(get_monitors(), key=lambda m: (m.x, m.y))
    except Exception:
        mons = []
    if not mons:
        raise AppError('No monitors were detected. Check your display connections and restart the application.')
    return mons


def default_two(mons):
    'Fallback when the monitor selection dialog cannot be opened: use the primary monitor and its nearest neighbor.'
    primary = next((m for m in mons if m.is_primary), mons[0])
    pcx, pcy = primary.x + primary.width / 2, primary.y + primary.height / 2
    others = [m for m in mons if m is not primary]
    near = min(others, key=lambda m: math.hypot(m.x + m.width / 2 - pcx, m.y + m.height / 2 - pcy))
    return sorted([primary, near], key=lambda m: (m.x, m.y))


def build_by_label(active):
    'Returns the monitor controlled by each hand (Left/Right).'
    if len(active) == 1:
        return {"Left": active[0], "Right": active[0]}
    a, b = active
    acx, acy = a.x + a.width / 2, a.y + a.height / 2
    bcx, bcy = b.x + b.width / 2, b.y + b.height / 2
    if abs(bcx - acx) >= abs(bcy - acy):
        left, right = (a, b) if acx <= bcx else (b, a)
        return {"Left": left, "Right": right}
    top, bottom = (a, b) if acy <= bcy else (b, a)
    return {"Left": bottom, "Right": top}


class MonitorSetup:
    def __init__(self, all_mons, active):
        self.signature = [mon_key(m) for m in all_mons]
        self.active = active
        self.by_label = build_by_label(active)
        self.vx0 = min(m.x for m in active)
        self.vx1 = max(m.x + m.width for m in active)
        self.vy0 = min(m.y for m in active)
        self.vy1 = max(m.y + m.height for m in active)

    def for_label(self, label):
        return self.by_label["Right" if label == "Right" else "Left"]

    def monitor_at(self, x, y):
        for m in self.active:
            if m.x <= x < m.x + m.width and m.y <= y < m.y + m.height:
                return m
        return None


def load_saved_choice(mons):
    try:
        with open(CONFIG_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
        if data.get("all") != [mon_key(m) for m in mons]:
            return None
        chosen = [m for m in mons if mon_key(m) in data.get("selected", [])]
        return chosen if 1 <= len(chosen) <= 2 else None
    except Exception:
        return None


def save_choice(mons, chosen):
    try:
        with open(CONFIG_PATH, "w", encoding="utf-8") as f:
            json.dump({"all": [mon_key(m) for m in mons],
                       "selected": [mon_key(m) for m in chosen]}, f)
    except Exception:
        pass


def ask_monitors(mons):
    'Monitor selection dialog (shown when more than two monitors are connected). Returns the selected monitors and whether to save the choice, or None if cancelled.'
    import tkinter as tk

    root = tk.Tk()
    root.title('Select monitors - ' + APP_TITLE)
    root.attributes("-topmost", True)
    root.resizable(False, False)
    result = {"value": None}

    tk.Label(root, text=f"{len(mons)} monitor(s) detected.\\nChoose which monitors Hand Mouse should control.\\n"
                        "(Select one or two monitors, or click a monitor in the layout.)",
             font=("Segoe UI", 11, "bold"), justify="left", anchor="w"
             ).pack(fill="x", padx=14, pady=(12, 6))


    CW, CH = 440, 170
    vx0 = min(m.x for m in mons)
    vx1 = max(m.x + m.width for m in mons)
    vy0 = min(m.y for m in mons)
    vy1 = max(m.y + m.height for m in mons)
    scale = min((CW - 24) / max(1, vx1 - vx0), (CH - 24) / max(1, vy1 - vy0))
    ox = (CW - (vx1 - vx0) * scale) / 2
    oy = (CH - (vy1 - vy0) * scale) / 2
    canvas = tk.Canvas(root, width=CW, height=CH, bg="#1e1e1e", highlightthickness=0)
    canvas.pack(padx=14, pady=4)

    vars_ = [tk.BooleanVar(master=root, value=False) for _ in mons]
    for v in vars_[:2]:
        v.set(True)

    def rect_of(m):
        x0 = ox + (m.x - vx0) * scale
        y0 = oy + (m.y - vy0) * scale
        return x0, y0, x0 + m.width * scale, y0 + m.height * scale

    def redraw():
        canvas.delete("all")
        for i, m in enumerate(mons):
            x0, y0, x1, y1 = rect_of(m)
            canvas.create_rectangle(x0, y0, x1, y1, outline="white", width=2,
                                    fill="#2d7ff9" if vars_[i].get() else "#4a4a4a")
            canvas.create_text((x0 + x1) / 2, (y0 + y1) / 2, text=str(i + 1),
                               fill="white", font=("Segoe UI", 18, "bold"))

    def on_click(ev):
        for i, m in enumerate(mons):
            x0, y0, x1, y1 = rect_of(m)
            if x0 <= ev.x <= x1 and y0 <= ev.y <= y1:
                vars_[i].set(not vars_[i].get())
                redraw()
                break

    canvas.bind("<Button-1>", on_click)


    rows = tk.Frame(root)
    rows.pack(fill="x", padx=14, pady=4)
    rows.columnconfigure(1, weight=1)
    for i, m in enumerate(mons):
        txt = f"Monitor {i + 1}" + (' (Primary)' if m.is_primary else "")
        tk.Label(rows, text=f"{m.width}x{m.height}", font=("Segoe UI", 10), fg="#666"
                 ).grid(row=i, column=0, sticky="w")
        tk.Checkbutton(rows, text=txt, variable=vars_[i], command=redraw,
                       font=("Segoe UI", 10), anchor="w", justify="left"
                       ).grid(row=i, column=1, sticky="e")

    save_var = tk.BooleanVar(master=root, value=True)
    tk.Checkbutton(root, text='Save this selection (do not ask again)', variable=save_var,
                   font=("Segoe UI", 10), anchor="w", justify="left"
                   ).pack(fill="x", padx=14, pady=(6, 0))

    warn = tk.Label(root, text="", fg="#d32f2f", font=("Segoe UI", 10), anchor="w", justify="left")
    warn.pack(fill="x", padx=14)

    def ok():
        chosen = [m for m, v in zip(mons, vars_) if v.get()]
        if not 1 <= len(chosen) <= 2:
            warn.config(text='Select one or two monitors.')
            return
        result["value"] = (chosen, bool(save_var.get()))
        root.destroy()

    btns = tk.Frame(root)
    btns.pack(pady=(4, 12))
    tk.Button(btns, text='OK', width=12, command=ok, font=("Segoe UI", 10)).pack(side="left", padx=6)
    tk.Button(btns, text='Cancel (Exit)', width=14, command=root.destroy,
              font=("Segoe UI", 10)).pack(side="left", padx=6)
    root.protocol("WM_DELETE_WINDOW", root.destroy)

    redraw()
    root.update_idletasks()
    sw, sh = root.winfo_screenwidth(), root.winfo_screenheight()
    root.geometry(f"+{(sw - root.winfo_reqwidth()) // 2}+{(sh - root.winfo_reqheight()) // 3}")
    root.mainloop()
    return result["value"]


def resolve_setup():
    'Detects monitors and creates the hand-to-monitor mapping. Returns None if the user cancels.'
    mons = detect_monitors()
    if len(mons) <= 2:
        active = mons
    else:
        active = load_saved_choice(mons)
        if active is None:
            try:
                ans = ask_monitors(mons)
            except Exception:
                ans = (default_two(mons), False)
            if ans is None:
                return None
            active, save = ans
            if save:
                save_choice(mons, active)
    return MonitorSetup(mons, active)




class OneEuro:
    'One Euro filter: strong smoothing for a steady hand and low latency during fast movement.'

    def __init__(self, min_cutoff, beta, d_cutoff=1.0):
        self.min_cutoff, self.beta, self.d_cutoff = min_cutoff, beta, d_cutoff
        self.reset()

    def reset(self):
        self.t = None
        self.x = 0.0
        self.dx = 0.0

    @staticmethod
    def _alpha(cutoff, dt):
        tau = 1.0 / (2.0 * math.pi * cutoff)
        return 1.0 / (1.0 + tau / dt)

    def __call__(self, x, t):
        if self.t is None:
            self.t, self.x, self.dx = t, x, 0.0
            return x
        dt = max(t - self.t, 1e-3)
        dx = (x - self.x) / dt
        a_d = self._alpha(self.d_cutoff, dt)
        self.dx += a_d * (dx - self.dx)
        cutoff = self.min_cutoff + self.beta * abs(self.dx)
        a = self._alpha(cutoff, dt)
        self.x += a * (x - self.x)
        self.t = t
        return self.x


class Deadzone:
    'Keeps the target fixed until it moves outside a small radius around the anchor point.'

    def __init__(self):
        self.reset()

    def reset(self):
        self.ax = self.ay = None
        self.key = None

    def apply(self, tx, ty, radius, key):
        if key != self.key or self.ax is None:
            self.key = key
            self.ax, self.ay = tx, ty
            return tx, ty
        if radius <= 0:
            self.ax, self.ay = tx, ty
            return tx, ty
        dx, dy = tx - self.ax, ty - self.ay
        dist = math.hypot(dx, dy)
        if dist > radius:
            k = (dist - radius) / dist
            self.ax += dx * k
            self.ay += dy * k
        return self.ax, self.ay




def ensure_model():
    """Ensure the MediaPipe model is available in a writable location."""
    global MODEL_PATH

    if os.path.exists(MODEL_PATH):
        try:
            if os.path.getsize(MODEL_PATH) > 1_000_000:
                return
            os.remove(MODEL_PATH)
        except OSError:
            MODEL_PATH = ""

    if not MODEL_PATH:
        MODEL_PATH = os.path.join(app_dir(), MODEL_NAME)

    target_dir = os.path.dirname(MODEL_PATH) or app_dir()
    try:
        os.makedirs(target_dir, exist_ok=True)
        with tempfile.NamedTemporaryFile(dir=target_dir, prefix=".handmouse-write-test-", delete=True):
            pass
    except OSError:
        data_root = os.environ.get("LOCALAPPDATA") or os.environ.get("APPDATA") or os.path.expanduser("~")
        target_dir = os.path.join(data_root, "HandMouse", "models")
        try:
            os.makedirs(target_dir, exist_ok=True)
            MODEL_PATH = os.path.join(target_dir, MODEL_NAME)
        except OSError as exc:
            raise AppError("The model folder is not writable. Check folder permissions and try again.") from exc

    if os.path.exists(MODEL_PATH):
        try:
            if os.path.getsize(MODEL_PATH) > 1_000_000:
                return
            os.remove(MODEL_PATH)
        except OSError as exc:
            raise AppError("An incomplete model file could not be removed. Delete hand_landmarker.task manually.") from exc

    show_message(
        "The hand-tracking model (approximately 7 MB) must be downloaded before the first launch.\n"
        "An internet connection is required.\n\n"
        "Click OK and wait for the camera window to open.",
        "info",
    )

    tmp_path = MODEL_PATH + ".part"
    try:
        with urllib.request.urlopen(MODEL_URL, timeout=30) as response, open(tmp_path, "wb") as output:
            while True:
                chunk = response.read(256 * 1024)
                if not chunk:
                    break
                output.write(chunk)

        if os.path.getsize(tmp_path) <= 1_000_000:
            raise ValueError("Downloaded model is unexpectedly small.")

        os.replace(tmp_path, MODEL_PATH)
    except Exception as exc:
        try:
            if os.path.exists(tmp_path):
                os.remove(tmp_path)
        except OSError:
            pass
        raise AppError(
            "The hand-tracking model could not be downloaded.\n\n"
            "Check your internet connection and try again, or download "
            "hand_landmarker.task manually and place it beside the application."
        ) from exc


def open_camera():
    "Returns (cap, None) on success or (None, 'closed' | 'noframes') on failure."
    saw_no_frames = False
    order = [CAM_INDEX] + [i for i in range(CAM_SEARCH_COUNT) if i != CAM_INDEX]
    for idx in order:
        cap = None
        if USE_DSHOW and os.name == "nt":
            cap = cv2.VideoCapture(idx, cv2.CAP_DSHOW)
        if cap is None or not cap.isOpened():
            if cap is not None:
                cap.release()
            cap = cv2.VideoCapture(idx)
        if not cap.isOpened():
            cap.release()
            continue
        cap.set(cv2.CAP_PROP_FRAME_WIDTH, CAM_WIDTH)
        cap.set(cv2.CAP_PROP_FRAME_HEIGHT, CAM_HEIGHT)
        cap.set(cv2.CAP_PROP_FPS, CAM_FPS)
        end = time.time() + CAM_OPEN_TIMEOUT
        while time.time() < end:
            ok, fr = cap.read()
            if ok and fr is not None:
                return cap, None
            time.sleep(0.05)
        cap.release()
        saw_no_frames = True
    return None, ("noframes" if saw_no_frames else "closed")


CAM_MSG_CLOSED = ('Camera not found or unavailable.\n\n• Make sure the webcam is connected and not disabled by a physical switch or cover.\n• Close other apps that may be using the camera (Zoom, Teams, your browser, or another Hand Mouse instance).\n• In Windows Settings > Privacy & security > Camera, enable camera access for desktop apps.')
CAM_MSG_NOFRAMES = ('The camera opened but is not providing frames.\n\n• Make sure the camera is enabled and unobstructed.\n• Close other apps that may be using it.\n• Check Windows camera privacy settings.')
CAM_MSG_LOST = ('The camera connection was lost. The camera may have been disabled, disconnected, or opened by another application. Fix the issue and restart Hand Mouse.')




class Debounced:
    'Debounces activation using separate on/off thresholds (hysteresis) and multi-frame confirmation to reduce accidental triggers.'

    def __init__(self, on, off, confirm=1):
        self.on, self.off, self.confirm = on, off, confirm
        self.state = False
        self.count = 0

    @property
    def pending(self):
        return (not self.state) and self.count > 0

    def update(self, value):
        if self.state:
            if value > self.off:
                self.state = False
                self.count = 0
        else:
            if value < self.on:
                self.count += 1
                if self.count >= self.confirm:
                    self.state = True
            else:
                self.count = 0
        return self.state

    def reset(self):
        self.state = False
        self.count = 0


TOOLBAR_NAMES = ("Settings", "Stop", "Help", "Exit")


def draw_toolbar(canvas, top, paused):
    'Draws the buttons below the camera image and returns their hit-test rectangles.'
    font = cv2.FONT_HERSHEY_SIMPLEX
    colors = {"Settings": (150, 95, 40), "Stop": (50, 50, 190), "Help": (120, 100, 40), "Exit": (70, 70, 70)}
    labels = {"Stop": "Start" if paused else "Stop"}
    if paused:
        colors["Stop"] = (60, 150, 60)
    n, gap = len(TOOLBAR_NAMES), 8
    bw = (canvas.shape[1] - gap * (n + 1)) // n
    bh = TOOLBAR_H - 2 * gap
    rects = []
    for i, name in enumerate(TOOLBAR_NAMES):
        x0, y0 = gap + i * (bw + gap), top + gap
        x1, y1 = x0 + bw, y0 + bh
        cv2.rectangle(canvas, (x0, y0), (x1, y1), colors[name], -1)
        cv2.rectangle(canvas, (x0, y0), (x1, y1), (220, 220, 220), 1)
        text = labels.get(name, name)
        (tw, th), _ = cv2.getTextSize(text, font, 0.65, 2)
        cv2.putText(canvas, text, (x0 + (bw - tw) // 2, y0 + (bh + th) // 2),
                    font, 0.65, (255, 255, 255), 2, cv2.LINE_AA)
        rects.append((name, x0, y0, x1, y1))
    return rects


def main():
    setup = resolve_setup()
    if setup is None:
        return

    ensure_model()

    options = vision.HandLandmarkerOptions(
        base_options=mp_python.BaseOptions(model_asset_path=MODEL_PATH),
        running_mode=vision.RunningMode.VIDEO,
        num_hands=1,
        min_hand_detection_confidence=0.6,
        min_hand_presence_confidence=0.4,
        min_tracking_confidence=0.4,
    )
    try:
        landmarker = vision.HandLandmarker.create_from_options(options)
    except Exception:
        try:
            if os.path.exists(MODEL_PATH):
                os.remove(MODEL_PATH)
        except Exception:
            pass
        raise AppError('The hand-tracking model could not be loaded. The model file was removed; restart the application to download it again.')

    cap, why = open_camera()
    if cap is None:
        landmarker.close()
        raise AppError(CAM_MSG_NOFRAMES if why == "noframes" else CAM_MSG_CLOSED)

    idx_pinch = Debounced(PINCH_ON, PINCH_OFF, CONFIRM_FRAMES)
    mid_pinch = Debounced(RIGHT_ON, RIGHT_OFF, RIGHT_CONFIRM_FRAMES)
    grab_state = Debounced(1.0, GRAB_RELEASE, GRAB_CONFIRM_FRAMES)

    cur_x = cur_y = None
    rel_off = None
    stable_label = None
    label_votes = 0
    mid_start = None
    mid_prev = False
    rc_pos = None
    rc_cancel = False

    dragging = False
    drag_rel_ready = False
    drag_hand0 = drag_cur0 = (0.0, 0.0)
    rel_off = None
    rel_hold_until = 0.0
    mon_override = None

    idx_prev = False
    pinch_start = 0.0
    pinch_skip = False
    pinch_pos = None
    last_click_time = 0.0
    last_click_pos = None
    flash_text, flash_until = "", 0.0
    lost_frames = 0
    pos_hist = deque(maxlen=PINCH_BACKTRACK)
    dist_ema = {}


    fx_filter = OneEuro(STEADY_MIN_CUTOFF, STEADY_BETA)
    fy_filter = OneEuro(STEADY_MIN_CUTOFF, STEADY_BETA)
    dz = Deadzone()

    def steady_reset():
        fx_filter.reset()
        fy_filter.reset()
        dz.reset()

    def sm(key, v):
        'Smooths fingertip distances between frames to reduce brief detection jitter.'
        prev = dist_ema.get(key)
        v = v if prev is None else prev + (v - prev) * DIST_SMOOTH
        dist_ema[key] = v
        return v

    scroll_on = scroll_off = 0
    scroll_active = False
    scroll_anchor = None
    scroll_y = None
    scroll_acc = 0.0

    settings_win = SettingsWindow()
    seen_ver = SETTINGS_VERSION


    ui = {"buttons": [], "action": None}
    paused = False

    def on_mouse(event, x, y, flags, param):
        if event == cv2.EVENT_LBUTTONUP:
            for name, x0, y0, x1, y1 in ui["buttons"]:
                if x0 <= x <= x1 and y0 <= y <= y1:
                    ui["action"] = name
                    break

    try:
        cv2.namedWindow(WIN)
        cv2.setMouseCallback(WIN, on_mouse)
    except Exception:
        cap.release()
        landmarker.close()
        cv2.destroyAllWindows()
        raise

    t0 = time.time()
    last_ts = -1
    last_hand_time = time.time()
    last_mon_check = time.time()
    bad_reads = 0
    idle_n = 0

    try:
        while True:

            if settings_win.is_open:
                settings_win.pump()
            if SETTINGS_VERSION != seen_ver:
                seen_ver = SETTINGS_VERSION
                idx_pinch.on, idx_pinch.off, idx_pinch.confirm = PINCH_ON, PINCH_OFF, CONFIRM_FRAMES
                mid_pinch.on, mid_pinch.off, mid_pinch.confirm = RIGHT_ON, RIGHT_OFF, RIGHT_CONFIRM_FRAMES
                grab_state.off, grab_state.confirm = GRAB_RELEASE, GRAB_CONFIRM_FRAMES
                for f_ in (fx_filter, fy_filter):
                    f_.min_cutoff, f_.beta = STEADY_MIN_CUTOFF, STEADY_BETA


            if time.time() - last_mon_check > MON_CHECK_EVERY:
                last_mon_check = time.time()
                try:
                    sig = [mon_key(m) for m in sorted(get_monitors(), key=lambda m: (m.x, m.y))]
                except Exception:
                    sig = None
                if sig is not None and sig != setup.signature:
                    if dragging:
                        pyautogui.mouseUp()
                        dragging = False
                        drag_rel_ready = False
                    settings_win.close()
                    new_setup = resolve_setup()
                    if new_setup is None:
                        break
                    setup = new_setup
                    mon_override = None
                    cur_x = cur_y = None
                    rel_off = None
                    steady_reset()
                    last_mon_check = time.time()

            ok, frame = cap.read()
            if not ok or frame is None:
                bad_reads += 1
                if bad_reads >= CAM_LOST_FRAMES:
                    if dragging:
                        pyautogui.mouseUp()
                        dragging = False
                        drag_rel_ready = False
                    cap.release()
                    cap, why = open_camera()
                    if cap is None:
                        raise AppError(CAM_MSG_LOST)
                    bad_reads = 0
                if cv2.waitKey(30) & 0xFF in (ord("q"), 27):
                    break
                continue
            bad_reads = 0

            frame = cv2.flip(frame, 1)
            h, w = frame.shape[:2]
            now = time.time()
            idle = (now - last_hand_time) > IDLE_AFTER
            skip_detect = False
            if idle:
                idle_n = (idle_n + 1) % IDLE_DETECT_EVERY
                skip_detect = idle_n != 0

            if skip_detect or paused:
                res = None
            else:
                rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                mp_image = mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb)
                ts = int((time.time() - t0) * 1000)
                if ts <= last_ts:
                    ts = last_ts + 1
                last_ts = ts
                res = landmarker.detect_for_video(mp_image, ts)

            status = "No hand"
            dbg = ""

            if res is not None and res.hand_landmarks:
                lm = res.hand_landmarks[0]
                last_hand_time = now
                lost_frames = 0
                label = res.handedness[0][0].category_name  # 'Left' / 'Right'
                if SWAP_HANDS:
                    label = "Left" if label == "Right" else "Right"


                pts = np.array([(p.x * w, p.y * h, p.z * w) for p in lm])

                for a, b in HAND_CONNECTIONS:
                    cv2.line(frame, tuple(pts[a][:2].astype(int)),
                             tuple(pts[b][:2].astype(int)), (0, 255, 0), 2)
                for p in pts:
                    cv2.circle(frame, tuple(p[:2].astype(int)), 3, (0, 0, 255), -1)

                def d(a, b):
                    return float(np.linalg.norm(pts[a] - pts[b]))

                hand_size = d(WRIST, MID_MCP) + 1e-6

                def extended(tip, pip):
                    return d(tip, WRIST) > d(pip, WRIST) * 1.05

                idx_ext = extended(IDX_TIP, IDX_PIP)
                mid_ext = extended(MID_TIP, MID_PIP)
                ring_ext = extended(RING_TIP, RING_PIP)
                pinky_ext = extended(PINKY_TIP, PINKY_PIP)

                d_idx = sm("idx", d(THUMB_TIP, IDX_TIP) / hand_size)
                d_mid = sm("mid", d(THUMB_TIP, MID_TIP) / hand_size)
                d_ring = sm("ring", d(THUMB_TIP, RING_TIP) / hand_size)
                d_pinky = sm("pinky", d(THUMB_TIP, PINKY_TIP) / hand_size)

                pinch_all = max(d_idx, d_mid, d_ring, d_pinky)

                curl = sm("curl", max(d(IDX_TIP, WRIST), d(MID_TIP, WRIST),
                                      d(RING_TIP, WRIST), d(PINKY_TIP, WRIST)) / hand_size)

                grab_val = min(pinch_all / GRAB_ON, curl / CURL_ON)
                is_grab = grab_state.update(grab_val)
                is_idx = idx_pinch.update(d_idx)
                mid_raw = mid_pinch.update(d_mid)

                mid_wins = d_mid < d_idx - MID_WINS_MARGIN
                is_mid = mid_raw and (mid_wins or not is_idx)
                dbg = f"grab={grab_val:.2f} idx={d_idx:.2f} mid={d_mid:.2f}"


                scroll_raw = (
                    not is_grab and idx_ext and mid_ext
                    and not ring_ext and not pinky_ext
                    and d_idx > 0.4 and d_mid > 0.4
                )
                if is_grab:
                    scroll_active = False
                    scroll_on = 0
                if scroll_raw:
                    scroll_on += 1
                    scroll_off = 0
                    if scroll_on >= SCROLL_ENTER_FRAMES:
                        scroll_active = True
                else:
                    scroll_on = 0
                    scroll_off += 1
                    if scroll_off >= SCROLL_EXIT_FRAMES:
                        scroll_active = False
                is_scroll = scroll_active


                raw_label = label
                if stable_label is None:
                    stable_label = raw_label
                elif raw_label != stable_label and not (is_scroll or is_grab or dragging):
                    label_votes += 1
                    if label_votes >= LABEL_CONFIRM_FRAMES:
                        stable_label = raw_label
                        label_votes = 0
                        mon_override = None
                        cur_x = cur_y = None
                        rel_off = None
                        steady_reset()
                else:
                    label_votes = 0
                label = stable_label
                label_mon = setup.for_label(label)
                mon = mon_override or label_mon


                px_raw, py_raw = pts[MID_MCP][:2]
                px = fx_filter(px_raw / w, now) * w
                py = fy_filter(py_raw / h, now) * h
                a_left, a_top, a_size = area_box()
                fx = (px / w - a_left) / a_size
                fy = (py / h - a_top) / a_size
                nx = float(np.clip(0.5 + (fx - 0.5) * SENSITIVITY, 0, 1))
                ny = float(np.clip(0.5 + (fy - 0.5) * SENSITIVITY, 0, 1))
                tx = mon.x + nx * (mon.width - 1)
                ty = mon.y + ny * (mon.height - 1)
                if cur_x is None:
                    cur_x, cur_y = tx, ty


                want_down = is_grab and not is_scroll
                if want_down and not dragging:
                    if pos_hist:
                        cur_x, cur_y = pos_hist[0]
                        move_cursor(cur_x, cur_y)
                    pyautogui.mouseDown()
                    dragging = True
                    drag_rel_ready = False
                    rel_off = None
                elif not want_down and dragging:
                    pyautogui.mouseUp()
                    dragging = False
                    drag_rel_ready = False

                    rel_off = (cur_x - tx, cur_y - ty)
                    rel_hold_until = now + RELEASE_HOLD

                    m_now = setup.monitor_at(cur_x, cur_y)
                    mon_override = m_now if (m_now is not None and (m_now.x, m_now.y) != (label_mon.x, label_mon.y)) else None
                    if mon_override is not None:
                        mon = mon_override


                if dragging:
                    if not drag_rel_ready:
                        drag_hand0 = (px, py)
                        drag_cur0 = (cur_x, cur_y)
                        drag_rel_ready = True
                    if grab_val > 1.0 + (GRAB_RELEASE - 1.0) * 0.3:

                        drag_hand0 = (px, py)
                        drag_cur0 = (cur_x, cur_y)

                    sx = SENSITIVITY * DRAG_SCALE * (mon.width - 1) / (a_size * w)
                    sy = SENSITIVITY * DRAG_SCALE * (mon.height - 1) / (a_size * h)
                    tx = float(np.clip(drag_cur0[0] + (px - drag_hand0[0]) * sx, setup.vx0, setup.vx1 - 1))
                    ty = float(np.clip(drag_cur0[1] + (py - drag_hand0[1]) * sy, setup.vy0, setup.vy1 - 1))


                if rel_off is not None and not dragging:
                    if now < rel_hold_until:
                        rel_off = (cur_x - tx, cur_y - ty)
                    else:
                        rel_off = (rel_off[0] * RELEASE_BLEND, rel_off[1] * RELEASE_BLEND)
                        if abs(rel_off[0]) < 1.0 and abs(rel_off[1]) < 1.0:
                            rel_off = None
                    if rel_off is not None:
                        tx = float(np.clip(tx + rel_off[0], mon.x, mon.x + mon.width - 1))
                        ty = float(np.clip(ty + rel_off[1], mon.y, mon.y + mon.height - 1))


                tx, ty = dz.apply(tx, ty, TREMOR_DEADZONE * mon.width * (0.25 if dragging else 1.0),
                                  (dragging, mon.x, mon.y))


                if is_idx and not idx_prev:
                    pinch_start = now
                    pinch_skip = False

                    pinch_pos = pos_hist[0] if pos_hist else (cur_x, cur_y)
                    if (last_click_pos is not None
                            and now - last_click_time <= DOUBLE_CLICK_WINDOW
                            and not (is_grab or is_mid or is_scroll)):

                        click_at(last_click_pos[0], last_click_pos[1])
                        cur_x, cur_y = last_click_pos
                        pinch_skip = True
                        last_click_pos = None
                        last_click_time = 0.0
                        flash_text, flash_until = f"{label}: DOUBLE CLICK", now + 0.5
                if is_idx and (is_grab or is_mid or is_scroll or dragging):
                    pinch_skip = True
                if idx_prev and not is_idx:
                    if not pinch_skip and (now - pinch_start) <= CLICK_MAX_TIME:
                        click_at(pinch_pos[0], pinch_pos[1])
                        cur_x, cur_y = pinch_pos
                        last_click_pos = pinch_pos
                        last_click_time = now
                        flash_text, flash_until = f"{label}: CLICK", now + 0.35
                idx_prev = is_idx




                in_dbl = (last_click_pos is not None
                          and now - last_click_time <= DOUBLE_CLICK_WINDOW
                          and math.hypot(tx - last_click_pos[0], ty - last_click_pos[1])
                          <= DOUBLE_CLICK_RELEASE_MOVE)
                freeze_cursor = is_scroll or (not is_grab and (
                    is_mid or is_idx or idx_pinch.pending or mid_pinch.pending or in_dbl))
                if not freeze_cursor:
                    cur_x += (tx - cur_x) * SMOOTH
                    cur_y += (ty - cur_y) * SMOOTH
                    move_cursor(cur_x, cur_y)
                pos_hist.append((cur_x, cur_y))


                if is_scroll:
                    y_now = py / h
                    if scroll_anchor is None:
                        scroll_anchor = y_now
                        scroll_y = y_now
                        scroll_acc = 0.0
                    scroll_y += (y_now - scroll_y) * 0.5
                    disp = scroll_anchor - scroll_y
                    mag = abs(disp) - SCROLL_DEADZONE
                    level = 0.0
                    if mag > 0:
                        level = min(1.0, mag / SCROLL_RANGE)
                        direction = 1 if disp > 0 else -1
                        if SCROLL_INVERT:
                            direction = -direction
                        scroll_acc += direction * (level ** 1.5) * SCROLL_MAX_SPEED
                        amount = int(scroll_acc)
                        if amount != 0:
                            pyautogui.scroll(amount)
                            scroll_acc -= amount
                    else:
                        scroll_acc = 0.0


                    ay = int(scroll_anchor * h)
                    dzv = int(SCROLL_DEADZONE * h)
                    cv2.line(frame, (0, ay), (w, ay), (255, 255, 0), 1)
                    cv2.line(frame, (0, ay - dzv), (w, ay - dzv), (255, 255, 0), 1)
                    cv2.line(frame, (0, ay + dzv), (w, ay + dzv), (255, 255, 0), 1)
                    cv2.circle(frame, (int(px), int(py)), 10, (0, 165, 255), 2)
                    if level > 0:
                        arrow = "UP" if (disp > 0) != SCROLL_INVERT else "DOWN"
                        status = f"{label}: SCROLL {arrow} {int(level * 100)}%"
                    else:
                        status = f"{label}: SCROLL (center)"
                else:
                    scroll_anchor = None
                    scroll_y = None
                    scroll_acc = 0.0


                if is_mid and not mid_prev:
                    mid_start = now
                    rc_pos = pos_hist[0] if pos_hist else (cur_x, cur_y)
                    rc_cancel = False
                if is_mid and (is_grab or is_scroll):
                    rc_cancel = True
                right_clicked = False
                if mid_prev and not is_mid and mid_start and rc_pos is not None:
                    dt = now - mid_start
                    if not rc_cancel and MIN_CLICK_TIME <= dt < MAX_CLICK_TIME:
                        click_at(rc_pos[0], rc_pos[1], "right")
                        cur_x, cur_y = rc_pos
                        right_clicked = True
                mid_prev = is_mid

                if not is_scroll:
                    if right_clicked:
                        status = f"{label}: RIGHT CLICK"
                    elif now < flash_until:
                        status = flash_text
                    elif is_grab:
                        status = f"{label}: GRAB"
                    else:
                        status = f"{label}: MOVE"
            else:


                lost_frames += 1
                if lost_frames > LOST_GRACE_FRAMES:
                    if dragging:
                        pyautogui.mouseUp()
                        dragging = False
                    idx_pinch.reset()
                    mid_pinch.reset()
                    grab_state.reset()
                    mid_prev = False
                    idx_prev = False
                    pinch_skip = True
                    last_click_pos = None
                    dist_ema.clear()
                    pos_hist.clear()
                    scroll_on = scroll_off = 0
                    scroll_active = False
                    scroll_anchor = None
                    scroll_y = None
                    scroll_acc = 0.0
                    stable_label = None
                    label_votes = 0
                    mon_override = None
                    drag_rel_ready = False
                    cur_x = cur_y = None
                    rel_off = None
                    rc_cancel = True
                    steady_reset()

            if paused:
                status, dbg = "STOPPED (press Start)", ""


            sc = max(1.0, DISPLAY_WIDTH / w)
            dw, dh = int(round(w * sc)), int(round(h * sc))
            disp = cv2.resize(frame, (dw, dh), interpolation=cv2.INTER_LINEAR) if sc != 1.0 else frame
            a_left, a_top, a_size = area_box()
            ax0, ay0 = int(a_left * dw), int(a_top * dh)
            ax1, ay1 = int((a_left + a_size) * dw), int((a_top + a_size) * dh)
            cv2.rectangle(disp, (ax0, ay0), (ax1 - 1, ay1 - 1), (0, 255, 0), 2)
            cv2.putText(disp, "cursor area", (ax0 + 6, ay1 - 10), cv2.FONT_HERSHEY_SIMPLEX,
                        0.5, (0, 255, 0), 1)
            cv2.putText(disp, status, (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.9, (0, 255, 255), 2)
            cv2.putText(disp, dbg, (10, 60), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 0), 2)
            canvas = np.full((dh + TOOLBAR_H, dw, 3), 35, np.uint8)
            canvas[:dh] = disp
            ui["buttons"] = draw_toolbar(canvas, dh, paused)
            cv2.imshow(WIN, canvas)
            key = cv2.waitKey(1) & 0xFF
            if key in (ord("q"), 27):
                break
            if key in (ord("s"), ord("S")):
                settings_win.open()


            act, ui["action"] = ui["action"], None
            if act == "Exit":
                break
            elif act == "Settings":
                settings_win.open()
            elif act == "Help":
                settings_win.open("help")
            elif act == "Stop":
                paused = not paused
                if paused:
                    if dragging:
                        pyautogui.mouseUp()
                        dragging = False
                        drag_rel_ready = False
                    lost_frames = LOST_GRACE_FRAMES + 1
                else:
                    last_hand_time = time.time()
                    lost_frames = 0
            if cv2.getWindowProperty(WIN, cv2.WND_PROP_VISIBLE) < 1:
                break
    finally:
        if dragging:
            pyautogui.mouseUp()
        settings_win.close()
        if cap is not None:
            cap.release()
        landmarker.close()
        cv2.destroyAllWindows()


if __name__ == "__main__":
    try:
        main()
    except AppError as e:
        show_message(str(e), "error")
    except Exception:
        import traceback
        err = traceback.format_exc()
        log_path = os.path.join(app_dir(), "hand_mouse_error.log")
        try:
            with open(log_path, "w", encoding="utf-8") as f:
                f.write(err)
        except Exception:
            log_path = None
        show_message('An unexpected error occurred and the application must close.'
                     + (f"\n\nError details were saved to:\n{log_path}" if log_path else ""),
                     "error")
