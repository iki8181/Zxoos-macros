"""Zxoos controller-only macro app for Windows.

Install vgamepad to create the virtual Xbox controller. Its Windows installer
also installs the required ViGEmBus driver.
"""
import configparser
import ctypes
import json
import math
import os
import re
import sys
import threading
import time
import tkinter as tk
import urllib.error
import urllib.request
import webbrowser
from ctypes import wintypes as wt
from tkinter import filedialog, messagebox, ttk

import updater

try:
    import vgamepad as vg
except ImportError:
    vg = None

# ----------------------------------------------------------------- Win32 setup
user32 = ctypes.windll.user32
kernel32 = ctypes.windll.kernel32
gdi32 = ctypes.windll.gdi32
dwmapi = ctypes.windll.dwmapi

user32.SetProcessDPIAware()
ctypes.windll.winmm.timeBeginPeriod(1)
sys.setswitchinterval(0.0005)

user32.GetForegroundWindow.restype = wt.HWND
user32.GetWindowThreadProcessId.argtypes = [wt.HWND, ctypes.POINTER(wt.DWORD)]
user32.GetWindowRect.argtypes = [wt.HWND, ctypes.POINTER(wt.RECT)]
kernel32.OpenProcess.restype = wt.HANDLE
kernel32.OpenProcess.argtypes = [wt.DWORD, wt.BOOL, wt.DWORD]
kernel32.CloseHandle.argtypes = [wt.HANDLE]
kernel32.QueryFullProcessImageNameW.argtypes = [
    wt.HANDLE, wt.DWORD, wt.LPWSTR, ctypes.POINTER(wt.DWORD)]

ROBLOX_EXE = "robloxplayerbeta.exe"
BACKDASH_HOLD_MS = 16

XINPUT_BUTTONS = {
    "DPAD_UP": 0x0001, "DPAD_DOWN": 0x0002,
    "DPAD_LEFT": 0x0004, "DPAD_RIGHT": 0x0008,
    "START": 0x0010, "BACK": 0x0020,
    "L3": 0x0040, "R3": 0x0080,
    "LB": 0x0100, "RB": 0x0200,
    "A": 0x1000, "B": 0x2000, "X": 0x4000, "Y": 0x8000,
}
XINPUT_ALIASES = {
    "r": "X", "e": "Y", "z": "LB", "x": "RB",
    "c": "DPAD_UP", "v": "DPAD_DOWN", "g": "RT",
    "f1": "BACK", "f2": "START", "f3": "L3",
}
XINPUT_OUTPUT_BUTTONS = {
    "A": "XUSB_GAMEPAD_A", "B": "XUSB_GAMEPAD_B",
    "X": "XUSB_GAMEPAD_X", "Y": "XUSB_GAMEPAD_Y",
    "LB": "XUSB_GAMEPAD_LEFT_SHOULDER",
    "RB": "XUSB_GAMEPAD_RIGHT_SHOULDER",
    "L3": "XUSB_GAMEPAD_LEFT_THUMB",
    "R3": "XUSB_GAMEPAD_RIGHT_THUMB",
    "DPAD_UP": "XUSB_GAMEPAD_DPAD_UP",
    "DPAD_DOWN": "XUSB_GAMEPAD_DPAD_DOWN",
    "DPAD_LEFT": "XUSB_GAMEPAD_DPAD_LEFT",
    "DPAD_RIGHT": "XUSB_GAMEPAD_DPAD_RIGHT",
    "START": "XUSB_GAMEPAD_START",
    "BACK": "XUSB_GAMEPAD_BACK",
}
CONTROLLER_OPTIONS = list(XINPUT_OUTPUT_BUTTONS)


class XInputGamepad(ctypes.Structure):
    _fields_ = [
        ("buttons", wt.WORD),
        ("left_trigger", wt.BYTE),
        ("right_trigger", wt.BYTE),
        ("thumb_lx", wt.SHORT),
        ("thumb_ly", wt.SHORT),
        ("thumb_rx", wt.SHORT),
        ("thumb_ry", wt.SHORT),
    ]


class XInputState(ctypes.Structure):
    _fields_ = [("packet_number", wt.DWORD), ("gamepad", XInputGamepad)]


_xinput_library = None


def load_xinput():
    global _xinput_library
    for name in ("xinput1_4", "xinput9_1_0", "xinput1_3"):
        try:
            library = ctypes.WinDLL(name)
            get_state = library.XInputGetState
            get_state.argtypes = [wt.DWORD, ctypes.POINTER(XInputState)]
            get_state.restype = wt.DWORD
            _xinput_library = library
            return get_state
        except (AttributeError, OSError):
            continue
    raise OSError("Windows XInput could not be loaded.")


def normalize_controller_button(value):
    value = str(value).strip()
    return XINPUT_ALIASES.get(value, value.upper())


if vg is None:
    _setup = tk.Tk()
    _setup.withdraw()
    messagebox.showerror(
        "Controller runtime required",
        "Install the controller dependency with:\n\n"
        f'"{sys.executable}" -m pip install -r requirements-controller.txt\n\n'
        "Accept its ViGEmBus driver installation, then restart this app.")
    _setup.destroy()
    raise SystemExit(1)

try:
    xinput_get_state = load_xinput()
except OSError as exc:
    _setup = tk.Tk()
    _setup.withdraw()
    messagebox.showerror(
        "Controller input unavailable",
        "Windows XInput could not start.\n\n"
        f"Details: {exc}")
    _setup.destroy()
    raise SystemExit(1) from exc

virtual_gamepad = None
_pad_lock = threading.RLock()
_pressed_actions = set()
_sent_buttons = set()
_right_stick_x = 0.0
_right_stick_timer = None
_trigger_down = False
_input_lock = threading.Lock()
_held_controller_buttons = set()
_controller_dispatch = {}
_previous_controller_buttons = set()
_controller_slot = None
_virtual_controller_slots = set()
_pending_virtual_slot_baseline = None
controller_hotkey_entries = []


def resource_path(name):
    base = getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(base, name)


APP_ICON = resource_path("circle.ico")
APP_VERSION = "v3.0"
GITHUB_API = "https://api.github.com/repos/iki8181/Zxoos-macros"
GITHUB_RELEASES = "https://github.com/iki8181/Zxoos-macros/releases"
VERSION_PATTERN = re.compile(r"^v?(\d+(?:\.\d+){0,3})$", re.IGNORECASE)


def foreground_roblox():
    """Return HWND jendela Roblox kalau sedang aktif, selain itu None."""
    hwnd = user32.GetForegroundWindow()
    if not hwnd:
        return None
    pid = wt.DWORD()
    user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
    h = kernel32.OpenProcess(0x1000, False, pid.value)  # QUERY_LIMITED_INFORMATION
    if not h:
        return None
    try:
        buf = ctypes.create_unicode_buffer(520)
        size = wt.DWORD(520)
        ok = kernel32.QueryFullProcessImageNameW(h, 0, buf, ctypes.byref(size))
    finally:
        kernel32.CloseHandle(h)
    if ok and os.path.basename(buf.value).lower() == ROBLOX_EXE:
        return hwnd
    return None


# ------------------------------------------------------------- Input helpers
def precise_sleep(ms):
    end = time.perf_counter() + ms / 1000.0
    while time.perf_counter() < end:
        pass


def key_down(k):
    with _pad_lock:
        _pressed_actions.add(k.lower())
        _update_virtual_gamepad()


def key_up(k):
    with _pad_lock:
        _pressed_actions.discard(k.lower())
        _update_virtual_gamepad()


def keys_down(keys):
    with _pad_lock:
        _pressed_actions.update(k.lower() for k in keys)
        _update_virtual_gamepad()


def keys_up(keys):
    with _pad_lock:
        _pressed_actions.difference_update(k.lower() for k in keys)
        _update_virtual_gamepad()


def tap(k):
    key_down(k)
    time.sleep(0.035)
    key_up(k)


def _action_button(action):
    mappings = {
        "q": C.get("dash_button", "B"),
        "space": C.get("jump_button", "A"),
        "shift": C.get("shiftlock_button", "R3"),
        "1": "X", "2": "Y", "3": "LB", "4": "RB",
    }
    return mappings.get(action)


def _update_virtual_gamepad():
    if virtual_gamepad is None:
        return
    desired = set()
    stick_x = 0.0
    stick_y = 0.0
    for action in _pressed_actions:
        button_name = _action_button(action)
        if button_name:
            desired.add(button_name)
        if action == "a":
            stick_x = -1.0
        elif action == "d":
            stick_x = 1.0
        elif action == "s":
            stick_y = -1.0
        elif action == "w":
            stick_y = 1.0

    for button_name in desired - _sent_buttons:
        button = getattr(vg.XUSB_BUTTON, XINPUT_OUTPUT_BUTTONS[button_name])
        virtual_gamepad.press_button(button=button)
    for button_name in _sent_buttons - desired:
        button = getattr(vg.XUSB_BUTTON, XINPUT_OUTPUT_BUTTONS[button_name])
        virtual_gamepad.release_button(button=button)
    _sent_buttons.clear()
    _sent_buttons.update(desired)

    virtual_gamepad.left_joystick_float(
        x_value_float=stick_x, y_value_float=stick_y)
    virtual_gamepad.right_joystick_float(
        x_value_float=_right_stick_x, y_value_float=0.0)
    virtual_gamepad.right_trigger_float(
        value_float=1.0 if _trigger_down else 0.0)
    virtual_gamepad.update()


def mouse_move(dx):
    global _right_stick_x, _right_stick_timer
    with _pad_lock:
        _right_stick_x = max(-1.0, min(1.0, float(dx) / 240.0))
        if _right_stick_timer:
            _right_stick_timer.cancel()

        def recenter():
            global _right_stick_x, _right_stick_timer
            with _pad_lock:
                _right_stick_x = 0.0
                _right_stick_timer = None
                _update_virtual_gamepad()

        _right_stick_timer = threading.Timer(0.035, recenter)
        _right_stick_timer.daemon = True
        _right_stick_timer.start()
        _update_virtual_gamepad()


def m1(down):
    global _trigger_down
    with _pad_lock:
        _trigger_down = bool(down)
        _update_virtual_gamepad()


# ------------------------------------------------------------------- State
macros_enabled = True
rgc_running = False
alive = True
ready = False
C = {}          # snapshot config (dibaca thread macro, tanpa menyentuh tkinter)
K = {}          # konstanta hasil kalkulasi sensitivitas
panel_h = 120
busy_count = 0  # jumlah macro yang sedang berjalan
busy_lock = threading.Lock()

# ------------------------------------------------------------------- Tema
cSide = "#08111F"
cBG = "#0A1423"
cCard = "#111F32"
cLine = "#263A55"
cIn = "#0C192A"
cTxt = "#D5E1F2"
cMut = "#8092AA"
BLUE, MAUVE, PINK = "#5794F2", "#4779CB", "#78AEFF"
GREEN, PEACH, RED = "#72D6B1", "#83B8FF", "#E06D7A"
YELLOW, TEAL = "#A7C8FF", "#69C6D8"
PALETTE = ["#214477", "#3C72BC", "#82B7FF", "#3C72BC"]
cAcc = BLUE
cGrn = GREEN

FONT = ("Segoe UI", 10)
FONT_B = ("Segoe UI", 10, "bold")


def mix(c1, c2, t):
    a = [int(c1[i:i + 2], 16) for i in (1, 3, 5)]
    b = [int(c2[i:i + 2], 16) for i in (1, 3, 5)]
    return "#%02x%02x%02x" % tuple(int(a[i] + (b[i] - a[i]) * t) for i in range(3))


def tween(owner, duration, update):
    token = object()
    owner._tween_token = token
    started = time.perf_counter()

    def tick():
        if getattr(owner, "_tween_token", None) is not token:
            return
        progress = min(1.0, (time.perf_counter() - started) * 1000 / duration)
        eased = 1 - (1 - progress) ** 3
        try:
            update(eased)
        except tk.TclError:
            return
        if progress < 1:
            root.after(16, tick)

    tick()


def palette_at(t):
    seg = (t % 1.0) * len(PALETTE)
    i = int(seg)
    return mix(PALETTE[i % len(PALETTE)], PALETTE[(i + 1) % len(PALETTE)], seg - i)


root = tk.Tk()
root.title("Zxoos Controller")
root.geometry("1100x680")
root.resizable(False, False)
root.configure(bg=cBG)
root.iconbitmap(APP_ICON)
root.update_idletasks()
try:  # title bar gelap + warna caption (Windows 10/11)
    _hw = user32.GetParent(root.winfo_id())
    dwmapi.DwmSetWindowAttribute(_hw, 20, ctypes.byref(ctypes.c_int(1)), 4)
    dwmapi.DwmSetWindowAttribute(_hw, 35, ctypes.byref(ctypes.c_int(0x000A1423)), 4)
except Exception:
    pass

def rrect(cv, x1, y1, x2, y2, r, **kw):
    pts = [x1 + r, y1, x2 - r, y1, x2, y1, x2, y1 + r, x2, y2 - r, x2, y2,
           x2 - r, y2, x1 + r, y2, x1, y2, x1, y2 - r, x1, y1 + r, x1, y1]
    return cv.create_polygon(pts, smooth=True, **kw)


def hover_bind(w, base, hot, skip=lambda: False):
    def transition(target):
        start = w.cget("bg")
        tween(w, 150, lambda t: w.config(bg=mix(start, target, t)))

    w.bind("<Enter>", lambda e: None if skip() else transition(hot))
    w.bind("<Leave>", lambda e: None if skip() else transition(base))


def flat_button(parent, x, y, w, h, text, bg, fg, cmd, hot=None, font=FONT_B):
    b = tk.Label(parent, text=text, bg=bg, fg=fg, font=font, cursor="hand2")
    b.place(x=x, y=y, width=w, height=h)
    hover_bind(b, bg, hot or mix(bg, "#FFFFFF", 0.18))

    def click(e):
        start = b.cget("bg")
        tween(b, 180, lambda t: b.config(bg=mix(
            mix(start, "#FFFFFF", 0.3), start, t)))
        cmd()

    b.bind("<Button-1>", click)
    return b


style = ttk.Style()
style.theme_use("clam")
style.configure("Z.TCombobox", fieldbackground=cIn, background=cLine,
                foreground=cTxt, arrowcolor=PEACH, bordercolor=cLine,
                lightcolor=cLine, darkcolor=cLine, selectbackground=cIn,
                selectforeground=cTxt)
style.map("Z.TCombobox",
          fieldbackground=[("readonly", cIn)],
          foreground=[("readonly", cTxt)],
          selectbackground=[("readonly", cIn)],
          selectforeground=[("readonly", cTxt)],
          bordercolor=[("focus", MAUVE)])
root.option_add("*TCombobox*Listbox.background", cIn)
root.option_add("*TCombobox*Listbox.foreground", cTxt)
root.option_add("*TCombobox*Listbox.selectBackground", MAUVE)
root.option_add("*TCombobox*Listbox.selectForeground", cSide)
root.option_add("*TCombobox*Listbox.font", FONT)


# --------------------------------------------------- Controller button input
class ControllerButtonEntry(tk.Entry):
    """Click the field, then press a physical controller button to bind it."""
    CAPTURE_PROMPT = "PRESS CONTROLLER"

    def __init__(self, master, default, on_change, acc, **kw):
        super().__init__(master, justify="center", bg=cIn, fg=acc,
                         insertbackground=cIn, relief="flat", font=FONT_B,
                         highlightthickness=1, highlightbackground=cLine,
                         highlightcolor=acc, **kw)
        self._v = ""
        self.acc = acc
        self.on_change = on_change
        self.bind("<KeyPress>", self._press)
        self.bind("<Button-1>", self._focus_for_controller)
        self.bind("<FocusIn>", self._show_capture_prompt)
        self.bind("<FocusOut>", self._show_value)
        controller_hotkey_entries.append(self)
        self.set(default)

    def get(self):
        return self._v

    def set(self, v):
        self._v = normalize_controller_button(v) if v else ""
        self._show_value()

    def _show_value(self, _event=None):
        super().delete(0, "end")
        super().insert(0, self._v)

    def _focus_for_controller(self, _event=None):
        self.focus_set()
        return "break"

    def _show_capture_prompt(self, _event=None):
        super().delete(0, "end")
        super().insert(0, self.CAPTURE_PROMPT)

    def _flash(self):
        tween(self, 220, lambda t: self.config(bg=mix(self.acc, cIn, t)))

    def _press(self, e):
        return "break"


# ------------------------------------------------------------ Toggle switch
class Switch(tk.Canvas):
    """Toggle bergaya iOS dengan animasi geser + warna. Punya .var (BooleanVar)."""

    def __init__(self, master, text, acc, command):
        super().__init__(master, width=280, height=28, bg=cCard,
                         highlightthickness=0, bd=0, cursor="hand2")
        self.var = tk.BooleanVar(value=False)
        self.acc = acc
        self.command = command
        self.p = 0.0
        self.track = rrect(self, 1, 4, 45, 24, 5, fill=cLine, outline="")
        self.knob = rrect(self, 0, 0, 14, 14, 3, fill=cMut, outline="")
        self.label = self.create_text(58, 14, text=text, anchor="w", fill=cTxt,
                                      font=FONT_B)
        self._draw(0.0)
        self.bind("<Button-1>", self._click)
        self.var.trace_add("write", lambda *a: self._go())

    def _draw(self, p):
        self.p = p
        self.itemconfig(self.track, fill=mix(cLine, self.acc, p))
        self.itemconfig(self.knob, fill=mix(cMut, "#FFFFFF", p))
        self.itemconfig(self.label, fill=mix(cMut, cTxt, 0.4 + 0.6 * p))
        x = 13 + 20 * p
        x1, y1, x2, y2, radius = x - 7, 7, x + 7, 21, 3
        self.coords(
            self.knob,
            x1 + radius, y1, x2 - radius, y1, x2, y1, x2, y1 + radius,
            x2, y2 - radius, x2, y2, x2 - radius, y2, x1 + radius, y2,
            x1, y2, x1, y2 - radius, x1, y1 + radius, x1, y1)

    def _go(self):
        start = self.p
        target = 1.0 if self.var.get() else 0.0
        tween(self, 180, lambda t: self._draw(start + (target - start) * t))

    def _click(self, e):
        self.var.set(not self.var.get())
        self.command()


# --------------------------------------------------------------- UI helpers
OFF = 210           # koordinat absolut -> koordinat di dalam frame halaman
CONTENT_X = 302
P = None            # frame halaman yang sedang dibangun
ACC = BLUE          # warna aksen section yang sedang dibangun
pages = {}          # frame tempat widget dibangun
page_tops = {}      # widget yang di-raise saat pindah tab
animated_headers = []
YO = 0              # offset Y untuk section di halaman Macros yang bisa di-scroll


def changed(*_):
    """Penerus ke savesettings (didefinisikan di bawah, jadi dipanggil lewat sini)."""
    savesettings()


def put(w, x, y, wd=None, h=None):
    kw = {"x": x - OFF, "y": y + YO}
    if wd:
        kw["width"] = wd
    if h:
        kw["height"] = h
    w.place(**kw)
    w._pi = kw
    return w


def set_vis(w, state):
    if state:
        w.place(**w._pi)
    else:
        w.place_forget()


def card(x, y, w, h):
    cv = tk.Canvas(P, width=w, height=h, bg=cBG, highlightthickness=0, bd=0)
    rrect(cv, 1, 1, w - 1, h - 1, 4, fill=cCard, outline=cLine)
    cv.create_line(20, 2, w - 20, 2, fill=ACC, width=3, capstyle="round")
    return put(cv, x, y, w, h)


def lbl(x, y, t, w=160):
    return put(tk.Label(P, text=t, bg=cCard, fg=cTxt, font=FONT, anchor="w"),
               x, y, w, 28)


def head(t, sub=""):
    put(tk.Label(P, text=t, bg=cBG, fg=ACC, font=("Segoe UI", 16, "bold"),
                 anchor="w"), 220, 14, 720, 36)
    g = tk.Canvas(P, height=3, bg=cBG, highlightthickness=0, bd=0)
    n, wtot = 24, 720
    for i in range(n):
        g.create_rectangle(i * wtot / n, 0, (i + 1) * wtot / n + 1, 3, width=0,
                           fill=mix(ACC, cBG, (i / (n - 1)) ** 0.8))
    put(g, 220, 52, wtot, 3)
    g._head_segments = g.find_all()
    g._head_accent = ACC
    animated_headers.append(g)
    if sub:
        put(tk.Label(P, text=sub, bg=cBG, fg=cMut, font=("Segoe UI", 9),
                     anchor="w"), 220, 58, 720, 22)


def chk(x, y, t):
    return put(Switch(P, t, ACC, changed), x, y, 280, 28)


def edt(x, y, v, num=True):
    var = tk.StringVar(value=v)
    kw = {}
    if num:
        kw = dict(validate="key", validatecommand=(
            root.register(lambda s: s.isdigit() or s == ""), "%P"))
    e = tk.Entry(P, textvariable=var, justify="center", bg=cIn, fg=ACC,
                 insertbackground=ACC, relief="flat", font=FONT_B,
                 disabledbackground=cIn, disabledforeground=cMut,
                 highlightthickness=1, highlightbackground=cLine,
                 highlightcolor=ACC, **kw)
    e.var = var
    var.trace_add("write", lambda *a: savesettings())
    return put(e, x, y, 110, 28)


def hk(x, y, v):
    return put(ControllerButtonEntry(P, v, changed, ACC), x, y, 110, 28)


def ddl(x, y, items, sel):
    var = tk.StringVar(value=items[sel - 1])
    cb = ttk.Combobox(P, textvariable=var, values=items, state="readonly",
                      style="Z.TCombobox", font=FONT, justify="center")
    cb.var = var

    def on_select(event):
        cb.selection_clear()
        savesettings()

    cb.bind("<<ComboboxSelected>>", on_select)
    return put(cb, x, y, 110, 28)


def val(w):
    return w.get() if isinstance(w, ControllerButtonEntry) else w.var.get()


def setv(w, v):
    if isinstance(w, ControllerButtonEntry):
        w.set(str(v))
    else:
        w.var.set(v)


def begin_page(n, yo=0, acc=BLUE):
    global P, YO, ACC
    P = pages[n]
    YO = yo
    ACC = acc


# ------------------------------------------------------------------ Sidebar
side = tk.Frame(root, bg=cSide)
side.place(x=0, y=0, width=126, height=680)
tk.Label(side, text="ZXOOS", bg=cSide, fg=BLUE, font=("Segoe UI", 16, "bold"),
         anchor="w").place(x=12, y=12, width=102, height=30)
tk.Label(side, text="TSB MACRO HUB", bg=cSide, fg=cMut,
         font=("Segoe UI", 7, "bold"), anchor="w").place(x=13, y=42, width=104, height=16)

NAV = [("\u26A1", "Macros", BLUE), ("\u2699", "Settings", MAUVE)]
nav_items = []
current_tab = 0


def make_nav(idx, icon, name, acc):
    n = tk.Label(side, text=f"{icon}  {name}", bg=cSide, fg=cMut, font=FONT_B,
                 anchor="w", cursor="hand2")
    n.place(x=8, y=98 + (idx - 1) * 38, width=110, height=32)
    n.acc = acc
    n.bind("<Button-1>", lambda e: select_tab(idx))
    hover_bind(n, cSide, cCard, skip=lambda: current_tab == idx)
    nav_items.append(n)


for _i, (_ic, _nm, _ac) in enumerate(NAV, start=1):
    make_nav(_i, _ic, _nm, _ac)
navbar = tk.Frame(side, bg=BLUE)
navbar.place(x=2, y=98, width=3, height=32)

subside = tk.Frame(root, bg="#0C1929")
subside.place(x=126, y=0, width=164, height=680)
subhead = tk.Label(subside, text="MACROS", bg="#0C1929", fg=cMut,
                   font=("Segoe UI", 8, "bold"), anchor="w")
subhead.place(x=12, y=14, width=140, height=18)
tk.Frame(subside, bg=cLine).place(x=12, y=34, width=140, height=1)
macro_categories = [
    ("Lethal", 0, 680),
    ("Twist", 680, 680),
    ("Backdash", 1360, 680),
    ("RGC", 2040, 680),
]
macro_category_items = []
current_category = 0
for _index, (_name, _offset, _height) in enumerate(macro_categories):
    _item = tk.Label(subside, text=f" {_name}", bg="#0C1929", fg=cMut,
                     font=FONT, anchor="w", cursor="hand2")
    _item.place(x=8, y=44 + _index * 34, width=148, height=30)
    _item.bind("<Button-1>", lambda e, i=_index: select_macro_category(i))
    macro_category_items.append(_item)
category_bar = tk.Frame(subside, bg=BLUE)
category_bar.place(x=2, y=44, width=3, height=30)
settings_category = tk.Label(subside, text=" General", bg="#0C1929", fg=cMut,
                            font=FONT, anchor="w", cursor="hand2")
settings_category.place(x=8, y=44, width=148, height=30)
settings_category.bind("<Button-1>", lambda e: select_tab(2))

status_accent = tk.Frame(side, bg=GREEN)
status_accent.place(x=12, y=510, width=2, height=20)
status_text = tk.Label(side, text="MACROS ON", bg=cSide, fg=GREEN,
                       font=("Segoe UI", 8, "bold"), anchor="w")
status_text.place(x=22, y=510, width=94, height=20)

# ----------------------------------------------------------- Sub windows
def make_window(w, h, title):
    win = tk.Toplevel(root)
    win.title(title)
    win.iconbitmap(APP_ICON)
    win.configure(bg=cBG)
    win.resizable(False, False)
    x = (user32.GetSystemMetrics(0) - w) // 2
    y = (user32.GetSystemMetrics(1) - h) // 2
    win.geometry(f"{w}x{h}+{x}+{y}")
    win.withdraw()
    win.update_idletasks()
    try:
        hw = user32.GetParent(win.winfo_id())
        dwmapi.DwmSetWindowAttribute(hw, 20, ctypes.byref(ctypes.c_int(1)), 4)
        dwmapi.DwmSetWindowAttribute(hw, 35, ctypes.byref(ctypes.c_int(0x000A1423)), 4)
    except Exception:
        pass
    return win


info = make_window(400, 300, "About")
tk.Label(info, text="ZXOOS", bg=cBG, fg=BLUE,
         font=("Segoe UI", 22, "bold")).place(x=0, y=20, width=400, height=40)
tk.Label(info, text="Controller-only macro hub for Roblox.\nCreated by zxoos.",
         bg=cBG, fg=cTxt, font=FONT, justify="center").place(x=40, y=72, width=320, height=70)

presetGui = make_window(360, 230, "Preset Manager")
tk.Label(presetGui, text="PRESET CONFIG", bg=cBG, fg=MAUVE,
         font=("Segoe UI", 15, "bold")).place(x=0, y=20, width=360, height=34)


def back_to_menu():
    info.withdraw()
    presetGui.withdraw()
    root.deiconify()


def open_about():
    root.withdraw()
    info.deiconify()


def open_preset():
    root.withdraw()
    presetGui.deiconify()


flat_button(info, 120, 160, 160, 38, "DISCORD SERVER", BLUE, cSide,
            lambda: webbrowser.open("https://discord.gg/AEyPMqDCeN"))
flat_button(info, 120, 212, 160, 38, "BACK TO MENU", cCard, cTxt, back_to_menu)
flat_button(presetGui, 50, 70, 260, 36, "SAVE TO FILE", GREEN, cSide,
            lambda: save_preset())
flat_button(presetGui, 50, 120, 260, 36, "LOAD FROM FILE", MAUVE, cSide,
            lambda: load_preset())
flat_button(presetGui, 50, 170, 260, 36, "BACK TO MENU", cCard, cTxt, back_to_menu)
info.protocol("WM_DELETE_WINDOW", back_to_menu)
presetGui.protocol("WM_DELETE_WINDOW", back_to_menu)

preset_button = flat_button(side, 8, 554, 110, 30, "Preset Manager", cCard, MAUVE,
                            open_preset, hot=mix(cCard, MAUVE, 0.22))
about_button = flat_button(side, 8, 596, 110, 30, "About Hub", cCard, BLUE,
                           open_about, hot=mix(cCard, BLUE, 0.22))

# --------------------------------------------------------------------- Pages
PAGE1_H = 2720  # empat bagian dengan satu viewport penuh per bagian

canvas = tk.Canvas(root, bg=cBG, highlightthickness=0, bd=0, yscrollincrement=40)
canvas.place(x=CONTENT_X, y=0, width=780, height=680)
inner = tk.Frame(canvas, bg=cBG)
canvas.create_window(0, 0, window=inner, anchor="nw", width=760, height=PAGE1_H)
canvas.configure(scrollregion=(0, 0, 760, PAGE1_H))
style.configure("Z.Vertical.TScrollbar", background=cLine, troughcolor=cBG,
                bordercolor=cBG, arrowcolor=cMut, lightcolor=cLine, darkcolor=cLine)
scroll = ttk.Scrollbar(root, orient="vertical", command=canvas.yview,
                       style="Z.Vertical.TScrollbar")
canvas.configure(yscrollcommand=scroll.set)
pages[1] = inner
page_tops[1] = canvas

f2 = tk.Frame(root, bg=cBG)
f2.place(x=CONTENT_X, y=0, width=780, height=680)
pages[2] = f2
page_tops[2] = f2


LX, LF, RX, RF = 220, 410, 590, 790

# =============================== MACROS page ===============================
# ---- Section 1: Lethal (biru)
begin_page(1, 0, BLUE)
head("LETHAL", "Controller-triggered combat macros and right-stick flicks")
card(208, 76, 358, 320)
card(578, 76, 358, 270)
lthmacro = chk(LX, 86, "Lethal")
lbl(LX, 131, "Controller button :")
lbl(LX, 173, "Shiftlock Version :")
lbl(LX, 215, "Wait For Flick :")
lbl(LX, 257, "Auto Jump :")
lthtext2 = lbl(LX, 299, "Dash Style :")
lthtext = lbl(LX, 341, "Wait For Flick :")
lthhk = hk(LF, 131, "r")
lthshiftlock = ddl(LF, 173, ["Shiftlock", "Unshiftlock"], 1)
lthsleep = edt(LF, 215, "220")
lthjump = ddl(LF, 257, ["On", "Off"], 1)
lthdashstyle = ddl(LF, 299, ["1", "2"], 1)
lthsleep2 = edt(LF, 341, "200")

lthv2macro = chk(RX, 86, "Lethal Beast")
lbl(RX, 131, "Controller button :")
lbl(RX, 173, "Wait For Flick :")
lbl(RX, 215, "Auto Jump :")
lbl(RX, 257, "Dash Style :")
lthv2text = lbl(RX, 299, "Wait For Flick :")
lthv2hk = hk(RF, 131, "r")
lthv2sleep = edt(RF, 173, "190")
lthv2jump = ddl(RF, 215, ["On", "Off"], 1)
lthv2dashstyle = ddl(RF, 257, ["1", "2"], 1)
lthv2sleep2 = edt(RF, 299, "75")

# ---- Section 2: Twist (ungu)
begin_page(1, 680, MAUVE)
head("TWIST", "Controller-triggered right-stick flicks")
card(208, 76, 358, 262)
card(578, 76, 358, 222)
twistv1macro = chk(LX, 86, "Twist V1")
lbl(LX, 131, "Controller button :")
lbl(LX, 173, "Wait For Flick :")
lbl(LX, 215, "Wait For 2nd Flick :")
lbl(LX, 257, "Dash Style :")
twistv1text = lbl(LX, 299, "Wait For Flick :")
twistv1hk = hk(LF, 131, "e")
twistv1sleep = edt(LF, 173, "170")
twistv1sleep2 = edt(LF, 215, "90")
twistv1dashstyle = ddl(LF, 257, ["1", "2"], 1)
twistv1sleep3 = edt(LF, 299, "110")

twistv2macro = chk(RX, 86, "Twist V2")
lbl(RX, 131, "Controller button :")
lbl(RX, 173, "1st Flick Degree :")
lbl(RX, 215, "Wait :")
lbl(RX, 257, "2nd Flick Degree :")
twistv2hk = hk(RF, 131, "e")
twistv2first = edt(RF, 173, "-60", False)
twistv2sleep = edt(RF, 215, "190")
twistv2second = edt(RF, 257, "86")

# ---- Section 3: Backdash (hijau)
begin_page(1, 1360, GREEN)
head("BACKDASH CANCEL", "Hold skill + left-stick back + dash together for 16 ms")
bdSet = []


def bd_cell(x, y, n, hkdef, skilldef):
    card(x - 12, y - 8, 358, 120)
    cb = chk(x, y, f"Backdash + {n}")
    lbl(x, y + 36, "Controller :", 90)
    hkc = hk(x + 100, y + 36, hkdef)
    lbl(x, y + 74, "Skill slot :", 90)
    skc = ddl(x + 100, y + 74, ["1", "2", "3", "4"], int(skilldef))
    bdSet.append({"macro": cb, "hk": hkc, "skill": skc})


bd_cell(220, 86, 1, "z", "1")
bd_cell(590, 86, 2, "x", "2")
bd_cell(220, 226, 3, "c", "3")
bd_cell(590, 226, 4, "v", "4")

# ---- Section 4: RGC (peach)
begin_page(1, 2040, PEACH)
head("RGC MACRO", "Hold a controller button to spam dash and direction")
card(208, 76, 358, 230)
card(578, 76, 358, 230)
rgcmacro = chk(LX, 86, "RGC")
lbl(LX, 131, "Controller (hold) :")
lbl(LX, 173, "Dash Direction :")
lbl(LX, 215, "Spam Delay (ms) :")
lbl(LX, 257, "Hold RT :")
rgchk = hk(LF, 131, "g")
rgcdash = ddl(LF, 173, ["Right", "Left"], 1)
rgcdelay = edt(LF, 215, "10")
rgchold = ddl(LF, 267, ["On", "Off"], 1)
put(tk.Label(P, text="HOW IT WORKS", bg=cCard, fg=PEACH, font=FONT_B, anchor="w"),
    RX, 86, 330, 28)
put(tk.Label(P, bg=cCard, fg=cTxt, font=("Segoe UI", 9), anchor="nw",
             justify="left", wraplength=330,
             text="1. Hold the assigned controller button.\n"
                  "2. The virtual pad holds left-stick direction and taps dash.\n"
                  "3. Right trigger is held if enabled.\n4. Release to stop."),
    RX, 121, 330, 170)

# ============================== SETTINGS page ==============================
begin_page(2, 0, MAUVE)
head("SETTINGS", "Controller bindings and virtual output")
card(208, 76, 358, 260)
card(578, 76, 358, 260)
lbl(LX, 86, "Roblox Sensitivity :")
lbl(LX, 131, "Exit button :")
lbl(LX, 176, "Macro toggle button :")
lbl(LX, 221, "Hide menu button :")
lbl(LX, 266, "Panel Opacity (max 255) :")
robloxsensivity = edt(LF, 86, "0.4", False)
exithk = hk(LF, 131, "f1")
togglehk = hk(LF, 176, "f2")
menutogglehk = hk(LF, 221, "f3")
hkmenuopacity = edt(LF, 266, "220")
hotkeypanel = chk(RX, 86, "Floating Panel")
cordcheck = chk(RX, 131, "Roblox Auto-Sync")
put(tk.Label(P, bg=cCard, fg=cMut, font=("Segoe UI", 9), anchor="nw",
             justify="left", wraplength=330,
             text="Auto-Sync makes the floating panel follow the Roblox window "
                  "position and hide when Roblox is not active. Click a button "
                  "binding, then press the controller button to assign it."),
    RX, 176, 330, 50)

card(208, 354, 728, 92)
put(tk.Label(P, text="VIRTUAL CONTROLLER OUTPUT", bg=cCard, fg=MAUVE,
             font=FONT_B, anchor="w"), 220, 360, 300, 22)
controller_status_label = put(
    tk.Label(P, text="INPUT: searching...", bg=cCard, fg=cMut,
             font=("Segoe UI", 9), anchor="e"),
    700, 360, 220, 22)
lbl(220, 387, "Dash", 52)
dash_button = ddl(272, 387, CONTROLLER_OPTIONS,
                  CONTROLLER_OPTIONS.index("B") + 1)
lbl(442, 387, "Jump", 52)
jump_button = ddl(494, 387, CONTROLLER_OPTIONS,
                  CONTROLLER_OPTIONS.index("A") + 1)
lbl(664, 387, "Shiftlock", 72)
shiftlock_button = ddl(736, 387, CONTROLLER_OPTIONS,
                       CONTROLLER_OPTIONS.index("R3") + 1)
put(tk.Label(P, text="Skill slots 1-4 output as X / Y / LB / RB; camera flicks use right stick.",
             bg=cCard, fg=cMut, font=("Segoe UI", 8), anchor="w"),
    220, 419, 700, 18)


# ------------------------------------------------------------ Floating panel
panel = tk.Toplevel(root)
panel.overrideredirect(True)
panel.attributes("-topmost", True)
panel.configure(bg=cSide)
panel.withdraw()
pn_status = None
panel_flags_set = False
panel_last_h = 0


def pretty_key(k):
    return k.upper()


def update_panel():
    global panel_h, pn_status
    for w in panel.winfo_children():
        w.destroy()

    def L(text, x, y, w, h, fg, font, bg=cSide, anchor="w"):
        lb = tk.Label(panel, text=text, bg=bg, fg=fg, font=font, anchor=anchor)
        lb.place(x=x, y=y, width=w, height=h)
        return lb

    bar = tk.Canvas(panel, width=210, height=3, bg=cSide, highlightthickness=0, bd=0)
    bar.place(x=0, y=0)
    for i in range(30):
        bar.create_rectangle(i * 7, 0, i * 7 + 8, 3, width=0,
                             fill=palette_at(i / 30 * 0.6))
    L("Zxoos", 14, 11, 90, 22, "#FFFFFF", ("Segoe UI", 11, "bold"))
    pn_status = L("", 100, 11, 96, 22, GREEN, ("Segoe UI", 8, "bold"), anchor="e")
    tk.Frame(panel, bg=cLine).place(x=14, y=38, width=182, height=1)

    items = [
        (lthmacro, "Lethal V1", lthhk, BLUE),
        (lthv2macro, "Lethal V2", lthv2hk, BLUE),
        (twistv1macro, "Twist V1", twistv1hk, MAUVE),
        (twistv2macro, "Twist V2", twistv2hk, MAUVE),
        (bdSet[0]["macro"], "Backdash Slot 1", bdSet[0]["hk"], GREEN),
        (bdSet[1]["macro"], "Backdash Slot 2", bdSet[1]["hk"], GREEN),
        (bdSet[2]["macro"], "Backdash Slot 3", bdSet[2]["hk"], GREEN),
        (bdSet[3]["macro"], "Backdash Slot 4", bdSet[3]["hk"], GREEN),
        (rgcmacro, "RGC", rgchk, PEACH),
    ]
    y, cnt = 46, 0
    for on, name, h_, col in items:
        if val(on):
            cnt += 1
            L(name, 14, y, 112, 20, cTxt, ("Segoe UI", 9))
            L(pretty_key(val(h_)), 130, y + 1, 66, 18, col, ("Segoe UI", 8, "bold"),
              bg=mix(cSide, col, 0.16), anchor="center")
            y += 24
    if cnt == 0:
        L("No macro enabled", 14, y, 182, 20, cMut, ("Segoe UI", 9, "italic"))
        y += 26
    tk.Frame(panel, bg=cLine).place(x=14, y=y + 4, width=182, height=1)
    y += 12
    for name, h_ in (("Toggle macros", togglehk), ("Exit", exithk)):
        L(name, 14, y, 112, 20, cMut, ("Segoe UI", 9))
        L(pretty_key(val(h_)), 130, y + 1, 66, 18, cMut, ("Segoe UI", 8, "bold"),
          bg=cLine, anchor="center")
        y += 24
    panel_h = y + 8
    st()


def st():
    on = macros_enabled
    if pn_status is not None:
        try:
            pn_status.config(text="ENABLED" if on else "DISABLED",
                             fg=GREEN if on else RED)
        except tk.TclError:
            pass
    col = GREEN if on else RED
    status_text.config(text="MACROS ON" if on else "MACROS OFF", fg=col)
    status_accent.config(bg=col)


def show_panel():
    global panel_flags_set, panel_last_h
    if not C.get("panel"):
        panel.withdraw()
        return
    if C.get("cord"):
        hwnd = foreground_roblox()
        if not hwnd:
            panel.withdraw()
            return
        r = wt.RECT()
        user32.GetWindowRect(hwnd, ctypes.byref(r))
        px, py = r.left + 14, r.bottom - panel_h - 14
    else:
        px, py = 14, user32.GetSystemMetrics(1) - panel_h - 80
    panel.geometry(f"210x{panel_h}+{px}+{py}")
    if panel.state() == "withdrawn":
        panel.deiconify()
    panel.update_idletasks()
    ph = user32.GetParent(panel.winfo_id()) or panel.winfo_id()
    if not panel_flags_set:
        ex = user32.GetWindowLongW(ph, -20)
        # LAYERED | TRANSPARENT (click-through) | TOOLWINDOW | NOACTIVATE
        user32.SetWindowLongW(ph, -20, ex | 0x80000 | 0x20 | 0x80 | 0x08000000)
        panel_flags_set = True
    if panel_last_h != panel_h:
        rgn = gdi32.CreateRoundRectRgn(0, 0, 211, panel_h + 1, 14, 14)
        user32.SetWindowRgn(ph, rgn, True)
        panel_last_h = panel_h
    apply_opacity()


def apply_opacity():
    try:
        v = min(255, max(30, int(C.get("opacity", 220))))
    except Exception:
        v = 220
    panel.attributes("-alpha", v / 255)


panel_job = None


def panel_tick():
    global panel_job
    show_panel()
    panel_job = root.after(100, panel_tick)


def ui_animation_loop():
    try:
        active = alive and root.winfo_viewable()
        if active:
            now = time.perf_counter()
            pulse = 0.5 + 0.5 * math.sin(now * 3.2)
            color = GREEN if macros_enabled else RED
            status_accent.place_configure(width=2 + int(pulse * 2))
            status_accent.config(bg=mix(cBG, color, 0.65 + 0.35 * pulse))
            if animated_headers:
                header = (animated_headers[current_category]
                          if current_tab == 1 else animated_headers[-1])
                segments = header._head_segments
                phase = (now * 0.22) % 1.0
                for index, item in enumerate(segments):
                    distance = abs(((index / len(segments) - phase + 0.5) % 1.0) - 0.5)
                    glow = max(0.0, 1.0 - distance / 0.2)
                    base = mix(header._head_accent, cBG, 0.82)
                    header.itemconfig(item, fill=mix(base, header._head_accent, glow))
    except tk.TclError:
        return
    root.after(35, ui_animation_loop)


# ---------------------------------------------------------------- Macro logic
def calculator():
    global K
    try:
        s = float(C["sens"])
        if s <= 0:
            s = 0.4
    except Exception:
        s = 0.4
    ref2 = 720 / s
    K = {"L1": 360 / s, "L3": 350 / s, "L4": -101.2 / s,
         "S1": -102.4 / s, "S2": 36 / s, "S3": 38.8 / s,
         "T1": -100 / s, "T2": 200 / s, "T3": -110 / s,
         "S4": -12 / s, "S5": 36 / s, "S6": -17.6 / s,
         "deg1": (C["t2_first"] / 360) * ref2,
         "deg2": (C["t2_second"] / 360) * ref2}


def lethal_v1():
    c = C
    if not c["v1_on"] or not macros_enabled:
        return
    jump = c["v1_jump"] == "On"
    if c["v1_shift"] == "Shiftlock":
        tap("q")
        if jump:
            key_down("space")
        if c["v1_style"] == "1":
            precise_sleep(adjusted_delay(c, c["v1_sleep"]))
            mouse_move(K["L1"])
        else:
            precise_sleep(adjusted_delay(c, c["v1_sleep2"]))
            for _ in range(4):
                mouse_move(K["L4"])
                precise_sleep(15)
        if jump:
            key_up("space")
    else:  # Unshiftlock
        tap("q")
        if jump:
            key_down("space")
        precise_sleep(adjusted_delay(c, c["v1_sleep"]))
        tap("shift")
        if jump:
            key_up("space")


def lethal_v2():
    c = C
    if not c["v2_on"] or not macros_enabled:
        return
    jump = c["v2_jump"] == "On"
    if c["v2_style"] == "1":
        mouse_move(K["L1"])
        if jump:
            key_down("space")
        tap("q")
        precise_sleep(adjusted_delay(c, c["v2_sleep"]))
        mouse_move(K["L3"])
        if jump:
            key_up("space")
    else:
        if jump:
            key_down("space")
        tap("q")
        precise_sleep(30)
        for _ in range(10):
            mouse_move(K["S2"])
            precise_sleep(8)
        precise_sleep(adjusted_delay(c, 70))
        for _ in range(10):
            mouse_move(K["S3"])
            precise_sleep(5)
        if jump:
            key_up("space")


def twist_v1():
    c = C
    if not c["t1_on"] or not macros_enabled:
        return
    if c["t1_style"] == "1":
        mouse_move(K["T1"])
        tap("q")
        precise_sleep(adjusted_delay(c, c["t1_sleep"]))
        mouse_move(K["T2"])
        precise_sleep(adjusted_delay(c, c["t1_sleep2"]))
        mouse_move(K["T3"])
    else:
        tap("q")
        precise_sleep(adjusted_delay(c, c["t1_sleep3"]))
        for _ in range(15):
            mouse_move(K["S4"])
            precise_sleep(2)
        precise_sleep(10)
        for _ in range(10):
            mouse_move(K["S5"])
            precise_sleep(8)
        precise_sleep(10)
        for _ in range(10):
            mouse_move(K["S6"])
            precise_sleep(3)


def twist_v2():
    c = C
    if not c["t2_on"] or not macros_enabled:
        return
    mouse_move(K["deg1"])
    tap("q")
    precise_sleep(adjusted_delay(c, c["t2_sleep"]))
    mouse_move(K["deg2"])


def run_bd(n):
    b = C["bd"][n]
    if not b["on"] or not macros_enabled:
        return
    skill = b["skill"] or str(n + 1)
    keys = (skill, "s", "q")
    try:
        keys_down(keys)
        precise_sleep(BACKDASH_HOLD_MS)
    finally:
        keys_up(keys)


def rgc():
    global rgc_running
    c = C
    if not c["rgc_on"] or not macros_enabled or rgc_running:
        return
    key = c["rgc_hk"]
    if not key:
        return
    dash = "d" if c["rgc_dash"] == "Right" else "a"
    delay = max(1, adjusted_delay(c, c["rgc_delay"]))
    hold = c["rgc_hold"] == "On"
    rgc_running = True
    try:
        if hold:
            m1(True)
        key_down(dash)
        while controller_button_pressed(key) and macros_enabled and alive:
            tap("q")
            precise_sleep(delay)
    finally:
        key_up(dash)
        if hold:
            m1(False)
        rgc_running = False


def toggle_macros():
    global macros_enabled
    macros_enabled = not macros_enabled
    root.after(0, st)


def menu_toggle():
    def _do():
        if root.winfo_viewable():
            root.withdraw()
        else:
            info.withdraw()
            presetGui.withdraw()
            root.deiconify()
    root.after(0, _do)


def exit_app():
    global alive, _right_stick_timer, _right_stick_x
    alive = False
    if _right_stick_timer:
        _right_stick_timer.cancel()
        _right_stick_timer = None
    _right_stick_x = 0.0
    if rgc_running:
        for k in ("d", "a"):
            key_up(k)
        m1(False)
    if virtual_gamepad is not None:
        with _pad_lock:
            _pressed_actions.clear()
            _update_virtual_gamepad()
            virtual_gamepad.reset()
            virtual_gamepad.update()
    root.destroy()


# ------------------------------------------------------------ Hotkey register
def make_dispatch(fns, roblox_only):
    def run():
        global busy_count
        with busy_lock:
            busy_count += 1
        try:
            for f in fns:
                f()
        finally:
            with busy_lock:
                busy_count -= 1

    def cb():
        if roblox_only and not foreground_roblox():
            return
        threading.Thread(target=run, daemon=True).start()
    return cb


def apply_hotkeys():
    global _controller_dispatch

    table = [
        (val(exithk), lambda: root.after(0, exit_app), False),
        (val(togglehk), toggle_macros, False),
        (val(menutogglehk), menu_toggle, False),
        (val(lthhk), lethal_v1, True),
        (val(lthv2hk), lethal_v2, True),
        (val(twistv1hk), twist_v1, True),
        (val(twistv2hk), twist_v2, True),
        (val(bdSet[0]["hk"]), lambda: run_bd(0), True),
        (val(bdSet[1]["hk"]), lambda: run_bd(1), True),
        (val(bdSet[2]["hk"]), lambda: run_bd(2), True),
        (val(bdSet[3]["hk"]), lambda: run_bd(3), True),
        (val(rgchk), rgc, True),
    ]
    groups = {}
    for raw_key, fn, rb in table:
        key = normalize_controller_button(raw_key)
        if key:
            groups.setdefault((key, rb), []).append(fn)
    _controller_dispatch = {
        key: make_dispatch(fns, rb)
        for (key, rb), fns in groups.items()
    }


def controller_button_pressed(name):
    with _input_lock:
        return normalize_controller_button(name) in _held_controller_buttons


def controller_poll_loop():
    global _controller_slot, _previous_controller_buttons
    global virtual_gamepad, _pending_virtual_slot_baseline
    if not alive:
        return

    connected = {}
    for slot in range(4):
        state = XInputState()
        if xinput_get_state(slot, ctypes.byref(state)) != 0:
            continue
        bits = state.gamepad.buttons
        active_buttons = {
            name for name, mask in XINPUT_BUTTONS.items() if bits & mask}
        if state.gamepad.left_trigger >= 30:
            active_buttons.add("LT")
        if state.gamepad.right_trigger >= 30:
            active_buttons.add("RT")
        connected[slot] = active_buttons

    if virtual_gamepad is None and connected:
        _pending_virtual_slot_baseline = set(connected)
        try:
            virtual_gamepad = vg.VX360Gamepad()
        except Exception as exc:
            controller_status_label.config(
                text="OUTPUT: virtual controller unavailable", fg=RED)
            messagebox.showerror(
                "Virtual controller unavailable",
                "Install vgamepad and its ViGEmBus driver, then restart this app.\n\n"
                f"Details: {exc}",
                parent=root)
            return

    if _pending_virtual_slot_baseline is not None and virtual_gamepad is not None:
        new_slots = set(connected) - _pending_virtual_slot_baseline
        _virtual_controller_slots.update(new_slots)
        if new_slots:
            _pending_virtual_slot_baseline = None

    physical_slots = [
        slot for slot in connected if slot not in _virtual_controller_slots]
    current_slot = physical_slots[0] if physical_slots else None
    active_buttons = connected.get(current_slot, set())

    newly_pressed = active_buttons - _previous_controller_buttons
    _controller_slot = current_slot
    _previous_controller_buttons = active_buttons
    with _input_lock:
        _held_controller_buttons.clear()
        _held_controller_buttons.update(active_buttons)

    if controller_status_label.winfo_exists():
        controller_status_label.config(
            text=(f"INPUT: Xbox controller {current_slot + 1}"
                  if current_slot is not None else "INPUT: controller disconnected"),
            fg=GREEN if current_slot is not None else cMut)

    captured = False
    if newly_pressed:
        focused = root.focus_get()
        if focused in controller_hotkey_entries:
            button_name = sorted(newly_pressed)[0]
            focused.set(button_name)
            focused._flash()
            focused.on_change()
            root.focus_set()
            captured = True

    if not captured:
        for button_name in newly_pressed:
            callback = _controller_dispatch.get(button_name)
            if callback:
                callback()

    root.after(20, controller_poll_loop)


# ----------------------------------------------------------- Config snapshot
def num(v, default):
    try:
        return int(v)
    except Exception:
        return default


def read_cfg():
    global C
    C = {
        "sens": val(robloxsensivity),
        "opacity": num(val(hkmenuopacity), 220),
        "dash_button": val(dash_button),
        "jump_button": val(jump_button),
        "shiftlock_button": val(shiftlock_button),
        "panel": bool(val(hotkeypanel)),
        "cord": bool(val(cordcheck)),
        "v1_on": bool(val(lthmacro)), "v1_shift": val(lthshiftlock),
        "v1_sleep": num(val(lthsleep), 220), "v1_jump": val(lthjump),
        "v1_style": val(lthdashstyle), "v1_sleep2": num(val(lthsleep2), 200),
        "v2_on": bool(val(lthv2macro)), "v2_sleep": num(val(lthv2sleep), 190),
        "v2_jump": val(lthv2jump), "v2_style": val(lthv2dashstyle),
        "v2_sleep2": num(val(lthv2sleep2), 75),
        "t1_on": bool(val(twistv1macro)), "t1_sleep": num(val(twistv1sleep), 170),
        "t1_sleep2": num(val(twistv1sleep2), 90), "t1_style": val(twistv1dashstyle),
        "t1_sleep3": num(val(twistv1sleep3), 110),
        "t2_on": bool(val(twistv2macro)), "t2_first": num(val(twistv2first), -60),
        "t2_sleep": num(val(twistv2sleep), 190),
        "t2_second": num(val(twistv2second), 86),
        "bd": [{"on": bool(val(b["macro"])), "skill": val(b["skill"]).strip()}
               for b in bdSet],
        "rgc_on": bool(val(rgcmacro)), "rgc_hk": val(rgchk),
        "rgc_dash": val(rgcdash), "rgc_delay": num(val(rgcdelay), 10),
        "rgc_hold": val(rgchold),
    }


def adjusted_delay(c, base_ms):
    return max(0, int(round(base_ms)))


def savesettings(*_):
    global panel_job
    if not ready:
        return
    if panel_job:
        root.after_cancel(panel_job)
        panel_job = None
    read_cfg()
    calculator()
    apply_hotkeys()
    update_panel()

    # --- visibilitas kontrol
    if val(twistv1dashstyle) == "1":
        set_vis(twistv1text, False)
        set_vis(twistv1sleep3, False)
        twistv1sleep.config(state="normal")
        twistv1sleep2.config(state="normal")
    else:
        set_vis(twistv1text, True)
        set_vis(twistv1sleep3, True)
        twistv1sleep.config(state="disabled")
        twistv1sleep2.config(state="disabled")

    if val(lthv2dashstyle) == "1":
        set_vis(lthv2text, False)
        set_vis(lthv2sleep2, False)
        lthv2sleep.config(state="normal")
    else:
        set_vis(lthv2text, True)
        set_vis(lthv2sleep2, True)
        lthv2sleep.config(state="disabled")

    if val(lthshiftlock) == "Shiftlock":
        set_vis(lthtext2, True)
        set_vis(lthdashstyle, True)
        if val(lthdashstyle) == "1":
            set_vis(lthsleep2, False)
            set_vis(lthtext, False)
            lthsleep.config(state="normal")
        else:
            set_vis(lthsleep2, True)
            set_vis(lthtext, True)
            lthsleep.config(state="disabled")
    else:
        for w in (lthsleep2, lthtext, lthdashstyle, lthtext2):
            set_vis(w, False)
        lthsleep.config(state="disabled")

    show_panel()
    if C["panel"] and C["cord"]:
        panel_job = root.after(100, panel_tick)


# ----------------------------------------------------------------- Presets
def save_preset():
    path = filedialog.asksaveasfilename(
        title="Save Preset File", initialfile="config.ini",
        defaultextension=".ini", filetypes=[("INI Config", "*.ini")])
    if not path:
        return
    cp = configparser.ConfigParser()
    cp["General"] = {
        "Sensitivity": val(robloxsensivity), "ExitHK": val(exithk),
        "ToggleHK": val(togglehk), "MenuToggleHK": val(menutogglehk),
        "Opacity": val(hkmenuopacity), "HotkeyPanel": str(int(val(hotkeypanel))),
        "CoordCheck": str(int(val(cordcheck)))}
    cp["Controller"] = {
        "DashButton": val(dash_button),
        "JumpButton": val(jump_button),
        "ShiftlockButton": val(shiftlock_button)}
    cp["Lethal"] = {
        "V1": str(int(val(lthmacro))), "V1HK": val(lthhk),
        "V1Shiftlock": val(lthshiftlock), "V1Sleep": val(lthsleep),
        "V1Jump": val(lthjump), "V1DashStyle": val(lthdashstyle),
        "V1Sleep2": val(lthsleep2),
        "V2": str(int(val(lthv2macro))), "V2HK": val(lthv2hk),
        "V2Sleep": val(lthv2sleep), "V2Jump": val(lthv2jump),
        "V2DashStyle": val(lthv2dashstyle), "V2Sleep2": val(lthv2sleep2)}
    cp["Twist"] = {
        "V1": str(int(val(twistv1macro))), "V1HK": val(twistv1hk),
        "V1Sleep": val(twistv1sleep), "V1Sleep2": val(twistv1sleep2),
        "V1DashStyle": val(twistv1dashstyle), "V1Sleep3": val(twistv1sleep3),
        "V2": str(int(val(twistv2macro))), "V2HK": val(twistv2hk),
        "V2First": val(twistv2first), "V2Sleep": val(twistv2sleep),
        "V2Second": val(twistv2second)}
    cp["Backdash"] = {}
    for i, b in enumerate(bdSet, 1):
        cp["Backdash"][f"Macro{i}"] = str(int(val(b["macro"])))
        cp["Backdash"][f"HK{i}"] = val(b["hk"])
        cp["Backdash"][f"Skill{i}"] = val(b["skill"])
    cp["RGC"] = {
        "Macro": str(int(val(rgcmacro))), "HK": val(rgchk), "Dash": val(rgcdash),
        "Delay": val(rgcdelay), "Hold": val(rgchold)}
    with open(path, "w", encoding="utf-8") as f:
        cp.write(f)
    messagebox.showinfo("Sukses", "Preset berhasil disimpan!", parent=presetGui)


def load_preset():
    path = filedialog.askopenfilename(
        title="Select Preset File", filetypes=[("INI Config", "*.ini")])
    if not path or not os.path.exists(path):
        return
    global ready
    try:
        cp = configparser.ConfigParser()
        cp.read(path, encoding="utf-8")
        g = lambda s, k, d: cp.get(s, k, fallback=d)
        ready = False  # tahan savesettings selama mengisi
        setv(robloxsensivity, g("General", "Sensitivity", "0.4"))
        setv(exithk, g("General", "ExitHK", "f1"))
        setv(togglehk, g("General", "ToggleHK", "f2"))
        setv(menutogglehk, g("General", "MenuToggleHK", "f3"))
        setv(hkmenuopacity, g("General", "Opacity", "220"))
        setv(hotkeypanel, bool(int(g("General", "HotkeyPanel", "0"))))
        setv(cordcheck, bool(int(g("General", "CoordCheck", "0"))))
        if cp.has_section("Controller"):
            setv(dash_button, g("Controller", "DashButton", "B"))
            setv(jump_button, g("Controller", "JumpButton", "A"))
            setv(shiftlock_button, g("Controller", "ShiftlockButton", "R3"))

        setv(lthmacro, bool(int(g("Lethal", "V1", "0"))))
        setv(lthhk, g("Lethal", "V1HK", "r"))
        setv(lthshiftlock, g("Lethal", "V1Shiftlock", "Shiftlock"))
        setv(lthsleep, g("Lethal", "V1Sleep", "220"))
        setv(lthjump, g("Lethal", "V1Jump", "On"))
        setv(lthdashstyle, g("Lethal", "V1DashStyle", "1"))
        setv(lthsleep2, g("Lethal", "V1Sleep2", "200"))

        setv(lthv2macro, bool(int(g("Lethal", "V2", "0"))))
        setv(lthv2hk, g("Lethal", "V2HK", "r"))
        setv(lthv2sleep, g("Lethal", "V2Sleep", "190"))
        setv(lthv2jump, g("Lethal", "V2Jump", "On"))
        setv(lthv2dashstyle, g("Lethal", "V2DashStyle", "1"))
        setv(lthv2sleep2, g("Lethal", "V2Sleep2", "75"))

        setv(twistv1macro, bool(int(g("Twist", "V1", "0"))))
        setv(twistv1hk, g("Twist", "V1HK", "e"))
        setv(twistv1sleep, g("Twist", "V1Sleep", "170"))
        setv(twistv1sleep2, g("Twist", "V1Sleep2", "90"))
        setv(twistv1dashstyle, g("Twist", "V1DashStyle", "1"))
        setv(twistv1sleep3, g("Twist", "V1Sleep3", "110"))
        setv(twistv2macro, bool(int(g("Twist", "V2", "0"))))
        setv(twistv2hk, g("Twist", "V2HK", "e"))
        setv(twistv2first, g("Twist", "V2First", "-60"))
        setv(twistv2sleep, g("Twist", "V2Sleep", "190"))
        setv(twistv2second, g("Twist", "V2Second", "86"))

        for i, b in enumerate(bdSet, 1):
            setv(b["macro"], bool(int(g("Backdash", f"Macro{i}", "0"))))
            setv(b["hk"], g("Backdash", f"HK{i}", "z"))
            setv(b["skill"], g("Backdash", f"Skill{i}", str(i)))

        setv(rgcmacro, bool(int(g("RGC", "Macro", "0"))))
        setv(rgchk, g("RGC", "HK", "g"))
        setv(rgcdash, g("RGC", "Dash", "Right"))
        setv(rgcdelay, g("RGC", "Delay", "10"))
        setv(rgchold, g("RGC", "Hold", "On"))

        ready = True
        savesettings()
        messagebox.showinfo("Sukses", "Preset berhasil dimuat!", parent=presetGui)
    except Exception:
        ready = True
        messagebox.showerror("Error", "Gagal memuat preset! Pastikan file valid.",
                             parent=presetGui)


# --------------------------------------------------------------------- Tabs
def select_tab(i):
    global current_tab
    current_tab = i
    top = page_tops[i]
    top.place_configure(x=CONTENT_X, y=0)
    tk.Misc.tkraise(top)
    version_frame.tkraise()
    scroll.place_forget()
    if i == 1:
        subhead.config(text="MACROS")
        settings_category.place_forget()
        for index, item in enumerate(macro_category_items):
            item.place(x=8, y=44 + index * 34, width=148, height=30)
        offset, height = macro_categories[current_category][1:]
        canvas.place_configure(height=height)
        canvas.yview_moveto(offset / PAGE1_H)
        category_bar.place(x=2, y=44 + current_category * 34, width=3, height=30)
    else:
        subhead.config(text="GENERAL")
        for item in macro_category_items:
            item.place_forget()
        category_bar.place_forget()
        settings_category.place(x=8, y=44, width=148, height=30)
    settings_category.config(bg=cCard if i == 2 else "#0C1929",
                             fg=MAUVE if i == 2 else cMut)
    for index, item in enumerate(macro_category_items):
        active = i == 1 and index == current_category
        item.config(bg=cCard if active else "#0C1929",
                    fg=BLUE if active else cMut)

    # indikator geser + warna menu
    start_y, target_y = navbar.winfo_y(), 98 + (i - 1) * 38
    tween(navbar, 320, lambda t: navbar.place_configure(
        y=round(start_y + (target_y - start_y) * t), width=3))
    old_color = navbar.cget("bg")
    target_color = NAV[i - 1][2]
    tween(navbar, 220, lambda t: navbar.config(
        bg=mix(old_color, target_color, t)))
    for j, n in enumerate(nav_items, start=1):
        selected = j == i
        start_bg, start_fg = n.cget("bg"), n.cget("fg")
        target_bg = mix(cSide, n.acc, 0.12) if selected else cSide
        target_fg = n.acc if selected else cMut
        tween(n, 220, lambda t, n=n, start_bg=start_bg, target_bg=target_bg,
              start_fg=start_fg, target_fg=target_fg:
              n.config(bg=mix(start_bg, target_bg, t),
                       fg=mix(start_fg, target_fg, t)))
    root.focus_set()


def select_macro_category(index):
    global current_category
    current_category = index
    if current_tab != 1:
        select_tab(1)
        return
    offset, height = macro_categories[index][1:]
    canvas.place_configure(height=height)
    canvas.yview_moveto(offset / PAGE1_H)
    start_y, target_y = category_bar.winfo_y(), 44 + index * 34
    tween(category_bar, 300, lambda t: category_bar.place_configure(
        y=round(start_y + (target_y - start_y) * t), width=3))
    for item_index, item in enumerate(macro_category_items):
        active = item_index == index
        start_bg, start_fg = item.cget("bg"), item.cget("fg")
        target_bg = cCard if active else "#0C1929"
        target_fg = BLUE if active else cMut
        tween(item, 220, lambda t, item=item, start_bg=start_bg,
              target_bg=target_bg, start_fg=start_fg, target_fg=target_fg:
              item.config(bg=mix(start_bg, target_bg, t),
                          fg=mix(start_fg, target_fg, t)))


# --------------------------------------------------------- Version indicator
version_frame = tk.Frame(root, bg=cCard, highlightthickness=1,
                         highlightbackground=cLine)
version_frame.place(x=996, y=14, width=92, height=28)
tk.Label(version_frame, text="VERSION", bg=cCard, fg=cMut,
         font=("Segoe UI", 7, "bold"), anchor="w").place(
             x=7, y=6, width=47, height=14)
version_value = tk.Label(version_frame, text=APP_VERSION, bg=cCard, fg=BLUE,
                         font=("Segoe UI", 9, "bold"), anchor="w",
                         cursor="hand2")
version_value.place(x=57, y=5, width=30, height=16)
version_status = "Checking GitHub for the latest version..."
version_tooltip = None
version_tooltip_job = None
latest_update_asset = None
latest_release_url = GITHUB_RELEASES
latest_release_version = None
update_prompted = False
update_in_progress = False


def version_number(tag):
    match = VERSION_PATTERN.fullmatch(tag.strip())
    if match is None:
        return None
    parts = tuple(int(part) for part in match.group(1).split("."))
    return parts + (0,) * (4 - len(parts))


def open_update_or_releases():
    if latest_release_version is None:
        webbrowser.open(latest_release_url)
        return

    current = version_number(APP_VERSION)
    if current is not None and latest_release_version <= current:
        messagebox.showinfo(
            "Zxoos Controller",
            f"You're up to date. Current version: {APP_VERSION}.",
            parent=root)
        return

    if latest_update_asset is not None and getattr(sys, "frozen", False):
        ask_to_update()
    else:
        webbrowser.open(latest_release_url)


def ask_to_update():
    if update_in_progress:
        return
    if messagebox.askyesno(
            "Zxoos Controller update",
            "A newer controller version is available. "
            "Download and install it now?\n"
            "Zxoos Controller will restart after the update is ready.",
            parent=root):
        start_update()


def start_update():
    global update_in_progress, version_status
    if latest_update_asset is None or update_in_progress:
        return
    update_in_progress = True
    version_status = "Downloading controller update..."
    version_value.config(text="...", fg=YELLOW,
                         font=("Segoe UI", 9, "bold"))

    def download():
        try:
            update_path = updater.download_update(
                latest_update_asset, sys.executable)
        except (OSError, urllib.error.URLError, TimeoutError, ValueError) as exc:
            try:
                root.after(0, update_failed, str(exc))
            except tk.TclError:
                pass
            return
        try:
            root.after(0, finish_update, update_path)
        except tk.TclError:
            try:
                os.remove(update_path)
            except FileNotFoundError:
                pass

    threading.Thread(target=download, daemon=True).start()


def update_failed(error):
    global update_in_progress, version_status
    update_in_progress = False
    version_status = f"Update failed: {error}"
    if latest_update_asset is not None:
        version_value.config(text=f"{APP_VERSION} \u2191", fg=YELLOW,
                             font=("Segoe UI", 8, "bold"))
    else:
        version_value.config(text=APP_VERSION, fg=BLUE,
                             font=("Segoe UI", 9, "bold"))
    messagebox.showerror("Zxoos Controller update failed", error, parent=root)


def finish_update(update_path):
    global version_status
    try:
        updater.install_update(update_path, sys.executable)
    except (OSError, ValueError) as exc:
        try:
            os.remove(update_path)
        except FileNotFoundError:
            pass
        update_failed(str(exc))
        return

    version_status = "Update downloaded. Restarting controller..."
    messagebox.showinfo(
        "Zxoos Controller update",
        "The update is ready. Zxoos Controller will close and restart.",
        parent=root)
    exit_app()


def check_latest_version():
    global latest_update_asset, latest_release_url, update_prompted
    latest = None
    release_url = GITHUB_RELEASES
    update_asset = None
    try:
        headers = {"Accept": "application/vnd.github+json",
                   "User-Agent": "Zxoos-Version-Check"}
        try:
            request = urllib.request.Request(
                f"{GITHUB_API}/releases/latest", headers=headers)
            with urllib.request.urlopen(request, timeout=8) as response:
                release = json.loads(response.read().decode("utf-8"))
            tag = release.get("tag_name", "")
            number = version_number(tag)
            if number is not None:
                latest = (number, tag)
                release_url = release.get("html_url", GITHUB_RELEASES)
                if getattr(sys, "frozen", False):
                    update_asset = updater.select_update_asset(
                        release, sys.executable,
                        fallback_name="Zxoos-Controller.exe")
        except urllib.error.HTTPError as exc:
            if exc.code != 404:
                raise

        if latest is None:
            request = urllib.request.Request(
                f"{GITHUB_API}/tags?per_page=100", headers=headers)
            with urllib.request.urlopen(request, timeout=8) as response:
                tags = json.loads(response.read().decode("utf-8"))
            parsed_tags = [
                (number, tag["name"])
                for tag in tags
                if isinstance(tag, dict)
                and isinstance(tag.get("name"), str)
                and (number := version_number(tag["name"])) is not None
            ]
            if parsed_tags:
                latest = max(parsed_tags, key=lambda entry: entry[0])
                release_url = f"{GITHUB_RELEASES}/tag/{latest[1]}"
    except (urllib.error.URLError, TimeoutError, OSError, ValueError,
            json.JSONDecodeError, TypeError) as exc:
        result = (None, GITHUB_RELEASES,
                  f"Version check failed: {exc}")
    else:
        if latest is None:
            result = (None, GITHUB_RELEASES,
                      "No versioned GitHub release or tag found yet.")
        else:
            result = (latest, release_url, f"Latest GitHub version: {latest[1]}")

    def update_badge():
        global version_status, latest_update_asset, latest_release_url
        global latest_release_version
        found, url, status = result
        version_status = status
        latest_release_url = url
        latest_update_asset = update_asset
        latest_release_version = found[0] if found is not None else None
        version_value.unbind("<Button-1>")
        version_value.bind(
            "<Button-1>", lambda event: open_update_or_releases())
        if found is not None:
            current = version_number(APP_VERSION)
            if current is not None and found[0] > current:
                version_value.config(text=f"{APP_VERSION} \u2191",
                                     fg=YELLOW,
                                     font=("Segoe UI", 8, "bold"))
                if latest_update_asset is not None:
                    version_status = (
                        f"Update available: {found[1]}. "
                        "Click to download and install.")
                    if not update_prompted:
                        update_prompted = True
                        root.after(100, ask_to_update)
                else:
                    version_status = (
                        f"Update available: {found[1]}. "
                        "Click to open GitHub releases.")
            else:
                version_value.config(text=APP_VERSION, fg=BLUE,
                                     font=("Segoe UI", 9, "bold"))
        else:
            version_value.config(text=APP_VERSION, fg=BLUE,
                                 font=("Segoe UI", 9, "bold"))

    try:
        root.after(0, update_badge)
    except tk.TclError:
        pass


def show_version_tooltip():
    global version_tooltip, version_tooltip_job
    version_tooltip_job = None
    if version_tooltip is not None or not version_frame.winfo_exists():
        return
    version_tooltip = tk.Toplevel(root)
    version_tooltip.overrideredirect(True)
    version_tooltip.configure(bg=cLine)
    text = tk.Label(version_tooltip, text=version_status, bg=cLine, fg=cTxt,
                    font=("Segoe UI", 8), justify="left", wraplength=300,
                    padx=8, pady=5)
    text.pack()
    version_tooltip.update_idletasks()
    x = min(version_frame.winfo_rootx(),
            user32.GetSystemMetrics(0) - version_tooltip.winfo_reqwidth() - 8)
    y = version_frame.winfo_rooty() + version_frame.winfo_height() + 4
    version_tooltip.geometry(f"+{x}+{y}")


def schedule_version_tooltip(_event=None):
    global version_tooltip_job
    if version_tooltip_job is None:
        version_tooltip_job = root.after(500, show_version_tooltip)


def hide_version_tooltip(_event=None):
    global version_tooltip, version_tooltip_job
    if version_tooltip_job is not None:
        root.after_cancel(version_tooltip_job)
        version_tooltip_job = None
    if version_tooltip is not None:
        version_tooltip.destroy()
        version_tooltip = None


version_frame.bind("<Enter>", schedule_version_tooltip)
version_frame.bind("<Leave>", hide_version_tooltip)
version_value.bind("<Enter>", schedule_version_tooltip)
version_value.bind("<Leave>", hide_version_tooltip)


def refresh_version_periodically():
    if not alive:
        return
    threading.Thread(target=check_latest_version, daemon=True).start()
    root.after(6 * 60 * 60 * 1000, refresh_version_periodically)


# ---------------------------------------------------------------------- Main
hkmenuopacity.var.trace_add(
    "write", lambda *a: (read_cfg(), apply_opacity()) if ready else None)

root.protocol("WM_DELETE_WINDOW", exit_app)
ready = True
savesettings()
select_tab(1)
ui_animation_loop()
root.after(20, controller_poll_loop)
root.after(500, lambda: threading.Thread(
    target=check_latest_version, daemon=True).start())
root.after(6 * 60 * 60 * 1000, refresh_version_periodically)
root.mainloop()