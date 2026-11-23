import tkinter as tk
from tkinter import ttk
import sys
import ctypes
import ctypes.wintypes
import math
import random
import threading
import time
from pathlib import Path

import pystray
from PIL import Image, ImageDraw

# Windows API
user32 = ctypes.windll.user32
ctypes.set_last_error(True)

user32.RegisterHotKey.restype = ctypes.wintypes.BOOL
user32.RegisterHotKey.argtypes = [
    ctypes.wintypes.HWND,
    ctypes.c_int,
    ctypes.wintypes.UINT,
    ctypes.wintypes.UINT,
]
user32.UnregisterHotKey.restype = ctypes.wintypes.BOOL
user32.UnregisterHotKey.argtypes = [ctypes.wintypes.HWND, ctypes.c_int]

user32.WindowFromPoint.restype = ctypes.wintypes.HWND

user32.GetWindowRect.restype = ctypes.wintypes.BOOL
user32.GetWindowRect.argtypes = [ctypes.wintypes.HWND, ctypes.POINTER(ctypes.wintypes.RECT)]

user32.GetParent.restype = ctypes.wintypes.HWND
user32.GetParent.argtypes = [ctypes.wintypes.HWND]
user32.GetWindowLongW.restype = ctypes.c_long
user32.GetWindowLongW.argtypes = [ctypes.wintypes.HWND, ctypes.c_int]
user32.SetWindowLongW.restype = ctypes.c_long
user32.SetWindowLongW.argtypes = [ctypes.wintypes.HWND, ctypes.c_int, ctypes.c_long]

gdi32 = ctypes.windll.gdi32
user32.GetDC.restype = ctypes.c_void_p
user32.GetDC.argtypes = [ctypes.wintypes.HWND]
user32.ReleaseDC.restype = ctypes.c_int
user32.ReleaseDC.argtypes = [ctypes.wintypes.HWND, ctypes.c_void_p]
gdi32.GetPixel.restype = ctypes.wintypes.DWORD
gdi32.GetPixel.argtypes = [ctypes.c_void_p, ctypes.c_int, ctypes.c_int]

GWL_EXSTYLE = -20
WS_EX_LAYERED = 0x00080000
WS_EX_TRANSPARENT = 0x00000020  
WS_EX_TOOLWINDOW = 0x00000080    
WS_EX_NOACTIVATE = 0x08000000    

kernel32 = ctypes.windll.kernel32

ES_CONTINUOUS = 0x80000000
ES_SYSTEM_REQUIRED = 0x00000001
ES_DISPLAY_REQUIRED = 0x00000002

kernel32.SetThreadExecutionState.restype = ctypes.wintypes.DWORD
kernel32.SetThreadExecutionState.argtypes = [ctypes.wintypes.DWORD]

_sleep_lock_count = 0
_sleep_lock_lock = threading.Lock()


def prevent_sleep(keep_display_on=False):
    global _sleep_lock_count
    with _sleep_lock_lock:
        _sleep_lock_count += 1
        flags = ES_CONTINUOUS | ES_SYSTEM_REQUIRED
        if keep_display_on:
            flags |= ES_DISPLAY_REQUIRED
        kernel32.SetThreadExecutionState(flags)


def allow_sleep(force=False):
    global _sleep_lock_count
    with _sleep_lock_lock:
        if force:
            _sleep_lock_count = 0
        else:
            _sleep_lock_count = max(0, _sleep_lock_count - 1)
        if _sleep_lock_count == 0:
            kernel32.SetThreadExecutionState(ES_CONTINUOUS)


ERROR_ALREADY_EXISTS = 183
_instance_mutex = kernel32.CreateMutexW(None, False, "Mouser_SingleInstance_Mutex")
if ctypes.get_last_error() == ERROR_ALREADY_EXISTS:
    try:
        import tkinter.messagebox as messagebox
        _tmp_root = tk.Tk()
        _tmp_root.withdraw()
        messagebox.showwarning(
            "Mouser is already running."
        )
        _tmp_root.destroy()
    except Exception:
        print("Mouser is already running.")
    raise SystemExit(0)

# Global hotkeys (scrapped)
HOTKEY_IDS = {
    1: ord('Z'),
    2: ord('X'),
    3: ord('C'),
    4: ord('V'),
    5: ord('B'),  
}
MOD_NOREPEAT = 0x4000  
hotkey_thread = None
hotkey_thread_id = None

APP_DIR = Path(sys.executable).resolve().parent if getattr(sys, "frozen", False) else Path(__file__).resolve().parent
WINDOW_ICON_PATH = APP_DIR / "Assets" / "Images" / "icon.ico"
TRAY_ICON_PATH = Path(__file__).with_name("tray_icon.png")

class POINT(ctypes.Structure):
    _fields_ = [
        ("x", ctypes.c_long),
        ("y", ctypes.c_long)
    ]

def get_mouse_position():
    pt = POINT()
    user32.GetCursorPos(ctypes.byref(pt))
    return pt.x, pt.y

def cursor_over_own_window():

    try:
        pt = POINT()
        user32.GetCursorPos(ctypes.byref(pt))
        cx, cy = pt.x, pt.y

        candidate_hwnds = []

        if motion_win is not None:
            try:
                if motion_win.winfo_exists():
                    candidate_hwnds.append(motion_win.winfo_id())
            except Exception:
                pass

        if mini_mode and mini_win is not None:
            try:
                if mini_win.winfo_exists():
                    candidate_hwnds.append(mini_win.winfo_id())
            except Exception:
                pass
        else:
            try:
                if root.winfo_exists() and root.state() != "withdrawn":
                    candidate_hwnds.append(root.winfo_id())
            except Exception:
                pass

        for hwnd in candidate_hwnds:
            rect = ctypes.wintypes.RECT()
            if user32.GetWindowRect(ctypes.wintypes.HWND(hwnd), ctypes.byref(rect)):
                if rect.left <= cx <= rect.right and rect.top <= cy <= rect.bottom:
                    return True

        return False
    except Exception:
        return False


running = False
movement_thread = None
clicking = False
click_thread = None


mini_mode = False
mini_win = None
mini_status_label = None


motion_win = None
motion_status_label = None


crosshair_win = None
crosshair_canvas = None
crosshair_on = False
invert_color = None  
invert_rgb = None   
INVERT_SMOOTHING = 0.18   
INVERT_INTERVAL_MS = 33   
CROSSHAIR_KEY = "#010101"  
CROSSHAIR_STYLES = ("Cross", "Cross + Dot", "Dot", "Circle", "Sniper Scope")
CROSSHAIR_COLORS = {
    "Green": "#00ff00",
    "Red": "#ff0000",
    "Cyan": "#00ffff",
    "Yellow": "#ffff00",
    "White": "#ffffff",
    "Magenta": "#ff00ff",
    "Orange": "#ff8000",
}


user_hidden_to_tray = False

def auto_clicker():
    global clicking

    try:
        interval = float(click_interval_var.get())
        if interval <= 0:
            raise ValueError
    except ValueError:
        set_status("Status: Invalid Click Interval", fg="red")
        update_mini_status("Bad Interval", "red")
        clicking = False
        return

    min_interval = 0.001
    if interval < min_interval:
        interval = min_interval
        set_status(f"Status: Interval too low, using {min_interval:.3f}s", fg="orange")
        update_mini_status("Idle: low interval", "orange")

    next_click = time.perf_counter()
    while clicking:
        if not cursor_over_own_window():
            user32.mouse_event(0x0002, 0, 0, 0, 0)
            user32.mouse_event(0x0004, 0, 0, 0, 0)


        this_interval = interval
        if ranked_mode_var.get():
            jitter = random.uniform(-0.35, 0.35)
            this_interval = max(min_interval, interval * (1 + jitter))

        next_click += this_interval
        sleep_time = next_click - time.perf_counter()
        if sleep_time > 0:
            time.sleep(sleep_time)
        else:
            next_click = time.perf_counter()

def start_clicker(event=None):
    global clicking, click_thread

    if clicking:
        return

    clicking = True
    prevent_sleep()
    click_thread = threading.Thread(target=auto_clicker, daemon=True)
    click_thread.start()
    set_status("Status: Autoclicker Running", fg="green")
    update_mini_status("Clicking", "green")

    if not running:
        enter_mini_mode()


def stop_clicker(event=None):
    global clicking

    was_clicking = clicking
    clicking = False
    set_status("Status: Autoclicker Stopped", fg="gray")
    update_mini_status("Idle", "gray")

    if was_clicking:
        allow_sleep()

    exit_mini_mode()


def infinity_motion():
    global running

    center_x, center_y = get_mouse_position()

    try:
        width = int(width_var.get())
        height = int(height_var.get())
        speed = float(speed_var.get())
    except ValueError:
        root.after(0, lambda: set_status("Status: Invalid Input", fg="red"))
        root.after(0, lambda: update_motion_status("Bad input", "red"))
        root.after(0, stop_motion)
        return

    t = 0.0
    last_set_pos = None
    movement_deadzone = 8

    while running:

        if last_set_pos is not None:
            current_pos = get_mouse_position()
            dx = abs(current_pos[0] - last_set_pos[0])
            dy = abs(current_pos[1] - last_set_pos[1])
            if dx > movement_deadzone or dy > movement_deadzone:
                root.after(0, lambda: stop_motion(auto_reason="Cursor moved"))
                return

        # Infinity
        x = int(center_x + width * math.sin(t))
        y = int(center_y + height * math.sin(2 * t))

        user32.SetCursorPos(x, y)

        last_set_pos = get_mouse_position()

        t += speed
        time.sleep(0.005)

def start_motion(event=None):
    global running, movement_thread

    if running:
        return

    running = True
    prevent_sleep(keep_display_on=True)

    movement_thread = threading.Thread(
        target=infinity_motion,
        daemon=True
    )
    movement_thread.start()

    if autoclick_var.get() and not clicking:
        start_clicker()

    set_status("Status: Running", fg="green")
    update_motion_status("Moving", "green")


    sync_root_visibility()

def stop_motion(event=None, *, auto_reason=None):
    global running

    was_running = running
    running = False
    if clicking:
        stop_clicker()

    if was_running:
        allow_sleep()

    if auto_reason:
        set_status(f"Status: Stopped ({auto_reason})", fg="gray")
        update_motion_status("Idle", "gray")
    else:
        set_status("Status: Stopped", fg="gray")
        update_motion_status("Idle", "gray")


    sync_root_visibility()


def toggle_motion(event=None):
    if running:
        stop_motion()
    else:
        start_motion()


def unregister_hotkeys():
    for hotkey_id in HOTKEY_IDS:
        try:
            user32.UnregisterHotKey(None, hotkey_id)
        except Exception:
            pass


def hotkey_listener():
    global hotkey_thread_id
    hotkey_thread_id = user32.GetCurrentThreadId()
    try:
        msg = ctypes.wintypes.MSG()
        PM_NOREMOVE = 0x0000
        user32.PeekMessageW(ctypes.byref(msg), None, 0, 0, PM_NOREMOVE)
    except Exception:
        pass

    failed = []
    for hotkey_id, vk in HOTKEY_IDS.items():
        ok = user32.RegisterHotKey(None, hotkey_id, MOD_NOREPEAT, vk)
        if not ok:
            err = ctypes.get_last_error()
            key_name = chr(vk)
            print(f"Warning: could not register hotkey id {hotkey_id} (vk={vk}): WinError {err}")
            if err == 1409:
                print("That key combo is already registered by another application.")
                failed.append(f"{key_name} (already in use)")
            elif err == 5:
                print("Access denied. The target window or app is likely running elevated; "
                      "try running this script as Administrator too.")
                failed.append(f"{key_name} (access denied)")
            else:
                failed.append(f"{key_name} (error {err})")

    if failed:
        msg = "Hotkey unavailable: " + ", ".join(failed)
        root.after(0, lambda m=msg: set_status(f"Status: {m}", fg="red"))

    msg = ctypes.wintypes.MSG()
    while True:
        ret = user32.GetMessageW(ctypes.byref(msg), None, 0, 0)
        if ret == 0 or ret == -1:
            break
        if msg.message == 0x0312:  # WM_HOTKEY
            if msg.wParam == 1:
                root.after(0, toggle_motion)
            elif msg.wParam == 2:
                root.after(0, stop_motion)
            elif msg.wParam == 3:
                root.after(0, start_clicker)
            elif msg.wParam == 4:
                root.after(0, stop_clicker)
            elif msg.wParam == 5:
                root.after(0, toggle_crosshair)
        user32.TranslateMessage(ctypes.byref(msg))
        user32.DispatchMessageW(ctypes.byref(msg))
    unregister_hotkeys()


def register_hotkeys():
    global hotkey_thread
    hotkey_thread = threading.Thread(target=hotkey_listener, daemon=True)
    hotkey_thread.start()

# Crosshair overlay
def make_click_through(win):
    """Make a Tk window click-through, non-activating and hidden from Alt+Tab."""
    win.update_idletasks()
    wid = win.winfo_id()
    hwnd = user32.GetParent(wid) or wid
    style = user32.GetWindowLongW(hwnd, GWL_EXSTYLE)
    style |= WS_EX_LAYERED | WS_EX_TRANSPARENT | WS_EX_TOOLWINDOW | WS_EX_NOACTIVATE
    user32.SetWindowLongW(hwnd, GWL_EXSTYLE, style)


def _clamped_int(var, default, lo, hi):
    try:
        value = int(float(var.get()))
    except (ValueError, tk.TclError):
        value = default
    return max(lo, min(hi, value))


def resolve_crosshair_color():
    if ch_invert_var.get() and invert_color:
        color = invert_color
    else:
        name = ch_color_var.get().strip()
        color = CROSSHAIR_COLORS.get(name, name)  
        try:
            root.winfo_rgb(color)
        except tk.TclError:
            color = CROSSHAIR_COLORS["Green"]
    if color.lower() == CROSSHAIR_KEY:
        color = "#020202"
    return color


def _crosshair_center_and_gap():
    sw = root.winfo_screenwidth()
    sh = root.winfo_screenheight()
    size = _clamped_int(ch_size_var, 12, 1, 400)
    thick = _clamped_int(ch_thickness_var, 2, 1, 20)
    gap = _clamped_int(ch_gap_var, 4, 0, 200)
    cx = sw // 2 + _clamped_int(ch_offx_var, 0, -2000, 2000)
    cy = sh // 2 + _clamped_int(ch_offy_var, 0, -2000, 2000)
    return sw, sh, cx, cy, gap + size + thick + 4


def sample_background():
  
    sw, sh, cx, cy, d = _crosshair_center_and_gap()
    hdc = user32.GetDC(None)
    if not hdc:
        return None
    total = [0, 0, 0]
    count = 0
    try:
        for dx, dy in ((-d, -d), (d, -d), (-d, d), (d, d)):
            x, y = cx + dx, cy + dy
            if not (0 <= x < sw and 0 <= y < sh):
                continue
            px = gdi32.GetPixel(hdc, x, y)
            if px == 0xFFFFFFFF:  # CLR_INVALID
                continue
            total[0] += px & 0xFF
            total[1] += (px >> 8) & 0xFF
            total[2] += (px >> 16) & 0xFF
            count += 1
    finally:
        user32.ReleaseDC(None, hdc)
    if count == 0:
        return None
    return tuple(t // count for t in total)


def inverse_rgb(rgb):
    r, g, b = rgb
    inv = (255 - r, 255 - g, 255 - b)

    def lum(c):
        return 0.299 * c[0] + 0.587 * c[1] + 0.114 * c[2]


    if abs(lum(inv) - lum(rgb)) < 90:
        inv = (255, 255, 255) if lum(rgb) < 128 else (0, 0, 0)
    return inv


def _update_invert_color():
    global invert_color, invert_rgb
    if crosshair_win is None:
        return
    try:
        if ch_invert_var.get():
            bg = sample_background()
            if bg:
                target = inverse_rgb(bg)
                if invert_rgb is None:
                    invert_rgb = [float(v) for v in target] 
                else:
                   
                    for i in range(3):
                        invert_rgb[i] += (target[i] - invert_rgb[i]) * INVERT_SMOOTHING
            new_color = None
            if invert_rgb is not None:
                new_color = "#%02x%02x%02x" % tuple(int(round(v)) for v in invert_rgb)
        else:
            invert_rgb = None
            new_color = None
        if new_color != invert_color:
            invert_color = new_color
            draw_crosshair()
        root.after(INVERT_INTERVAL_MS, _update_invert_color)
    except tk.TclError:
        pass


def _paint_crosshair(c, style, cx, cy, sw, sh, size, thick, gap, color, extra):
  
    w = thick + extra
    r_dot = thick + 1 + extra / 2

    def arm(x1, y1, x2, y2, width=w):
        c.create_line(x1, y1, x2, y2, fill=color, width=width, capstyle="butt")

    def dot(x, y, r):
        c.create_oval(x - r, y - r, x + r, y + r, fill=color, outline=color)

    if style in ("Cross", "Cross + Dot"):
        arm(cx - gap - size, cy, cx - gap, cy)
        arm(cx + gap, cy, cx + gap + size, cy)
        arm(cx, cy - gap - size, cx, cy - gap)
        arm(cx, cy + gap, cx, cy + gap + size)
        if style == "Cross + Dot":
            dot(cx, cy, r_dot)

    elif style == "Dot":
        dot(cx, cy, max(2, size // 6) + extra / 2)

    elif style == "Circle":
        c.create_oval(cx - size, cy - size, cx + size, cy + size, outline=color, width=w)
        dot(cx, cy, r_dot)

    elif style == "Sniper Scope":
    
        arm(0, cy, cx - gap, cy)
        arm(cx + gap, cy, sw, cy)
        arm(cx, 0, cx, cy - gap)
        arm(cx, cy + gap, cx, sh)
        spacing = max(12, size * 3)
        for i in range(1, 6):
            for px, py in ((cx - i * spacing, cy), (cx + i * spacing, cy),
                           (cx, cy - i * spacing), (cx, cy + i * spacing)):
                if 0 <= px <= sw and 0 <= py <= sh:
                    dot(px, py, r_dot)
        dot(cx, cy, r_dot)


def draw_crosshair(*_):
    if crosshair_canvas is None:
        return
    try:
        c = crosshair_canvas
        c.delete("all")

        sw, sh, cx, cy, _ = _crosshair_center_and_gap()
        size = _clamped_int(ch_size_var, 12, 1, 400)
        thick = _clamped_int(ch_thickness_var, 2, 1, 20)
        gap = _clamped_int(ch_gap_var, 4, 0, 200)
        style = ch_style_var.get()
        if style not in CROSSHAIR_STYLES:
            style = "Cross + Dot"
        color = resolve_crosshair_color()

        if ch_outline_var.get():
            _paint_crosshair(c, style, cx, cy, sw, sh, size, thick, gap, "#000000", 2)
        _paint_crosshair(c, style, cx, cy, sw, sh, size, thick, gap, color, 0)
    except tk.TclError:
        pass


def _keep_crosshair_on_top():
    if crosshair_win is None:
        return
    try:
        crosshair_win.attributes("-topmost", True)
        crosshair_win.lift()
        root.after(1000, _keep_crosshair_on_top)
    except tk.TclError:
        pass


def show_crosshair():
    global crosshair_win, crosshair_canvas, crosshair_on

    if crosshair_win is not None:
        return

    sw = root.winfo_screenwidth()
    sh = root.winfo_screenheight()

    win = tk.Toplevel(root)
    win.overrideredirect(True)
    win.attributes("-topmost", True)
    win.configure(bg=CROSSHAIR_KEY)
    win.geometry(f"{sw}x{sh}+0+0")
    win.attributes("-transparentcolor", CROSSHAIR_KEY)

    canvas = tk.Canvas(win, bg=CROSSHAIR_KEY, highlightthickness=0, bd=0)
    canvas.pack(fill="both", expand=True)

    crosshair_win = win
    crosshair_canvas = canvas
    crosshair_on = True

    make_click_through(win)
    draw_crosshair()
    root.after(1000, _keep_crosshair_on_top)
    root.after(INVERT_INTERVAL_MS, _update_invert_color)

    ch_button_text.set("Hide Crosshair")
    set_status("Status: Crosshair On", fg="green")


def hide_crosshair():
    global crosshair_win, crosshair_canvas, crosshair_on, invert_color, invert_rgb

    if crosshair_win is not None:
        try:
            crosshair_win.destroy()
        except tk.TclError:
            pass
    crosshair_win = None
    crosshair_canvas = None
    crosshair_on = False
    invert_color = None
    invert_rgb = None

    ch_button_text.set("Show Crosshair")
    set_status("Status: Crosshair Off", fg="gray")


def toggle_crosshair(event=None):
    if crosshair_on:
        hide_crosshair()
    else:
        show_crosshair()

# GUI
root = tk.Tk()
root.title("Mouser")

WINDOW_WIDTH = 650
WINDOW_HEIGHT = 580

def center_window(win, width, height):
    win.update_idletasks()
    screen_width = win.winfo_screenwidth()
    screen_height = win.winfo_screenheight()
    x = (screen_width // 2) - (width // 2)
    y = (screen_height // 2) - (height // 2)
    win.geometry(f"{width}x{height}+{x}+{y}")

center_window(root, WINDOW_WIDTH, WINDOW_HEIGHT)
root.resizable(False, False)


def set_window_icon():
    if WINDOW_ICON_PATH.exists():
        try:
            root.iconbitmap(default=str(WINDOW_ICON_PATH))
        except Exception as e:
            print(f"Warning: could not set native icon bitmap from {WINDOW_ICON_PATH}: {e}")

set_window_icon()

title = ttk.Label(
    root,
    text="Mouser",
    font=("Impact", 20,)
)
title.pack(pady=10)

main_frame = ttk.Frame(root)
main_frame.pack(padx=10, pady=10, fill="x")

left_frame = ttk.LabelFrame(main_frame, text="Autoclicker", padding=10)
left_frame.pack(side="left", padx=10, pady=5, fill="both", expand=True)

right_frame = ttk.LabelFrame(main_frame, text="Motion", padding=10)
right_frame.pack(side="right", padx=10, pady=5, fill="both", expand=True)


autoclick_var = tk.BooleanVar(value=False)

ctk = ttk.Checkbutton(
    left_frame,
    text="Autoclicker",
    variable=autoclick_var
)
ctk.grid(row=0, column=0, columnspan=2, padx=5, pady=5, sticky="w")

ttk.Label(left_frame, text="Interval:").grid(
    row=1, column=0, padx=5, pady=5, sticky="w"
)

click_interval_var = tk.StringVar(value="0.1")

ttk.Entry(
    left_frame,
    textvariable=click_interval_var,
    width=12
).grid(row=1, column=1, padx=5, pady=5)

ranked_mode_var = tk.BooleanVar(value=False)

ttk.Checkbutton(
    left_frame,
    text="Ranked",
    variable=ranked_mode_var
).grid(row=2, column=0, columnspan=2, padx=5, pady=5, sticky="w")

ttk.Button(
    left_frame,
    text="Start",
    command=start_clicker,
    takefocus=False
).grid(row=3, column=0, columnspan=2, padx=5, pady=10, sticky="ew")

# Motion
width_var = tk.StringVar(value="250")
height_var = tk.StringVar(value="125")
speed_var = tk.StringVar(value="0.02")

ttk.Label(right_frame, text="Width:").grid(
    row=0, column=0, padx=5, pady=5, sticky="w"
)

ttk.Entry(
    right_frame,
    textvariable=width_var,
    width=12
).grid(row=0, column=1, padx=5, pady=5)

# Height
ttk.Label(right_frame, text="Height:").grid(
    row=1, column=0, padx=5, pady=5, sticky="w"
)

ttk.Entry(
    right_frame,
    textvariable=height_var,
    width=12
).grid(row=1, column=1, padx=5, pady=5)

# Speed
ttk.Label(right_frame, text="Speed:").grid(
    row=2, column=0, padx=5, pady=5, sticky="w"
)

ttk.Entry(
    right_frame,
    textvariable=speed_var,
    width=12
).grid(row=2, column=1, padx=5, pady=5)

ttk.Button(
    right_frame,
    text="Start",
    command=toggle_motion,
    takefocus=False
).grid(row=3, column=0, columnspan=2, padx=5, pady=10, sticky="ew")


ch_style_var = tk.StringVar(value="Cross + Dot")
ch_color_var = tk.StringVar(value="Green")
ch_size_var = tk.StringVar(value="12")
ch_thickness_var = tk.StringVar(value="2")
ch_gap_var = tk.StringVar(value="4")
ch_offx_var = tk.StringVar(value="0")
ch_offy_var = tk.StringVar(value="0")
ch_outline_var = tk.BooleanVar(value=True)
ch_invert_var = tk.BooleanVar(value=False)
ch_button_text = tk.StringVar(value="Show Crosshair")

crosshair_frame = ttk.LabelFrame(root, text="Crosshair Overlay (hotkey: B)", padding=10)
crosshair_frame.pack(padx=20, pady=(0, 5), fill="x")

ttk.Label(crosshair_frame, text="Style:").grid(row=0, column=0, padx=5, pady=4, sticky="w")
ttk.Combobox(
    crosshair_frame, textvariable=ch_style_var, values=CROSSHAIR_STYLES,
    state="readonly", width=12
).grid(row=0, column=1, padx=5, pady=4)

ttk.Label(crosshair_frame, text="Color:").grid(row=0, column=2, padx=5, pady=4, sticky="w")
ch_color_combo = ttk.Combobox(
    crosshair_frame, textvariable=ch_color_var, values=list(CROSSHAIR_COLORS),
    width=12
)
ch_color_combo.grid(row=0, column=3, padx=5, pady=4)

ttk.Checkbutton(
    crosshair_frame, text="Outline", variable=ch_outline_var
).grid(row=0, column=4, padx=5, pady=4, sticky="w")

ttk.Checkbutton(
    crosshair_frame, text="Invert", variable=ch_invert_var
).grid(row=0, column=5, padx=5, pady=4, sticky="w")

ttk.Label(crosshair_frame, text="Size:").grid(row=1, column=0, padx=5, pady=4, sticky="w")
ttk.Spinbox(crosshair_frame, from_=1, to=400, textvariable=ch_size_var, width=8).grid(row=1, column=1, padx=5, pady=4)

ttk.Label(crosshair_frame, text="Thickness:").grid(row=1, column=2, padx=5, pady=4, sticky="w")
ttk.Spinbox(crosshair_frame, from_=1, to=20, textvariable=ch_thickness_var, width=8).grid(row=1, column=3, padx=5, pady=4)

ttk.Label(crosshair_frame, text="Gap:").grid(row=1, column=4, padx=5, pady=4, sticky="w")
ttk.Spinbox(crosshair_frame, from_=0, to=200, textvariable=ch_gap_var, width=8).grid(row=1, column=5, padx=5, pady=4)

ttk.Label(crosshair_frame, text="Offset X:").grid(row=2, column=0, padx=5, pady=4, sticky="w")
ttk.Spinbox(crosshair_frame, from_=-2000, to=2000, textvariable=ch_offx_var, width=8).grid(row=2, column=1, padx=5, pady=4)

ttk.Label(crosshair_frame, text="Offset Y:").grid(row=2, column=2, padx=5, pady=4, sticky="w")
ttk.Spinbox(crosshair_frame, from_=-2000, to=2000, textvariable=ch_offy_var, width=8).grid(row=2, column=3, padx=5, pady=4)

ttk.Button(
    crosshair_frame,
    textvariable=ch_button_text,
    command=toggle_crosshair,
    takefocus=False
).grid(row=2, column=4, columnspan=2, padx=5, pady=4, sticky="ew")

for _v in (ch_style_var, ch_color_var, ch_size_var, ch_thickness_var,
           ch_gap_var, ch_offx_var, ch_offy_var, ch_outline_var, ch_invert_var):
    _v.trace_add("write", draw_crosshair)


def update_color_state(*_):
   
    ch_color_combo.config(state="disabled" if ch_invert_var.get() else "normal")


ch_invert_var.trace_add("write", update_color_state)
update_color_state()


status_label = tk.Label(
    root,
    text="Status: Stopped",
    font=("Arial", 10),
    fg="gray"
)
status_label.pack(pady=10)

def set_status(text, fg="black"):
    status_label.config(text=text, fg=fg)



def update_mini_status(text, fg):
    if mini_status_label is not None:
        try:
            mini_status_label.config(text=text, fg=fg)
        except tk.TclError:
            pass


def update_motion_status(text, fg):
    if motion_status_label is not None:
        try:
            motion_status_label.config(text=text, fg=fg)
        except tk.TclError:
            pass


instructions = ttk.Label(
    root,
    text=(
        "\n"
        "© Mendukusai. All Rights Reserved."
    ),
    justify="center"
)
instructions.pack()
root.focus_force()
register_hotkeys()
def create_tray_image():
    for candidate in (WINDOW_ICON_PATH, TRAY_ICON_PATH):
        if candidate.exists():
            try:
                image = Image.open(candidate)
                image = image.convert("RGBA")
                image = image.resize((64, 64), Image.Resampling.LANCZOS if hasattr(Image, 'Resampling') else Image.ANTIALIAS)
                return image
            except Exception as e:
                print(f"Warning: could not load hidden / tray icon {candidate}: {e}")

    image = Image.new("RGB", (64, 64), color=(0, 0, 0))
    draw = ImageDraw.Draw(image)
    draw.rectangle([16, 16, 28, 48], fill="white")
    draw.rectangle([36, 16, 48, 48], fill="white")
    return image


def sync_root_visibility():
    should_hide = running or mini_mode
    try:
        if should_hide:
            if root.state() != "withdrawn":
                root.withdraw()
        elif not user_hidden_to_tray and root.state() == "withdrawn":
            root.deiconify()
            root.lift()
            root.focus_force()
    except tk.TclError:
        pass


def force_show_root():
    global user_hidden_to_tray
    user_hidden_to_tray = False
    root.deiconify()
    root.lift()
    root.focus_force()


def make_panel_button(parent, text, cmd, width=5):
    b = tk.Button(
        parent, text=text, command=cmd,
        bg="#333333", fg="white", activebackground="#444444",
        activeforeground="white", relief="flat", bd=0,
        font=("Arial", 8), width=width
    )
    b.pack(side="left", padx=1)
    return b


def make_draggable(win, widgets):
    offset = {"x": 0, "y": 0}

    def start_drag(event):
        offset["x"] = event.x
        offset["y"] = event.y

    def do_drag(event):
        x = win.winfo_pointerx() - offset["x"]
        y = win.winfo_pointery() - offset["y"]
        win.geometry(f"+{x}+{y}")

    for widget in widgets:
        widget.bind("<ButtonPress-1>", start_drag)
        widget.bind("<B1-Motion>", do_drag)


def enter_mini_mode():
    global mini_mode, mini_win, mini_status_label

    if mini_mode:
        return
    mini_mode = True

    sync_root_visibility()  

    mini_win = tk.Toplevel(root)
    if WINDOW_ICON_PATH.exists():
        try:
            mini_win.iconbitmap(default=str(WINDOW_ICON_PATH))
        except tk.TclError:
            pass
    mini_win.overrideredirect(True)       
    mini_win.attributes("-topmost", True)  
    try:
        mini_win.attributes("-alpha", 0.92)  
    except tk.TclError:
        pass
    mini_win.configure(bg="#1e1e1e")

    bar = tk.Frame(mini_win, bg="#1e1e1e")
    bar.pack(fill="both", expand=True, padx=4, pady=4)

    mini_status_label = tk.Label(
        bar, text="Stopped", fg="gray", bg="#1e1e1e",
        font=("Arial", 9), anchor="w", width=10
    )
    mini_status_label.pack(side="left", padx=(4, 6))

    make_panel_button(bar, "Stop", stop_clicker)

    mini_status_label.config(
        text=("Clicking" if clicking else "Idle"),
        fg=("green" if clicking else "gray"),
    )


    mini_win.update_idletasks()
    w = mini_win.winfo_reqwidth() + 4
    h = mini_win.winfo_reqheight() + 4

    cursor_x, cursor_y = get_mouse_position()
    offset = 20
    x = cursor_x + offset
    y = cursor_y + offset

    screen_w = mini_win.winfo_screenwidth()
    screen_h = mini_win.winfo_screenheight()
    x = max(0, min(x, screen_w - w))
    y = max(0, min(y, screen_h - h))

    mini_win.geometry(f"{w}x{h}+{x}+{y}")


    make_draggable(mini_win, (mini_win, bar, mini_status_label))

    mini_win.protocol("WM_DELETE_WINDOW", exit_mini_mode)


def exit_mini_mode(force_show=False):
    global mini_mode, mini_win, mini_status_label

    if not mini_mode:
        return
    mini_mode = False

    if mini_win is not None:
        try:
            mini_win.destroy()
        except tk.TclError:
            pass
    mini_win = None
    mini_status_label = None

    if force_show:
        force_show_root()
    else:
        sync_root_visibility()


def show_window(icon=None, item=None):
    if mini_mode:
        root.after(0, lambda: exit_mini_mode(force_show=True))
    else:
        root.after(0, force_show_root)


def hide_window(icon=None, item=None):
    global user_hidden_to_tray
    user_hidden_to_tray = True
    root.after(0, root.withdraw)
    set_status("Status: Running in tray", fg="orange")


def quit_app(icon=None, item=None):
    global running, clicking
    running = False
    clicking = False
    allow_sleep(force=True)
    if mini_win is not None:
        try:
            mini_win.destroy()
        except Exception:
            pass
    if motion_win is not None:
        try:
            motion_win.destroy()
        except Exception:
            pass
    if crosshair_win is not None:
        try:
            crosshair_win.destroy()
        except Exception:
            pass
    try:
        icon.stop()
    except Exception:
        pass
    try:
        if hotkey_thread_id is not None:
            user32.PostThreadMessageW(hotkey_thread_id, 0x0012, 0, 0)
    except Exception:
        pass
    unregister_hotkeys()
    root.after(0, root.destroy)


def setup_tray():
    menu = pystray.Menu(
        pystray.MenuItem("Show", show_window),
        pystray.MenuItem("Toggle Crosshair", lambda icon, item: root.after(0, toggle_crosshair)),
        pystray.MenuItem("Exit", quit_app)
    )
    icon = pystray.Icon("Mouser", create_tray_image(), "Mouser", menu)
    threading.Thread(target=icon.run, daemon=True).start()
    return icon

tray_icon = setup_tray()

root.protocol("WM_DELETE_WINDOW", hide_window)

root.mainloop()
