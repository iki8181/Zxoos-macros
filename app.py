"""
Zxoos - port Python dari zxoos.ahk (AutoHotkey v2)  |  GUI modern + animasi

Dependensi:  pip install keyboard
Platform  :  Windows saja (pakai user32/kernel32 via ctypes)
Jalankan  :  python zxoos.py   (jalankan sebagai Administrator kalau Roblox
             berjalan sebagai admin, sama seperti AHK)
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
import tkinter.font as tkfont
import urllib.error
import urllib.request
import webbrowser
from ctypes import wintypes as wt
from tkinter import filedialog, messagebox, ttk

import keyboard
import updater

# ----------------------------------------------------------------- Win32 setup
user32 = ctypes.windll.user32
kernel32 = ctypes.windll.kernel32
gdi32 = ctypes.windll.gdi32
dwmapi = ctypes.windll.dwmapi

user32.SetProcessDPIAware()
ctypes.windll.winmm.timeBeginPeriod(1)

user32.GetForegroundWindow.restype = wt.HWND
user32.GetAsyncKeyState.argtypes = [ctypes.c_int]
user32.GetAsyncKeyState.restype = wt.SHORT
user32.GetWindowThreadProcessId.argtypes = [wt.HWND, ctypes.POINTER(wt.DWORD)]
user32.GetWindowRect.argtypes = [wt.HWND, ctypes.POINTER(wt.RECT)]
kernel32.OpenProcess.restype = wt.HANDLE
kernel32.OpenProcess.argtypes = [wt.DWORD, wt.BOOL, wt.DWORD]
kernel32.CloseHandle.argtypes = [wt.HANDLE]
kernel32.QueryFullProcessImageNameW.argtypes = [
    wt.HANDLE, wt.DWORD, wt.LPWSTR, ctypes.POINTER(wt.DWORD)]

ROBLOX_EXE = "robloxplayerbeta.exe"
BACKDASH_HOLD_MS = 16
PANEL_W = 270
PANEL_H = 300
KEYSTROKE_PANEL_W = 400
KEYSTROKE_PANEL_H = 205


def resource_path(name):
    base = getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(base, name)


APP_ICON = resource_path("circle.ico")
APP_VERSION = "v3.3"
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
    while True:
        remaining = end - time.perf_counter()
        if remaining <= 0:
            return
        if remaining > 0.001:
            time.sleep(remaining - 0.001)


def key_down(k):
    keyboard.press(k)


def key_up(k):
    keyboard.release(k)


def tap(k):
    keyboard.press(k)
    keyboard.release(k)


def mouse_move(dx):
    user32.mouse_event(0x0001, int(dx), 0, 0, 0)  # MOUSEEVENTF_MOVE


def m1(down):
    user32.mouse_event(0x0002 if down else 0x0004, 0, 0, 0, 0)


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
cSub = "#0C1929"
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
current_theme = "Dark-White"

FONT = ("Segoe UI", 10)
FONT_B = ("Segoe UI", 10, "bold")
THEME_NAMES = ["Dark-White", "Blue-Black", "Black", "White"]
THEME_PALETTES = {
    "Dark-White": {
        "cSide": "#101010", "cBG": "#0B0B0B", "cCard": "#1A1A1A",
        "cLine": "#363636", "cIn": "#111111", "cTxt": "#FFFFFF",
        "cMut": "#A0A0A0", "BLUE": "#72A7FF", "MAUVE": "#8585E8",
        "PINK": "#A8C5FF", "GREEN": "#70D6A5", "PEACH": "#A6C4F2",
        "RED": "#E97878", "YELLOW": "#C5D5FF", "TEAL": "#72C6D0",
        "cSub": "#171717",
    },
    "Blue-Black": {
        "cSide": "#071727", "cBG": "#091A2A", "cCard": "#102B43",
        "cLine": "#1F4565", "cIn": "#0D2439", "cTxt": "#E7F2FC",
        "cMut": "#91AFC6", "BLUE": "#54B8FF", "MAUVE": "#3289D1",
        "PINK": "#82C9FF", "GREEN": "#68D6B0", "PEACH": "#79C7F2",
        "RED": "#F07883", "YELLOW": "#A5D8FF", "TEAL": "#53C5D8",
        "cSub": "#0A2034",
    },
    "Black": {
        "cSide": "#050505", "cBG": "#090909", "cCard": "#141414",
        "cLine": "#303030", "cIn": "#101010", "cTxt": "#F4F4F4",
        "cMut": "#A0A0A0", "BLUE": "#8AAEFF", "MAUVE": "#7777CC",
        "PINK": "#A6BFFF", "GREEN": "#70D6A5", "PEACH": "#A0B9E8",
        "RED": "#E97878", "YELLOW": "#C5D5FF", "TEAL": "#72C6D0",
        "cSub": "#101010",
    },
    "White": {
        "cSide": "#E7EBF0", "cBG": "#F5F7FA", "cCard": "#FFFFFF",
        "cLine": "#D5DCE5", "cIn": "#EDF1F5", "cTxt": "#17212B",
        "cMut": "#667485", "BLUE": "#2563EB", "MAUVE": "#5B57C8",
        "PINK": "#5379E8", "GREEN": "#17845E", "PEACH": "#3471C8",
        "RED": "#C83F4D", "YELLOW": "#3D5FC4", "TEAL": "#167C92",
        "cSub": "#E1E6ED",
    },
}


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


def animate_window(window, show, target_alpha=1.0, duration=180,
                   on_complete=None):
    if getattr(window, "_visibility_target", None) is show:
        return
    token = object()
    window._visibility_token = token
    window._visibility_target = show
    if show:
        if window.state() == "withdrawn":
            window.attributes("-alpha", 0.0)
            window.deiconify()
            start_alpha = 0.0
        else:
            start_alpha = float(window.attributes("-alpha"))
        end_alpha = target_alpha
    else:
        if window.state() == "withdrawn":
            if on_complete:
                on_complete()
            return
        start_alpha = float(window.attributes("-alpha"))
        end_alpha = 0.0

    started = time.perf_counter()

    def tick():
        if getattr(window, "_visibility_token", None) is not token:
            return
        progress = min(1.0, (time.perf_counter() - started) * 1000 / duration)
        eased = 1 - (1 - progress) ** 3
        alpha = start_alpha + (end_alpha - start_alpha) * eased
        try:
            window.attributes("-alpha", alpha)
            window._animating_visibility = progress < 1
        except tk.TclError:
            return
        if progress < 1:
            root.after(16, tick)
            return
        if not show:
            window.withdraw()
        if on_complete:
            on_complete()

    tick()


def palette_at(t):
    seg = (t % 1.0) * len(PALETTE)
    i = int(seg)
    return mix(PALETTE[i % len(PALETTE)], PALETTE[(i + 1) % len(PALETTE)], seg - i)


root = tk.Tk()
root.title("Zxoos")
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


_winmm = ctypes.windll.winmm
_mci_send_string = _winmm.mciSendStringW
_mci_send_string.argtypes = [wt.LPCWSTR, wt.LPWSTR, wt.UINT, wt.HWND]
_mci_send_string.restype = wt.UINT
_mci_error_string = _winmm.mciGetErrorStringW
_mci_error_string.argtypes = [wt.UINT, wt.LPWSTR, wt.UINT]
_mci_error_string.restype = wt.BOOL
sound_aliases = set()


def mci_send(command):
    error_code = _mci_send_string(command, None, 0, None)
    if error_code:
        error_text = ctypes.create_unicode_buffer(256)
        if not _mci_error_string(error_code, error_text, len(error_text)):
            error_text.value = f"MCI error {error_code}"
        raise OSError(error_text.value)


def initialize_click_sounds():
    errors = []
    for alias, filename in (
            ("zxoos_ui_click", "ui-click.mp3"),
            ("zxoos_keystroke", "keystroke-click.mp3")):
        path = resource_path(filename)
        if not os.path.isfile(path):
            errors.append(filename + " is missing")
            continue
        try:
            mci_send(f'open "{path}" type mpegvideo alias {alias}')
        except OSError as exc:
            errors.append(f"Could not load {filename}: {exc}")
            continue
        sound_aliases.add(alias)
    return "; ".join(errors) if errors else None


sound_error_shown = False


def report_sound_error(error):
    global sound_error_shown
    if sound_error_shown:
        return
    sound_error_shown = True
    messagebox.showwarning(
        "Audio playback unavailable", str(error), parent=root)


def play_sound(alias):
    if alias in sound_aliases:
        try:
            mci_send(f"seek {alias} to start")
            mci_send(f"play {alias}")
        except OSError as exc:
            sound_aliases.discard(alias)
            report_sound_error(exc)


def play_click_sound():
    play_sound("zxoos_ui_click")


style = ttk.Style()
style.theme_use("clam")

def apply_theme(name):
    global cSide, cSub, cBG, cCard, cLine, cIn, cTxt, cMut
    global BLUE, MAUVE, PINK, GREEN, PEACH, RED, YELLOW, TEAL
    global cAcc, cGrn, ACC, PALETTE, current_theme
    palette = THEME_PALETTES[name]
    color_names = ("cSide", "cSub", "cBG", "cCard", "cLine", "cIn", "cTxt", "cMut",
                   "BLUE", "MAUVE", "PINK", "GREEN", "PEACH", "RED",
                   "YELLOW", "TEAL")
    old_colors = {key: globals()[key] for key in color_names}
    color_map = {old_colors[key]: palette[key] for key in color_names}
    old_palette = PALETTE
    new_palette = [
        mix(palette["BLUE"], palette["cBG"], 0.68),
        mix(palette["BLUE"], palette["cBG"], 0.38),
        palette["PINK"],
        mix(palette["BLUE"], palette["cBG"], 0.38),
    ]
    color_map.update(dict(zip(old_palette, new_palette)))

    for key in color_names:
        globals()[key] = palette[key]
    cAcc, cGrn = BLUE, GREEN
    ACC = color_map.get(ACC, BLUE)
    PALETTE = new_palette
    current_theme = name

    def recolor(widget):
        for option in ("background", "foreground", "highlightbackground",
                       "highlightcolor", "insertbackground",
                       "disabledforeground", "selectbackground",
                       "selectforeground", "activebackground",
                       "activeforeground"):
            if option in widget.keys():
                value = widget.cget(option)
                if value in color_map:
                    widget.configure(**{option: color_map[value]})
        if isinstance(widget, tk.Canvas):
            for item in widget.find_all():
                for option in ("fill", "outline"):
                    try:
                        value = widget.itemcget(item, option)
                    except tk.TclError:
                        continue
                    if value in color_map:
                        widget.itemconfig(item, **{option: color_map[value]})
        for attribute in ("acc", "_head_accent"):
            value = getattr(widget, attribute, None)
            if value in color_map:
                setattr(widget, attribute, color_map[value])
        for child in widget.winfo_children():
            recolor(child)

    recolor(root)
    if "panel" in globals():
        recolor(panel)
    if "keystroke_panel" in globals():
        recolor(keystroke_panel)
    if "macro_canvas" in globals():
        update_panel()
        draw_keystroke_keyboard()
    style.configure("Z.Vertical.TScrollbar", background=cLine, troughcolor=cBG,
                    bordercolor=cBG, arrowcolor=cMut, lightcolor=cLine,
                    darkcolor=cLine)
    try:
        hw = user32.GetParent(root.winfo_id())
        caption_color = int(cBG[5:7] + cBG[3:5] + cBG[1:3], 16)
        dwmapi.DwmSetWindowAttribute(
            hw, 35, ctypes.byref(ctypes.c_int(caption_color)), 4)
    except (OSError, tk.TclError):
        pass


# ------------------------------------------------------------ Hotkey widget
class HotkeyEntry(tk.Entry):
    """Pengganti kontrol Hotkey AHK: klik lalu tekan tombol. Backspace = hapus."""
    MODS = {"Control_L", "Control_R", "Shift_L", "Shift_R", "Alt_L", "Alt_R",
            "Win_L", "Win_R", "Caps_Lock", "Num_Lock", "Meta_L", "Meta_R"}
    ALIAS = {"return": "enter", "prior": "page up", "next": "page down",
             "escape": "esc", "caps_lock": "caps lock"}

    def __init__(self, master, default, on_change, acc, **kw):
        super().__init__(master, justify="center", bg=cIn, fg=acc,
                         insertbackground=cIn, relief="flat", font=FONT_B,
                         highlightthickness=1, highlightbackground=cLine,
                         highlightcolor=acc, **kw)
        self._v = ""
        self._capturing = False
        self.acc = acc
        self.on_change = on_change
        self.bind("<KeyPress>", self._press)
        self.bind("<Button-1>", self._begin_capture)
        self.bind("<FocusOut>", self._cancel_capture)
        self.set(default)

    def get(self):
        return self._v

    def set(self, v):
        self._v = v
        super().delete(0, "end")
        super().insert(0, v.upper())

    def _begin_capture(self, _event=None):
        self._capturing = True
        super().delete(0, "end")
        super().insert(0, "Press key...")
        self.config(fg=YELLOW)
        self.focus_set()
        return "break"

    def _finish_capture(self):
        self._capturing = False
        self.config(fg=self.acc)
        super().delete(0, "end")
        super().insert(0, self._v.upper())
        root.focus_set()

    def _cancel_capture(self, _event=None):
        if self._capturing:
            self._finish_capture()

    def _flash(self):
        tween(self, 220, lambda t: self.config(bg=mix(self.acc, cIn, t)))

    def _press(self, e):
        if not self._capturing:
            return
        ks = e.keysym
        if ks in self.MODS:
            return "break"
        if ks == "Escape":
            self._finish_capture()
            return "break"
        if ks in ("Tab", "BackSpace"):
            if ks == "BackSpace":
                self.set("")
                self._flash()
                self.on_change()
            self._finish_capture()
            return "break"
        else:
            name = self.ALIAS.get(ks.lower(), ks.lower())
            mods = []
            if e.state & 0x4:
                mods.append("ctrl")
            if e.state & 0x8:
                mods.append("alt")
            if e.state & 0x1:
                mods.append("shift")
            self.set("+".join(mods + [name]))
            self._flash()
            self.on_change()
            self._finish_capture()
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


active_dropdown = None


def dismiss_dropdown(event):
    if active_dropdown is None:
        return
    popup = active_dropdown.popup
    if event.widget is active_dropdown:
        return
    if popup is not None and event.widget.winfo_toplevel() == popup:
        return
    active_dropdown.close_menu()


root.bind_all("<Button-1>", dismiss_dropdown, add="+")
root.bind_all("<ButtonPress-1>", lambda _event: play_click_sound(), add="+")


class Dropdown(tk.Canvas):
    def __init__(self, master, items, selected, width=110):
        super().__init__(master, width=width, height=28, bg=cCard,
                         highlightthickness=0, bd=0, cursor="hand2")
        self.items = items
        self.var = tk.StringVar(value=items[selected - 1])
        self.popup = None
        self.width = width
        self.configure(takefocus=True)
        self.var.trace_add("write", lambda *_: self._draw())
        self.bind("<Button-1>", self._toggle)
        self.bind("<KeyPress-Down>", lambda _event: self._move_selection(1))
        self.bind("<KeyPress-Up>", lambda _event: self._move_selection(-1))
        self.bind("<KeyPress-Return>", self._toggle)
        self.bind("<KeyPress-space>", self._toggle)
        self.bind("<KeyPress-Escape>", self._close_from_key)
        self._draw()

    def _draw(self):
        self.delete("all")
        self.configure(bg=cCard)
        rrect(self, 1, 1, self.width - 1, 27, 9, fill=cIn, outline=cLine)
        self.create_text(11, 14, text=self.var.get(), anchor="w",
                         fill=cTxt, font=FONT)
        self.create_line(self.width - 17, 12, self.width - 13, 8,
                         fill=cMut, width=1)
        self.create_line(self.width - 13, 8, self.width - 9, 12,
                         fill=cMut, width=1)
        self.create_line(self.width - 17, 16, self.width - 13, 20,
                         fill=cMut, width=1)
        self.create_line(self.width - 13, 20, self.width - 9, 16,
                         fill=cMut, width=1)

    def get(self):
        return self.var.get()

    def selection_clear(self):
        return None

    def _toggle(self, _event=None):
        global active_dropdown
        self.focus_set()
        if active_dropdown is self:
            self.close_menu()
            return
        if active_dropdown is not None:
            active_dropdown.close_menu()
        self.open_menu()
        active_dropdown = self

    def _move_selection(self, direction):
        index = self.items.index(self.var.get())
        next_index = max(0, min(len(self.items) - 1, index + direction))
        if next_index != index:
            self.var.set(self.items[next_index])
            self.event_generate("<<ComboboxSelected>>")
        return "break"

    def _close_from_key(self, _event=None):
        self.close_menu()
        return "break"

    def open_menu(self):
        self.update_idletasks()
        row_height = 30
        height = len(self.items) * row_height + 8
        x = self.winfo_rootx()
        y = self.winfo_rooty() + self.winfo_height() + 4
        if y + height > self.winfo_screenheight():
            y = self.winfo_rooty() - height - 4

        popup = tk.Toplevel(root)
        popup.overrideredirect(True)
        popup.geometry(f"{self.width}x{height}+{x}+{y}")
        popup.configure(bg=cBG)
        popup.withdraw()
        self.popup = popup
        menu = tk.Canvas(popup, width=self.width, height=height, bg=cBG,
                         highlightthickness=0, bd=0)
        menu.pack(fill="both", expand=True)
        rrect(menu, 1, 1, self.width - 1, height - 1, 10,
              fill=cBG, outline=cLine)
        self.row_shapes = {}
        for index, value in enumerate(self.items):
            y1 = 4 + index * row_height
            tag = f"option-{index}"
            fill = mix(cLine, cTxt, 0.12) if value == self.var.get() else cBG
            shape = rrect(menu, 5, y1, self.width - 5, y1 + row_height - 2, 8,
                          fill=fill, outline="")
            menu.addtag_withtag(tag, shape)
            self.row_shapes[index] = shape
            menu.create_text(11, y1 + row_height / 2 - 1, text=value,
                             anchor="w", fill=cTxt, font=FONT_B, tags=(tag,))
            menu.tag_bind(tag, "<Enter>",
                          lambda _event, i=index: self._hover_option(i, True))
            menu.tag_bind(tag, "<Leave>",
                          lambda _event, i=index: self._hover_option(i, False))
            menu.tag_bind(tag, "<Button-1>",
                          lambda _event, item=value: self._select(item))
        self.menu = menu
        animate_window(popup, True, duration=130)

    def _hover_option(self, index, active):
        if self.popup is None or not self.popup.winfo_exists():
            return
        value = self.items[index]
        if value == self.var.get():
            fill = mix(cLine, cTxt, 0.12)
        else:
            fill = mix(cLine, cTxt, 0.08) if active else cBG
        self.menu.itemconfig(self.row_shapes[index], fill=fill)

    def _select(self, item):
        self.var.set(item)
        self.event_generate("<<ComboboxSelected>>")
        self.close_menu()

    def close_menu(self):
        global active_dropdown
        if self.popup is not None and self.popup.winfo_exists():
            popup = self.popup
            animate_window(popup, False, duration=110,
                           on_complete=popup.destroy)
        self.popup = None
        if active_dropdown is self:
            active_dropdown = None


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
    return put(HotkeyEntry(P, v, changed, ACC), x, y, 110, 28)


def ddl(x, y, items, sel, width=110):
    cb = Dropdown(P, items, sel, width)

    def on_select(_event):
        cb.selection_clear()
        savesettings()

    cb.bind("<<ComboboxSelected>>", on_select)
    return put(cb, x, y, width, 28)


def val(w):
    return w.get() if isinstance(w, HotkeyEntry) else w.var.get()


def setv(w, v):
    if isinstance(w, HotkeyEntry):
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

subside = tk.Frame(root, bg=cSub)
subside.place(x=126, y=0, width=164, height=680)
subhead = tk.Label(subside, text="MACROS", bg=cSub, fg=cMut,
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
    _item = tk.Label(subside, text=f" {_name}", bg=cSub, fg=cMut,
                     font=FONT, anchor="w", cursor="hand2")
    _item.place(x=8, y=44 + _index * 34, width=148, height=30)
    _item.bind("<Button-1>", lambda e, i=_index: select_macro_category(i))
    macro_category_items.append(_item)
category_bar = tk.Frame(subside, bg=BLUE)
category_bar.place(x=2, y=44, width=3, height=30)
settings_category = tk.Label(subside, text=" General", bg=cSub, fg=cMut,
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
tk.Label(info, text="Custom macro hub for Roblox.\n"
         "Macro hotkeys work only while Roblox is focused.\n"
         "No keystrokes are recorded or sent.",
         bg=cBG, fg=cTxt, font=FONT, justify="center").place(x=40, y=72, width=320, height=70)

presetGui = make_window(360, 230, "Preset Manager")
tk.Label(presetGui, text="PRESET CONFIG", bg=cBG, fg=MAUVE,
         font=("Segoe UI", 15, "bold")).place(x=0, y=20, width=360, height=34)


def back_to_menu():
    window = info if info.state() != "withdrawn" else presetGui
    animate_window(
        window, False,
        on_complete=lambda: animate_window(root, True, duration=200))


def open_about():
    animate_window(
        root, False,
        on_complete=lambda: animate_window(info, True, duration=200))


def open_preset():
    animate_window(
        root, False,
        on_complete=lambda: animate_window(presetGui, True, duration=200))


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
head("LETHAL", "Lethal V1 and V2 \u2014 automated combat macros and flicks")
card(208, 76, 358, 320)
card(578, 76, 358, 270)
lthmacro = chk(LX, 86, "Lethal")
lbl(LX, 131, "Hotkey :")
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
lbl(RX, 131, "Hotkey :")
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
head("TWIST", "Twist V1 and V2")
card(208, 76, 358, 262)
card(578, 76, 358, 222)
twistv1macro = chk(LX, 86, "Twist V1")
lbl(LX, 131, "Hotkey :")
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
lbl(RX, 131, "Hotkey :")
lbl(RX, 173, "1st Flick Degree :")
lbl(RX, 215, "Wait :")
lbl(RX, 257, "2nd Flick Degree :")
twistv2hk = hk(RF, 131, "e")
twistv2first = edt(RF, 173, "-60", False)
twistv2sleep = edt(RF, 215, "190")
twistv2second = edt(RF, 257, "86")

# ---- Section 3: Backdash (hijau)
begin_page(1, 1360, GREEN)
head("BACKDASH CANCEL", "Hold Skill Key + S + Q together for 16 ms")
bdSet = []


def bd_cell(x, y, n, hkdef, skilldef):
    card(x - 12, y - 8, 358, 120)
    cb = chk(x, y, f"Backdash + {n}")
    lbl(x, y + 36, "Hotkey :", 90)
    hkc = hk(x + 100, y + 36, hkdef)
    lbl(x, y + 74, "Skill Key :", 90)
    skc = edt(x + 100, y + 74, skilldef, False)
    bdSet.append({"macro": cb, "hk": hkc, "skill": skc})


bd_cell(220, 86, 1, "z", "1")
bd_cell(590, 86, 2, "x", "2")
bd_cell(220, 226, 3, "c", "3")
bd_cell(590, 226, 4, "v", "4")

# ---- Section 4: RGC (peach)
begin_page(1, 2040, PEACH)
head("RGC MACRO", "Spam side dash while holding M1 & direction key")
card(208, 76, 358, 230)
card(578, 76, 358, 230)
rgcmacro = chk(LX, 86, "RGC")
lbl(LX, 131, "Hotkey (hold) :")
lbl(LX, 173, "Dash Direction :")
lbl(LX, 215, "Spam Delay (ms) :")
lbl(LX, 257, "Hold M1 :")
rgchk = hk(LF, 131, "g")
rgcdash = ddl(LF, 173, ["Right", "Left"], 1)
rgcdelay = edt(LF, 215, "10")
rgchold = ddl(LF, 267, ["On", "Off"], 1)
put(tk.Label(P, text="HOW IT WORKS", bg=cCard, fg=PEACH, font=FONT_B, anchor="w"),
    RX, 86, 330, 28)
put(tk.Label(P, bg=cCard, fg=cTxt, font=("Segoe UI", 9), anchor="nw",
             justify="left", wraplength=330,
             text="1. Hold your hotkey.\n2. Macro holds direction key (D/A) and spams Q.\n"
                  "3. M1 is held down if set to On.\n4. Release key to stop."),
    RX, 121, 330, 170)

# ============================== SETTINGS page ==============================
begin_page(2, 0, MAUVE)
head("SETTINGS", "Controls and overlay")
card(208, 76, 358, 260)
card(578, 76, 358, 304)
lbl(LX, 86, "Roblox Sensitivity :")
lbl(LX, 131, "Exit Macro Hotkey :")
lbl(LX, 176, "Macro On/Off Hotkey :")
lbl(LX, 221, "Hide Menu Hotkey :")
lbl(LX, 266, "Panel Opacity (max 255) :")
robloxsensivity = edt(LF, 86, "0.4", False)
exithk = hk(LF, 131, "f1")
togglehk = hk(LF, 176, "f2")
menutogglehk = hk(LF, 221, "f3")
hkmenuopacity = edt(LF, 266, "220")
hotkeypanel = chk(RX, 86, "Macro Overlay")
cordcheck = chk(RX, 131, "Roblox Auto-Sync")
keystroke_overlay = chk(RX, 176, "Keystrokes Overlay")
keystroke_overlay.var.set(True)
put(tk.Label(P, bg=cCard, fg=cMut, font=("Segoe UI", 9), anchor="nw",
             justify="left", wraplength=330,
             text="Overlays are separate resizable windows. Drag a title "
                  "bar to move; turn Auto-Sync off for free placement. "
                  "Keystrokes show while Roblox is focused."),
    RX, 207, 330, 48)
lbl(RX, 266, "Theme :")
theme_selector = ddl(RF, 266, THEME_NAMES, 1, width=128)
theme_selector.bind(
    "<<ComboboxSelected>>",
    lambda _event: apply_theme(theme_selector.get()), add="+")

# ------------------------------------------------------------ Floating panel
panel = tk.Toplevel(root)
panel.title("Zxoos - Macro panel")
panel.attributes("-topmost", True)
panel.configure(bg=cSide)
panel.resizable(True, True)
panel.minsize(220, 230)
panel.geometry(f"{PANEL_W}x{PANEL_H}+14+180")
panel.withdraw()
keystroke_panel = tk.Toplevel(root)
keystroke_panel.title("Zxoos - Keystrokes")
keystroke_panel.attributes("-topmost", True)
keystroke_panel.configure(bg=cSide)
keystroke_panel.resizable(True, True)
keystroke_panel.minsize(300, 150)
keystroke_panel.geometry(
    f"{KEYSTROKE_PANEL_W}x{KEYSTROKE_PANEL_H}+"
    f"{max(0, user32.GetSystemMetrics(0) - KEYSTROKE_PANEL_W - 14)}+180")
keystroke_panel.withdraw()
pn_status = None
macro_canvas = tk.Canvas(
    panel, bg=cSide, highlightthickness=0, bd=0)
macro_canvas.pack(fill="both", expand=True)
KEYSTROKE_KEYS = (
    *"1234567890", *"qwertyuiop", *"asdfghjkl", *"zxcvbnm",
    "space", "lmb", "rmb",
)
KEYSTROKE_VK = {
    **{key: ord(key.upper()) for key in "abcdefghijklmnopqrstuvwxyz"},
    **{key: ord(key) for key in "0123456789"},
    "space": 0x20, "lmb": 0x01, "rmb": 0x02,
}
keystroke_keycaps = {}
keystroke_canvas = tk.Canvas(
    keystroke_panel, bg=cSide, highlightthickness=0, bd=0)
keystroke_canvas.pack(fill="both", expand=True)
keystroke_values = {key: 0.0 for key in KEYSTROKE_KEYS}
keystroke_targets = {key: False for key in KEYSTROKE_KEYS}
keystroke_last_tick = time.perf_counter()
panel_h = PANEL_H
panel_user_geometry = None
keystroke_user_geometry = None

def pretty_key(k):
    return k.upper()


def update_panel():
    global panel_h
    canvas = macro_canvas
    width, height = canvas.winfo_width(), canvas.winfo_height()
    if width < 10 or height < 10:
        return
    panel_h = max(PANEL_H, panel.winfo_height())
    canvas.delete("all")
    scale = min(width / PANEL_W, height / PANEL_H)
    offset_x = (width - PANEL_W * scale) / 2
    offset_y = (height - PANEL_H * scale) / 2

    def L(text, x, y, w, h, fg, font, bg=None, anchor="w"):
        if bg is None:
            bg = cSide
        canvas.create_text(
            offset_x + x * scale, offset_y + (y + h / 2) * scale,
            text=text, fill=fg,
            font=(font[0], max(6, round(font[1] * scale)),
                  *font[2:]),
            anchor=anchor)

    for i in range(32):
        canvas.create_rectangle(
            offset_x + i * PANEL_W / 32 * scale, offset_y,
            offset_x + (i + 1) * PANEL_W / 32 * scale + 1, offset_y + 4 * scale,
            width=0, fill=palette_at(i / 30 * 0.6))
    L("Zxoos", 16, 10, 110, 22, cTxt, ("Segoe UI", 12, "bold"))
    L("MACRO CONTROL", 17, 32, 130, 14, cMut, ("Segoe UI", 7, "bold"))
    status_color = GREEN if macros_enabled else RED
    canvas.create_rectangle(
        offset_x + 174 * scale, offset_y + 12 * scale,
        offset_x + 246 * scale, offset_y + 34 * scale,
        fill=cCard, outline=cLine, width=max(1, scale))
    L("ENABLED" if macros_enabled else "DISABLED", 174, 12, 72, 22,
      status_color, ("Segoe UI", 8, "bold"), anchor="center")
    canvas.create_line(
        offset_x + 260 * scale, offset_y + 12 * scale,
        offset_x + 260 * scale, offset_y + 268 * scale,
        fill=cLine, width=max(1, scale))

    items = [
        (lthmacro, "Lethal V1", lthhk, BLUE),
        (lthv2macro, "Lethal V2", lthv2hk, BLUE),
        (twistv1macro, "Twist V1", twistv1hk, MAUVE),
        (twistv2macro, "Twist V2", twistv2hk, MAUVE),
        (bdSet[0]["macro"], "Backdash 1", bdSet[0]["hk"], GREEN),
        (bdSet[1]["macro"], "Backdash 2", bdSet[1]["hk"], GREEN),
        (bdSet[2]["macro"], "Backdash 3", bdSet[2]["hk"], GREEN),
        (bdSet[3]["macro"], "Backdash 4", bdSet[3]["hk"], GREEN),
        (rgcmacro, "RGC", rgchk, PEACH),
    ]
    enabled_items = []
    for on, name, h_, col in items:
        if val(on):
            enabled_items.append((name, h_, col))

    L("ACTIVE MACROS", 14, 56, 130, 16, cMut, ("Segoe UI", 8, "bold"))
    L(f"{len(enabled_items)} ENABLED", 158, 56, 88, 16,
      cMut, ("Segoe UI", 7, "bold"), anchor="e")

    if enabled_items:
        for index, (name, hotkey, color) in enumerate(enabled_items):
            col, row_index = divmod(index, 5)
            x, y = 14 + col * 122, 78 + row_index * 29
            canvas.create_rectangle(
                offset_x + x * scale, offset_y + y * scale,
                offset_x + (x + 114) * scale, offset_y + (y + 25) * scale,
                fill=cCard, outline=cLine, width=max(1, scale))
            canvas.create_rectangle(
                offset_x + x * scale, offset_y + y * scale,
                offset_x + (x + 3) * scale, offset_y + (y + 25) * scale,
                fill=color, outline=color)
            L(name, x + 8, y, 72, 24, cTxt, ("Segoe UI", 7))
            L(pretty_key(val(hotkey)), x + 81, y + 3, 28, 19, color,
              ("Segoe UI", 7, "bold"), anchor="center")
    else:
        canvas.create_rectangle(
            offset_x + 14 * scale, offset_y + 78 * scale,
            offset_x + 246 * scale, offset_y + 120 * scale,
            fill=cCard, outline=cLine, width=max(1, scale))
        L("No macros enabled", 18, 78, 222, 42, cMut,
          ("Segoe UI", 9), anchor="center")

    canvas.create_line(
        offset_x + 14 * scale, offset_y + 232 * scale,
        offset_x + 246 * scale, offset_y + 232 * scale,
        fill=cLine, width=max(1, scale))
    for title, hotkey, x, width in (
            ("TOGGLE", togglehk, 14, 103), ("EXIT", exithk, 132, 94)):
        L(title, x, 240, 48, 18, cMut, ("Segoe UI", 7, "bold"))
        canvas.create_rectangle(
            offset_x + (x + 49) * scale, offset_y + 238 * scale,
            offset_x + (x + width) * scale, offset_y + 260 * scale,
            fill=cCard, outline=cLine, width=max(1, scale))
        L(pretty_key(val(hotkey)), x + 49, 238, width - 49, 22, cTxt,
          ("Segoe UI", 8, "bold"), anchor="center")

def draw_keystroke_keyboard():
    global keystroke_keycaps
    canvas = keystroke_canvas
    width, height = canvas.winfo_width(), canvas.winfo_height()
    if width < 10 or height < 10:
        return
    canvas.delete("all")
    scale = min(
        width / KEYSTROKE_PANEL_W,
        height / (KEYSTROKE_PANEL_H - 30))
    offset_x = (width - KEYSTROKE_PANEL_W * scale) / 2
    offset_y = (height - (KEYSTROKE_PANEL_H - 30) * scale) / 2
    keystroke_keycaps = {key: [] for key in KEYSTROKE_KEYS}

    def text(x, y, value, color, size=8, anchor="w"):
        canvas.create_text(
            offset_x + x * scale, offset_y + y * scale, text=value,
            fill=color, font=("Segoe UI", max(6, round(size * scale)), "bold"),
            anchor=anchor)

    text(5, 12, "KEYSTROKES", cTxt)
    text(KEYSTROKE_PANEL_W - 5, 12, "ROBLOX ONLY", TEAL, 7, "e")

    def keycap(key, x, y, width=19, label=None):
        value = keystroke_values[key]
        accent = (
            BLUE if key in ("w", "a", "s", "d", "space")
            else PEACH if key in ("lmb", "rmb")
            else MAUVE if key == "q" else TEAL)
        rect = canvas.create_rectangle(
            offset_x + x * scale, offset_y + y * scale,
            offset_x + (x + width) * scale, offset_y + (y + 22) * scale,
            fill=mix(cSub, accent, value * 0.58),
            outline=mix(cLine, accent, value), width=max(1, scale))
        text = canvas.create_text(
            offset_x + (x + width / 2) * scale,
            offset_y + (y + 11) * scale, text=label or key.upper(),
            fill=mix(cMut, cTxt, 0.45 + value * 0.55),
            font=("Segoe UI", max(6, round(7 * scale)), "bold"))
        keystroke_keycaps[key].append((rect, text))

    rows = (
        ("1234567890", 5, 36),
        ("qwertyuiop", 11, 62),
        ("asdfghjkl", 22, 88),
        ("zxcvbnm", 34, 114),
    )
    for keys, start_x, y in rows:
        for index, key in enumerate(keys):
            keycap(key, start_x + index * 22, y)

    keycap("w", 300, 38, 26)
    keycap("a", 271, 65, 26)
    keycap("s", 300, 65, 26)
    keycap("d", 329, 65, 26)
    keycap("space", 271, 94, 84, "SPACE")
    keycap("lmb", 271, 122, 40, "LMB")
    keycap("rmb", 315, 122, 40, "RMB")


macro_canvas.bind("<Configure>", lambda _event: update_panel())
keystroke_canvas.bind(
    "<Configure>", lambda _event: draw_keystroke_keyboard())


def st():
    col = GREEN if macros_enabled else RED
    status_text.config(
        text="MACROS ON" if macros_enabled else "MACROS OFF", fg=col)
    status_accent.config(bg=col)
    if "macro_canvas" in globals():
        update_panel()


def overlay_has_focus():
    focused = user32.GetForegroundWindow()
    for window in (panel, keystroke_panel):
        hwnd = user32.GetParent(window.winfo_id()) or window.winfo_id()
        if focused == hwnd:
            return True
    return False


def place_overlay(window, x, y):
    window.geometry(f"+{max(0, int(x))}+{max(0, int(y))}")


def show_panel():
    global panel_user_geometry, panel_h
    if not C.get("panel"):
        animate_window(panel, False, duration=160)
        return
    panel.update_idletasks()
    width = max(panel.winfo_reqwidth(), panel.winfo_width())
    height = max(panel.winfo_reqheight(), panel.winfo_height())
    panel_h = max(PANEL_H, height)
    if C.get("cord"):
        hwnd = roblox_focused_hwnd
        if not hwnd or user32.GetForegroundWindow() != hwnd:
            if panel.state() != "withdrawn" and overlay_has_focus():
                return
            animate_window(panel, False, duration=160)
            return
        rect = wt.RECT()
        user32.GetWindowRect(hwnd, ctypes.byref(rect))
        px = min(max(0, rect.left + 14),
                 max(0, user32.GetSystemMetrics(0) - width))
        py = min(max(0, rect.bottom - height - 14),
                 max(0, user32.GetSystemMetrics(1) - height))
        place_overlay(panel, px, py)
    elif panel_user_geometry is None:
        px = 14
        py = user32.GetSystemMetrics(1) - height - 80
        place_overlay(panel, px, py)
        panel_user_geometry = (px, max(0, py))
    if panel.state() == "withdrawn" or getattr(
            panel, "_visibility_target", None) is False:
        animate_window(panel, True, target_alpha=panel_opacity(), duration=180)
    elif not getattr(panel, "_animating_visibility", False):
        apply_opacity()


def show_keystroke_panel():
    global keystroke_user_geometry
    if not C.get("keystroke_overlay"):
        animate_window(keystroke_panel, False, duration=160)
        return
    hwnd = roblox_focused_hwnd
    if not hwnd or user32.GetForegroundWindow() != hwnd:
        if (keystroke_panel.state() != "withdrawn"
                and overlay_has_focus()):
            return
        animate_window(keystroke_panel, False, duration=140)
        return

    keystroke_panel.update_idletasks()
    if not keystroke_keycaps:
        draw_keystroke_keyboard()
    if C.get("cord"):
        rect = wt.RECT()
        if not user32.GetWindowRect(hwnd, ctypes.byref(rect)):
            animate_window(keystroke_panel, False, duration=140)
            return
        width = max(
            keystroke_panel.winfo_reqwidth(), keystroke_panel.winfo_width())
        height = max(
            keystroke_panel.winfo_reqheight(), keystroke_panel.winfo_height())
        px = min(max(0, rect.right - width - 14),
                 max(0, user32.GetSystemMetrics(0) - width))
        py = min(max(0, rect.bottom - height - 14),
                 max(0, user32.GetSystemMetrics(1) - height))
        place_overlay(keystroke_panel, px, py)
    elif keystroke_user_geometry is None:
        width = max(
            keystroke_panel.winfo_reqwidth(), keystroke_panel.winfo_width())
        height = max(
            keystroke_panel.winfo_reqheight(), keystroke_panel.winfo_height())
        px = user32.GetSystemMetrics(0) - width - 14
        py = user32.GetSystemMetrics(1) - height - 80
        place_overlay(keystroke_panel, px, py)
        keystroke_user_geometry = (max(0, px), max(0, py))

    if (keystroke_panel.state() == "withdrawn"
            or getattr(keystroke_panel, "_visibility_target", None) is False):
        animate_window(
            keystroke_panel, True, target_alpha=panel_opacity(), duration=160)
    elif not getattr(keystroke_panel, "_animating_visibility", False):
        keystroke_panel.attributes("-alpha", panel_opacity())


def panel_opacity():
    try:
        v = min(255, max(30, int(C.get("opacity", 220))))
    except Exception:
        v = 220
    return v / 255


def apply_opacity():
    if not getattr(panel, "_animating_visibility", False):
        panel.attributes("-alpha", panel_opacity())
    if not getattr(keystroke_panel, "_animating_visibility", False):
        keystroke_panel.attributes("-alpha", panel_opacity())


panel_job = None


def panel_tick():
    global panel_job
    show_panel()
    show_keystroke_panel()
    if C.get("panel") or C.get("keystroke_overlay"):
        panel_job = root.after(150, panel_tick)


def keystroke_animation_loop():
    global keystroke_last_tick
    if not alive:
        return
    try:
        now = time.perf_counter()
        elapsed = min(0.05, now - keystroke_last_tick)
        keystroke_last_tick = now
        focused = (
            roblox_focused_state and roblox_focused_hwnd
            and user32.GetForegroundWindow() == roblox_focused_hwnd
            and C.get("keystroke_overlay")
            and keystroke_panel.state() != "withdrawn"
        )
        for key, virtual_key in KEYSTROKE_VK.items():
            pressed = (
                bool(user32.GetAsyncKeyState(virtual_key) & 0x8000)
                if focused else False)
            if pressed and not keystroke_targets[key]:
                play_sound("zxoos_keystroke")
            keystroke_targets[key] = pressed

        easing = 1 - math.exp(-elapsed / 0.055)
        for key, keycaps in keystroke_keycaps.items():
            target = 1.0 if keystroke_targets[key] else 0.0
            value = keystroke_values[key]
            value += (target - value) * easing
            if abs(target - value) < 0.005:
                value = target
            if value == keystroke_values[key]:
                continue
            keystroke_values[key] = value
            accent = (
                BLUE if key in ("w", "a", "s", "d", "space")
                else PEACH if key in ("lmb", "rmb")
                else MAUVE if key == "q" else TEAL)
            for rect, label in keycaps:
                keystroke_canvas.itemconfig(
                    rect, fill=mix(cSub, accent, value * 0.58),
                    outline=mix(cLine, accent, value))
                keystroke_canvas.itemconfig(
                    label, fill=mix(cMut, cTxt, 0.45 + value * 0.55))
    except tk.TclError:
        return
    root.after(33, keystroke_animation_loop)


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
    root.after(50, ui_animation_loop)


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
    jump_pressed = False
    try:
        if c["v1_shift"] == "Shiftlock":
            tap("q")
            if jump:
                jump_pressed = True
                key_down("space")
            if c["v1_style"] == "1":
                precise_sleep(adjusted_delay(c, c["v1_sleep"]))
                mouse_move(K["L1"])
            else:
                precise_sleep(adjusted_delay(c, c["v1_sleep2"]))
                for _ in range(4):
                    mouse_move(K["L4"])
                    precise_sleep(15)
        else:  # Unshiftlock
            tap("q")
            if jump:
                jump_pressed = True
                key_down("space")
            precise_sleep(adjusted_delay(c, c["v1_sleep"]))
            tap("shift")
    finally:
        if jump_pressed:
            key_up("space")


def lethal_v2():
    c = C
    if not c["v2_on"] or not macros_enabled:
        return
    jump = c["v2_jump"] == "On"
    jump_pressed = False
    try:
        if c["v2_style"] == "1":
            mouse_move(K["L1"])
            if jump:
                jump_pressed = True
                key_down("space")
            tap("q")
            precise_sleep(adjusted_delay(c, c["v2_sleep"]))
            mouse_move(K["L3"])
        else:
            if jump:
                jump_pressed = True
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
    finally:
        if jump_pressed:
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
        for k in keys:
            key_down(k)
        precise_sleep(BACKDASH_HOLD_MS)
    finally:
        for k in keys:
            key_up(k)


def rgc():
    global rgc_running
    c = C
    if not c["rgc_on"] or not macros_enabled or rgc_running:
        return
    key = c["rgc_hk"].split("+")[-1]
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
        while keyboard.is_pressed(key) and macros_enabled and alive:
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
            animate_window(root, False, duration=170)
        else:
            window = info if info.state() != "withdrawn" else presetGui
            if window.state() != "withdrawn":
                animate_window(
                    window, False,
                    on_complete=lambda: animate_window(root, True, duration=200))
            else:
                animate_window(root, True, duration=200)
    root.after(0, _do)


def exit_app():
    global alive
    alive = False
    if rgc_running:
        for k in ("d", "a"):
            try:
                keyboard.release(k)
            except Exception:
                pass
        m1(False)
    try:
        keyboard.unhook_all()
    except Exception:
        pass
    ctypes.windll.winmm.timeEndPeriod(1)
    root.destroy()


# ------------------------------------------------------------ Hotkey register
def remove_hotkeys(handles):
    registration_errors = []
    for kind, handle in handles:
        try:
            if kind == "release":
                keyboard.unhook(handle)
            else:
                keyboard.remove_hotkey(handle)
        except Exception as exc:
            registration_errors.append(f"Could not remove an old hotkey: {exc}")
    handles.clear()
    return registration_errors


def macro_hotkey_table():
    return [
        (val(lthhk), lethal_v1, False),
        (val(lthv2hk), lethal_v2, False),
        (val(twistv1hk), twist_v1, False),
        (val(twistv2hk), twist_v2, False),
        (val(bdSet[0]["hk"]), lambda: run_bd(0), False),
        (val(bdSet[1]["hk"]), lambda: run_bd(1), False),
        (val(bdSet[2]["hk"]), lambda: run_bd(2), False),
        (val(bdSet[3]["hk"]), lambda: run_bd(3), False),
        (val(rgchk), rgc, False),
    ]


def register_hotkey_table(table, handles, roblox_only):
    registration_errors = []
    groups = {}
    for key, fn, allowed_during_update in table:
        if key:
            groups.setdefault(key, []).append((fn, allowed_during_update))
    for key, fns in groups.items():
        main_key = key.rsplit(",", 1)[-1].strip().rsplit("+", 1)[-1].strip()
        release_handle = None
        try:
            callback, release_callback = make_dispatch(fns)
            release_handle = keyboard.on_release_key(
                main_key, release_callback, suppress=False)
            hotkey_handle = keyboard.add_hotkey(
                key, lambda cb=callback: cb(roblox_only), suppress=False)
            handles.extend([
                ("hotkey", hotkey_handle),
                ("release", release_handle),
            ])
        except Exception as exc:
            if release_handle is not None:
                keyboard.unhook(release_handle)
            registration_errors.append(f"{key}: {exc}")
    return registration_errors


hotkey_handles = []
macro_hotkey_handles = []
roblox_focused_state = False
roblox_focused_hwnd = None


def make_dispatch(fns):
    dispatch_lock = threading.Lock()
    pressed_lock = threading.Lock()
    hotkey_is_down = False

    def run():
        global busy_count
        try:
            with busy_lock:
                busy_count += 1
            for f, allowed_during_update in fns:
                if not update_required or allowed_during_update:
                    f()
        finally:
            with busy_lock:
                busy_count -= 1
            dispatch_lock.release()

    def cb(roblox_only=False):
        if roblox_only and not foreground_roblox():
            return
        nonlocal hotkey_is_down
        with pressed_lock:
            if hotkey_is_down:
                return
            hotkey_is_down = True
        if not dispatch_lock.acquire(blocking=False):
            return
        try:
            threading.Thread(target=run, daemon=True).start()
        except RuntimeError:
            dispatch_lock.release()
            raise

    def on_release(_event):
        nonlocal hotkey_is_down
        with pressed_lock:
            hotkey_is_down = False

    return cb, on_release


def apply_hotkeys():
    global roblox_focused_state, roblox_focused_hwnd
    registration_errors = remove_hotkeys(hotkey_handles)
    registration_errors.extend(remove_hotkeys(macro_hotkey_handles))
    for key in KEYSTROKE_KEYS:
        keystroke_targets[key] = False

    control_table = [
        (val(exithk), lambda: root.after(0, exit_app), True),
        (val(togglehk), toggle_macros, False),
        (val(menutogglehk), menu_toggle, False),
    ]
    registration_errors.extend(
        register_hotkey_table(control_table, hotkey_handles, False))
    roblox_focused_hwnd = foreground_roblox()
    roblox_focused_state = bool(roblox_focused_hwnd)
    if roblox_focused_state:
        registration_errors.extend(
            register_hotkey_table(
                macro_hotkey_table(), macro_hotkey_handles, True))

    if registration_errors:
        messagebox.showwarning(
            "Hotkey registration failed",
            "Some hotkeys could not be registered:\n\n"
            + "\n".join(registration_errors),
            parent=root)


def macro_focus_tick():
    global roblox_focused_state, roblox_focused_hwnd
    if not alive:
        return
    roblox_focused_hwnd = foreground_roblox()
    roblox_focused = bool(roblox_focused_hwnd)
    if roblox_focused != roblox_focused_state:
        roblox_focused_state = roblox_focused
        for key in KEYSTROKE_KEYS:
            keystroke_targets[key] = False
        if roblox_focused:
            registration_errors = register_hotkey_table(
                macro_hotkey_table(), macro_hotkey_handles, True)
            if registration_errors:
                messagebox.showwarning(
                    "Hotkey registration failed",
                    "Some macro hotkeys could not be registered:\n\n"
                    + "\n".join(registration_errors),
                    parent=root)
        else:
            registration_errors = remove_hotkeys(macro_hotkey_handles)
            if registration_errors:
                messagebox.showwarning(
                    "Hotkey cleanup failed",
                    "\n".join(registration_errors),
                    parent=root)
    root.after(500, macro_focus_tick)


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
        "panel": bool(val(hotkeypanel)),
        "keystroke_overlay": bool(val(keystroke_overlay)),
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
    st()

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
    show_keystroke_panel()
    if C["panel"] or C["keystroke_overlay"]:
        panel_job = root.after(150, panel_tick)


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
        "KeystrokeOverlay": str(int(val(keystroke_overlay))),
        "CoordCheck": str(int(val(cordcheck)))}
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
        setv(
            keystroke_overlay,
            bool(int(g(
                "General", "KeystrokeOverlay",
                "1"))))
        setv(cordcheck, bool(int(g("General", "CoordCheck", "0"))))

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
macro_scroll_token = None
macro_scroll_target = 0.0


def animate_macro_scroll(target_offset, duration=None):
    global macro_scroll_token, macro_scroll_target
    token = object()
    macro_scroll_token = token
    canvas.update_idletasks()
    start_offset = canvas.yview()[0] * PAGE1_H
    max_offset = max(0, PAGE1_H - canvas.winfo_height())
    target_offset = max(0, min(max_offset, target_offset))
    macro_scroll_target = target_offset
    distance = target_offset - start_offset
    if abs(distance) < 1:
        canvas.yview_moveto(target_offset / PAGE1_H)
        macro_scroll_token = None
        return

    if duration is None:
        duration = min(1100, max(650, abs(distance) * 0.45))
    started = time.perf_counter()

    def tick():
        global macro_scroll_token
        if macro_scroll_token is not token:
            return
        progress = min(1.0, (time.perf_counter() - started) * 1000 / duration)
        eased = progress ** 3 * (progress * (progress * 6 - 15) + 10)
        offset = start_offset + distance * eased
        canvas.yview_moveto(offset / PAGE1_H)
        if progress < 1:
            root.after(16, tick)
        else:
            canvas.yview_moveto(target_offset / PAGE1_H)
            if macro_scroll_token is token:
                macro_scroll_token = None

    tick()


def smooth_mousewheel(event):
    widget = event.widget
    while widget is not None and widget is not canvas:
        widget = widget.master
    if widget is None:
        return
    base = macro_scroll_target
    if macro_scroll_token is None:
        base = canvas.yview()[0] * PAGE1_H
    delta = -(event.delta / 120) * 120
    animate_macro_scroll(base + delta, duration=240)
    return "break"


root.bind_all("<MouseWheel>", smooth_mousewheel, add="+")


def select_tab(i):
    global current_tab
    if i == current_tab:
        return
    current_tab = i
    top = page_tops[i]
    top.place_configure(x=CONTENT_X + 14, y=0)
    tk.Misc.tkraise(top)
    start_x = CONTENT_X + 14
    tween(top, 210, lambda t: top.place_configure(
        x=round(start_x + (CONTENT_X - start_x) * t)))
    version_frame.tkraise()
    scroll.place_forget()
    if i == 1:
        subhead.config(text="MACROS")
        settings_category.place_forget()
        for index, item in enumerate(macro_category_items):
            item.place(x=8, y=44 + index * 34, width=148, height=30)
        offset, height = macro_categories[current_category][1:]
        canvas.place_configure(height=height)
        animate_macro_scroll(offset)
        category_bar.place(x=2, y=44 + current_category * 34, width=3, height=30)
    else:
        subhead.config(text="GENERAL")
        for item in macro_category_items:
            item.place_forget()
        category_bar.place_forget()
        settings_category.place(x=8, y=44, width=148, height=30)
    settings_category.config(bg=cCard if i == 2 else cSub,
                             fg=MAUVE if i == 2 else cMut)
    for index, item in enumerate(macro_category_items):
        active = i == 1 and index == current_category
        item.config(bg=cCard if active else cSub,
                    fg=BLUE if active else cMut)

    # indikator geser + warna menu
    start_y, target_y = navbar.winfo_y(), 98 + (i - 1) * 38
    tween(navbar, 320, lambda t: navbar.place_configure(
        y=round(start_y + (target_y - start_y) * t), width=3))
    old_color = navbar.cget("bg")
    target_color = nav_items[i - 1].acc
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
    animate_macro_scroll(offset)
    start_y, target_y = category_bar.winfo_y(), 44 + index * 34
    tween(category_bar, 300, lambda t: category_bar.place_configure(
        y=round(start_y + (target_y - start_y) * t), width=3))
    for item_index, item in enumerate(macro_category_items):
        active = item_index == index
        start_bg, start_fg = item.cget("bg"), item.cget("fg")
        target_bg = cCard if active else cSub
        target_fg = BLUE if active else cMut
        tween(item, 220, lambda t, item=item, start_bg=start_bg,
              target_bg=target_bg, start_fg=start_fg, target_fg=target_fg:
              item.config(bg=mix(start_bg, target_bg, t),
                          fg=mix(start_fg, target_fg, t)))


# --------------------------------------------------------- Version indicator
version_frame = tk.Frame(root, bg=cCard, highlightthickness=1,
                         highlightbackground=cLine)
version_frame.place(x=972, y=14, width=116, height=28)
tk.Label(version_frame, text="VERSION", bg=cCard, fg=cMut,
         font=("Segoe UI", 7, "bold"), anchor="w").place(
             x=7, y=6, width=47, height=14)
version_value = tk.Label(version_frame, text=APP_VERSION, bg=cCard, fg=BLUE,
                         font=("Segoe UI", 9, "bold"), anchor="center",
                         cursor="hand2")
version_value.place(x=56, y=5, width=54, height=16)
version_status = "Checking GitHub for the latest version..."
version_tooltip = None
version_tooltip_job = None
latest_update_asset = None
latest_release_url = GITHUB_RELEASES
latest_release_version = None
latest_release_tag = None
update_prompted = False
update_in_progress = False
update_required = False


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
            "Zxoos",
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
    if not getattr(sys, "frozen", False):
        messagebox.showwarning(
            "Required Zxoos update",
            f"Version {latest_release_version} is required. "
            "This source version cannot update itself. Download the new "
            "executable from GitHub and reopen Zxoos; this window will stay open.",
            parent=root)
        webbrowser.open(latest_release_url)
        return
    if latest_update_asset is None:
        messagebox.showwarning(
            "Zxoos update unavailable",
            f"Version {latest_release_version} is required, but GitHub has no "
            "downloadable Zxoos executable for this release. Zxoos will stay "
            "open; macros remain disabled until the update is installed. "
            "Add the executable to the GitHub release, then retry.",
            parent=root)
        webbrowser.open(latest_release_url)
        return
    messagebox.showwarning(
        "Required Zxoos update",
        f"Version {latest_release_version} is required. "
        "Zxoos will download and install it now, then restart.",
        parent=root)
    start_update()


def start_update():
    global update_in_progress, version_status
    if latest_update_asset is None or update_in_progress:
        return
    update_in_progress = True
    version_status = "Downloading update..."
    if update_required:
        root.attributes("-disabled", True)
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
    if update_required:
        root.attributes("-disabled", False)
        if messagebox.askretrycancel(
                "Required Zxoos update failed",
                f"The required update could not be installed:\n\n{error}\n\n"
                "Retry the update, or close Zxoos.",
                parent=root):
            start_update()
        else:
            exit_app()
        return
    if latest_update_asset is not None:
        version_value.config(text=f"{APP_VERSION} \u2191", fg=YELLOW,
                             font=("Segoe UI", 8, "bold"))
    else:
        version_value.config(text=APP_VERSION, fg=BLUE,
                             font=("Segoe UI", 9, "bold"))
    messagebox.showerror("Zxoos update failed", error, parent=root)


def finish_update(update_path):
    try:
        updater.install_update(
            update_path, sys.executable, latest_release_tag,
            create_desktop_shortcut=True)
    except (OSError, ValueError) as exc:
        try:
            os.remove(update_path)
        except FileNotFoundError:
            pass
        update_failed(str(exc))
        return

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
                        release, sys.executable)
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
        global latest_release_version, latest_release_tag
        global update_prompted, update_required
        found, url, status = result
        version_status = status
        latest_release_url = url
        latest_update_asset = update_asset
        latest_release_version = found[0] if found is not None else None
        latest_release_tag = found[1] if found is not None else None
        version_value.unbind("<Button-1>")
        version_value.bind("<Button-1>", lambda event: open_update_or_releases())
        if found is not None:
            current = version_number(APP_VERSION)
            if current is not None and found[0] > current:
                update_required = True
                version_value.config(text=f"{APP_VERSION} \u2191",
                                     fg=YELLOW,
                                     font=("Segoe UI", 8, "bold"))
                version_status = (
                    f"Required update: {found[1]}. "
                    "The app must be updated before it can be used.")
                if not update_prompted:
                    update_prompted = True
                    root.after(100, ask_to_update)
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


def show_welcome_intro():
    root.update_idletasks()
    width, height = root.winfo_width(), root.winfo_height()
    x, y = root.winfo_rootx(), root.winfo_rooty()
    intro = tk.Toplevel(root)
    intro.overrideredirect(True)
    intro.attributes("-topmost", True)
    intro.attributes("-alpha", 1.0)
    intro.geometry(f"{width}x{height}+{x}+{y + 18}")
    intro.configure(bg=cBG)

    intro.withdraw()
    root.withdraw()
    intro.deiconify()
    fade_duration = 420

    def fade_out():
        fade_started = time.perf_counter()

        def tick():
            elapsed = (time.perf_counter() - fade_started) * 1000
            amount = min(1.0, elapsed / fade_duration)
            intro.attributes("-alpha", 1 - amount)
            intro.geometry(f"+{x}+{round(y - 16 * amount)}")
            if amount < 1:
                root.after(16, tick)
            else:
                intro.destroy()
                root.deiconify()
                root.focus_set()

        tick()

    def reveal_welcome():
        available_fonts = {family.casefold() for family in tkfont.families(root)}
        welcome_font = "MillyAbrams-Regular"
        if welcome_font.casefold() not in available_fonts:
            welcome_font = "Segoe UI"
        welcome = tk.Label(
            intro, text="Welcome", bg=cBG, fg=cTxt,
            font=(welcome_font, 38))
        welcome.place(relx=0.5, rely=0.44, anchor="center")
        status = tk.Label(
            intro, text="Loading GUI... 0%", bg=cBG, fg=cMut, font=FONT)
        status.place(relx=0.5, rely=0.61, anchor="center")

        bar = tk.Canvas(intro, width=444, height=12, bg=cBG,
                        highlightthickness=0, bd=0)
        bar.place(relx=0.5, rely=0.66, anchor="center")
        bar_x, bar_y = 2, 2
        bar_width = 440
        rrect(bar, 0, 0, 443, 11, 5, fill=cLine, outline="")
        progress = bar.create_rectangle(
            bar_x, bar_y, bar_x, bar_y + 8, fill=BLUE, outline="")
        fade_started = time.perf_counter()
        progress_started = time.perf_counter()

        def fade_in():
            elapsed = (time.perf_counter() - fade_started) * 1000
            amount = min(1.0, elapsed / fade_duration)
            eased = 1 - (1 - amount) ** 3
            intro.attributes("-alpha", eased)
            intro.geometry(f"+{x}+{round(y + 18 * (1 - eased))}")
            if amount < 1:
                root.after(16, fade_in)
            else:
                root.after(100, load_progress)

        def load_progress():
            progress_amount = min(
                1.0, (time.perf_counter() - progress_started) / 1.7)
            bar.coords(progress, bar_x, bar_y,
                       bar_x + bar_width * progress_amount, bar_y + 8)
            status.config(text=f"Loading GUI... {round(progress_amount * 100)}%")
            if progress_amount < 1:
                root.after(16, load_progress)
            else:
                root.after(240, fade_out)

        fade_in()

    root.after(900, reveal_welcome)


# ---------------------------------------------------------------------- Main
hkmenuopacity.var.trace_add(
    "write", lambda *a: (read_cfg(), apply_opacity()) if ready else None)

root.protocol("WM_DELETE_WINDOW", exit_app)
ready = True
apply_theme(theme_selector.get())
savesettings()
select_tab(1)
ui_animation_loop()
root.after(500, macro_focus_tick)
root.after(33, keystroke_animation_loop)
sound_error = initialize_click_sounds()
if sound_error:
    root.after(4000, lambda: report_sound_error(sound_error))
show_welcome_intro()
root.after(500, lambda: threading.Thread(
    target=check_latest_version, daemon=True).start())
root.after(6 * 60 * 60 * 1000, refresh_version_periodically)
root.mainloop()